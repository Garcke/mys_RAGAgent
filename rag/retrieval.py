"""
检索 + Query Parser + Context Assembler + 回答生成 (单 ChromaDB 版) — 阶段二
"""
import os
import re
import json
from collections import defaultdict

from dotenv import load_dotenv
import dashscope
from dashscope import TextEmbedding, Generation,MultiModalConversation

from . import chroma

load_dotenv()
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY", "")

QUERY_PARSER_MODEL = os.getenv("QUERY_PARSER_MODEL", "qwen-max")
ANSWER_MODEL = os.getenv("ANSWER_MODEL", "qwen-max")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")

# game_id 映射（用于 Query Parser 实体识别）
GAME_NAMES = {
    "崩坏3": 1, "崩坏 3": 1,
    "原神": 2, "genshin": 2,
    "崩坏学园2": 3, "崩坏学园 2": 3,
    "未定事件簿": 4,
    "大别野": 5,
    "星穹铁道": 6, "崩坏星穹铁道": 6, "崩坏：星穹铁道": 6,
    "绝区零": 8, "zzz": 8,
}


def _content_to_text(content) -> str:
    """兼容 DashScope message.content 可能是字符串或分段数组。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


def is_chitchat_query(question: str) -> bool:
    """判定是否是寒暄类问题，寒暄不返回来源"""
    q = (question or "").strip().lower()
    if not q:
        return True

    # 常见寒暄与泛问候
    patterns = [
        r"^你好[呀啊吗嘛]?$",
        r"^嗨[呀啊]?$",
        r"^hello[!. ]*$",
        r"^hi[!. ]*$",
        r"^在吗[?？]?$",
        r"^早上好$",
        r"^中午好$",
        r"^晚上好$",
        r"^你是谁[?？]?$",
    ]
    return any(re.match(p, q) for p in patterns)


# ── Query Parser ───────────────────────────────────────────

def parse_query(question: str) -> dict:
    """
    用 qwen-max 解析查询意图，生成 ChromaDB where 过滤条件。
    返回 {"where": dict|None, "rewritten": str}
    """
    system = """你是一个查询解析器，从用户问题中提取结构化过滤信息。
请严格返回 JSON，格式如下（所有字段可选，不确定则不填）：
{
  "game_id": <int|null>,       // 游戏ID：1崩坏3,2原神,3崩坏学园2,4未定事件簿,5大别野,6星穹铁道,8绝区零
  "is_official": <bool|null>,  // 是否只看官方帖子
  "version": <str|null>,       // 游戏版本号，如"2.7"
  "rewritten": <str>           // 改写后的检索查询，更适合语义搜索
}
只返回 JSON，不要任何解释。"""

    try:
        resp = MultiModalConversation.call(
            model=QUERY_PARSER_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": question},
            ],
            result_format="message",
        )
        if resp.status_code != 200:
            raise RuntimeError(resp.message)
        raw = _content_to_text(resp.output.choices[0]["message"]["content"]).strip()
        # 去掉可能的 markdown 代码块
        raw = raw.strip("`").lstrip("json").strip()
        parsed = json.loads(raw)
    except Exception as e:
        print(f"[QueryParser] 解析失败，使用原始查询: {e}")
        return {"where": None, "rewritten": question}

    # 构建 ChromaDB where 子句
    conditions = []
    game_id = parsed.get("game_id")
    if game_id and isinstance(game_id, int):
        conditions.append({"game_id": {"$eq": game_id}})

    is_official = parsed.get("is_official")
    if is_official is True:
        conditions.append({"is_official": {"$eq": True}})

    version = parsed.get("version")
    if version and isinstance(version, str) and version.strip():
        conditions.append({"version_tag": {"$eq": version.strip()}})

    where = None
    if len(conditions) == 1:
        where = conditions[0]
    elif len(conditions) > 1:
        where = {"$and": conditions}

    rewritten = parsed.get("rewritten") or question
    return {"where": where, "rewritten": rewritten}


# ── 向量检索 ───────────────────────────────────────────────

def retrieve(query_text: str, n_results: int = 50, where: dict = None) -> list:
    resp = TextEmbedding.call(
        model=EMBEDDING_MODEL,
        input=query_text,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Embedding 失败: {resp.message}")
    q_emb = resp.output["embeddings"][0]["embedding"]

    results = chroma.query(q_emb, n_results=n_results, where=where)

    chunks = []
    for i, doc_id in enumerate(results["ids"][0]):
        meta = results["metadatas"][0][i]
        chunks.append({
            "doc_id":        doc_id,
            "document":      results["documents"][0][i],
            "distance":      results["distances"][0][i],
            "post_id":       meta.get("post_id", ""),
            "modality":      meta.get("modality", "text"),
            "post_title":    meta.get("post_title", ""),
            "post_url":      meta.get("post_url", ""),
            "author_name":   meta.get("author_name", ""),
            "forum_name":    meta.get("forum_name", ""),
            "is_official":   meta.get("is_official", False),
            "quality_score": float(meta.get("quality_score", 0)),
            "media_url":     meta.get("media_url", ""),
            "like_num":      int(meta.get("like_num", 0)),
            "game_id":       int(meta.get("game_id", 0)),
        })
    return chunks


# ── Context Assembler ──────────────────────────────────────

def assemble_context(chunks: list) -> tuple:
    """
    按 post_id 聚合，生成知识卡片。
    返回 (context_str, sources)
    """
    groups = defaultdict(list)
    for c in chunks:
        # 过滤低相关度的 chunk（cosine distance > 0.5 表示相关性不足）
        if c["distance"] > 0.5:
            continue
        groups[c["post_id"]].append(c)

    # 按 quality_score 排序
    sorted_posts = sorted(
        groups.items(),
        key=lambda kv: max(c["quality_score"] for c in kv[1]),
        reverse=True,
    )

    cards   = []
    sources = []

    for pid, group in sorted_posts[:4]:  # 最多 4 张知识卡片，保证质量
        best         = min(group, key=lambda x: x["distance"])
        official_tag = "【官方】" if best["is_official"] else ""
        title        = best["post_title"] or pid
        author       = best["author_name"]
        forum        = best["forum_name"]
        url          = best["post_url"]

        text_parts = [c["document"] for c in group if c["modality"] == "text"]
        img_parts  = [c["document"] for c in group if c["modality"] == "image"]
        img_urls   = [c["media_url"] for c in group if c["modality"] == "image" and c["media_url"]]
        video_urls = [c["media_url"] for c in group if c["modality"] == "video" and c["media_url"]]

        text_content = "\n".join(text_parts)[:1200]
        img_content  = "\n".join(img_parts)[:600]

        card_lines = [
            f"【知识卡片{official_tag}】{title}",
            f"来源：{forum} · {author}  链接：{url}",
        ]
        if text_content:
            card_lines.append(f"文本内容：\n{text_content}")
        if img_content:
            card_lines.append(f"图片内容（AI描述）：\n{img_content}")
        if img_urls:
            card_lines.append(f"原图({len(img_urls)}张）：" + " ".join(img_urls[:3]))
        if video_urls:
            card_lines.append(f"视频：" + " ".join(video_urls[:2]))

        cards.append("\n".join(card_lines))
        sources.append({
            "doc_id":  best["doc_id"],
            "post_id": pid,
            "summary": title[:60],
            "type":    "official" if best["is_official"] else "user",
            "url":     url,
        })

    context_str = "\n\n---\n\n".join(cards)
    return context_str, sources


# ── LLM 生成 ───────────────────────────────────────────────

def generate_answer(question: str, context: str, sources: list) -> tuple:
    """调用回答模型生成回答，同时返回实际引用的 sources"""
    # 给每个知识卡片编号，用于引用追踪
    source_ids = [s["post_id"] for s in sources]
    system_prompt = (
        "你是一个米游社游戏助手，专门基于用户的收藏帖子回答问题。\n"
        "请基于提供的【知识卡片】回答用户问题。\n"
        "要求：\n"
        "1. 不要在回答末尾写 [1]、[2] 等脚注编号和参考文献列表，来源由系统单独展示\n"
        "2. 需要引用时直接在行内写作者名即可，例如：根据 Asgater 的攻略...\n"
        "3. 只引用与问题直接相关的内容，不相关的知识卡片忽略\n"
        "4. 【官方】标注的帖子优先采纳\n"
        "5. 涉及图片内容时说明'根据攻略截图显示...'\n"
        "6. 知识库信息不足时诚实说明\n"
        "7. 回答简洁清晰，使用中文，支持 Markdown 格式"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": f"知识卡片：\n\n{context}\n\n用户问题：{question}"},
    ]
    resp = MultiModalConversation.call(
        model=ANSWER_MODEL,
        messages=messages,
        result_format="message",
    )
    if resp.status_code != 200:
        raise RuntimeError(f"LLM 失败: {resp.message}")
    answer = _content_to_text(resp.output.choices[0]["message"]["content"])

    # 只保留 answer 中实际提到了 post_title 或 summary 的来源
    used_sources = []
    for s in sources:
        if s["summary"] and s["summary"][:10] in answer:
            used_sources.append(s)
    # 如果没匹配到任何来源，保留评分最高的一个
    if not used_sources and sources:
        used_sources = [sources[0]]

    return answer, used_sources


# ── 检索问答入口 ───────────────────────────────────────────

def query_rag(question: str, game_id: int = None) -> dict:
    """
    完整 RAG 流程：
    Query Parser → 向量检索 → Context Assembler → LLM 生成
    """
    # 寒暄类问题直接返回，不附带来源
    if is_chitchat_query(question):
        return {
            "answer": "你好！有什么可以帮你的？",
            "sources": [],
        }

    # 1. Query Parser
    parsed  = parse_query(question)
    where   = parsed["where"]
    requery = parsed["rewritten"]

    # 若前端传了 game_id，优先用前端的
    if game_id:
        where = {"game_id": {"$eq": int(game_id)}}

    # 2. 向量检索
    chunks = retrieve(requery, n_results=30, where=where)
    if not chunks:
        # 降级：去掉过滤条件重试
        if where:
            chunks = retrieve(requery, n_results=20, where=None)
        if not chunks:
            return {
                "answer": "知识库中暂无相关内容，请先归档收藏帖。",
                "sources": [],
            }

    # 3. Context Assembler
    context, sources = assemble_context(chunks)

    # 4. 生成回答（同时过滤实际引用的来源）
    answer, used_sources = generate_answer(question, context, sources)
    return {"answer": answer, "sources": used_sources}
