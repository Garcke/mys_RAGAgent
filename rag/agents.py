"""
归档 Pipeline (单 ChromaDB 版) — 阶段二
实现：Router Agent + Text Agent + Image Agent + Merge Agent + Indexer Agent
"""
import os
import re
import time
from typing import TypedDict, List

from dotenv import load_dotenv
import dashscope
from dashscope import TextEmbedding, MultiModalConversation
from dashscope.audio.qwen_asr.qwen_transcription import QwenTranscription
from dashscope.audio.asr.transcription import Transcription as ParaformerTranscription
from langchain_text_splitters import RecursiveCharacterTextSplitter

from . import chroma

load_dotenv()
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY", "")

SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=1024,
    chunk_overlap=200,
    separators=["\n\n", "\n", "。", "！", "？", "，", " ", ""],
)

IMAGE_PROMPT = (
    "请详细描述这张游戏相关图片的内容，包括：角色名称、技能/数值信息、"
    "界面文字、活动奖励、场景描述等所有可见内容。尽量提取文字信息。"
)

# ── game_id 映射 ───────────────────────────────────────────
GAME_PATH = {
    1: "bh3", 2: "ys", 3: "bh2",
    4: "wd",  5: "dby", 6: "sr", 8: "zzz",
}

def make_post_url(post_id: str, game_id: int) -> str:
    return f"https://www.miyoushe.com/{GAME_PATH.get(game_id, 'dby')}/article/{post_id}"


# ── 状态定义 ───────────────────────────────────────────────
class ArchiveState(TypedDict):
    post_id: str
    raw_data: dict
    has_text: bool
    has_image: bool
    has_video: bool
    text_result: List[dict]
    image_result: List[dict]
    audio_result: List[dict]
    unified_docs: List[dict]
    index_status: dict


# ── 工具函数 ───────────────────────────────────────────────

def clean_content(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\[图片\]|\[链接\]|\[视频\]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compute_quality_score(like_num: int, is_official: bool, created_at: int) -> float:
    norm_like = min((like_num or 0) / 10000.0, 1.0)
    official  = 1.0 if is_official else 0.0
    days_old  = (time.time() - created_at) / 86400 if created_at else 365
    recency   = max(0.0, 1.0 - days_old / 365.0)
    return round(0.5 * norm_like + 0.3 * official + 0.2 * recency, 4)


def get_embedding(text: str) -> List[float]:
    resp = TextEmbedding.call(
        model=TextEmbedding.Models.text_embedding_v3,
        input=text,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Embedding 失败: {resp.message}")
    return resp.output["embeddings"][0]["embedding"]


def describe_image(image_url: str) -> str:
    """调用 qwen-vl-max 生成图片描述"""
    try:
        messages = [{
            "role": "user",
            "content": [
                {"image": image_url},
                {"text": IMAGE_PROMPT},
            ],
        }]
        resp = MultiModalConversation.call(
            model="qwen-vl-max",
            messages=messages,
        )
        if resp.status_code != 200:
            return ""
        content = resp.output.choices[0]["message"]["content"]
        # content 可能是 list[{"text": ...}] 或直接 str
        if isinstance(content, list):
            return " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        return str(content)
    except Exception as e:
        print(f"[ImageAgent] VL 失败 {image_url[:60]}: {e}")
        return ""


def pick_vod_url(vod: dict) -> str:
    """优先选择低清晰度 URL（更快更省）"""
    resolutions = vod.get("resolutions") or []
    if not isinstance(resolutions, list) or not resolutions:
        return ""

    # 优先 480P，其次按清晰度从低到高
    def rank(res):
        d = str(res.get("definition") or "")
        if "480" in d:
            return 0
        if "720" in d:
            return 1
        if "1080" in d:
            return 2
        return 3

    for r in sorted(resolutions, key=rank):
        url = r.get("url")
        if url:
            return str(url)
    return ""


def transcribe_video_audio(file_url: str) -> str:
    """调用 paraformer-v2 对视频 URL 做转写"""
    try:
        resp = ParaformerTranscription.call(
            model="paraformer-v2",
            file_urls=[file_url],
            language_hints=["zh", "en"],
        )
        if getattr(resp, "status_code", None) != 200:
            print(f"[AudioAgent] ASR 失败 status={getattr(resp, 'status_code', None)}")
            return ""

        output = getattr(resp, "output", None) or {}
        if isinstance(output, dict):
            results = output.get("results")
            if isinstance(results, list) and results:
                transcription_url = results[0].get("transcription_url") or ""
                if transcription_url:
                    import requests as _req
                    tr = _req.get(transcription_url, timeout=15)
                    tr.raise_for_status()
                    tr_data = tr.json()
                    transcripts = tr_data.get("transcripts") if isinstance(tr_data, dict) else None
                    if transcripts and isinstance(transcripts, list) and isinstance(transcripts[0], dict):
                        sentences = transcripts[0].get("sentences") or []
                        if sentences:
                            text = " ".join(s.get("text", "") for s in sentences if isinstance(s, dict))
                        else:
                            text = transcripts[0].get("text") or ""
                        if text:
                            return str(text).strip()
        return ""
    except Exception as e:
        print(f"[AudioAgent] ASR 异常 {file_url[:60]}: {e}")
        return ""


def build_base_metadata(raw: dict) -> dict:
    """
    公共元数据，ChromaDB 只支持 str/int/float/bool
    """
    post   = raw.get("post", {})
    stat   = raw.get("stat", {})
    user   = raw.get("user", {})
    forum  = raw.get("forum", {})
    topics = raw.get("topics", [])

    post_id     = str(post.get("post_id", ""))
    game_id     = int(post.get("game_id") or 0)
    forum_id    = int(forum.get("id") or 0)
    is_official = bool(post.get("post_status", {}).get("is_official", False))
    like_num    = int(stat.get("like_num") or 0)
    created_at  = int(post.get("created_at") or 0)
    quality     = compute_quality_score(like_num, is_official, created_at)
    entities    = ",".join(t.get("name", "") for t in topics if t.get("name"))

    # 从标题和内容中提取版本号，如 "2.7"、"3.0"
    subject_text = str(post.get("subject") or "")
    content_text = str(post.get("content") or "")
    version_match = re.search(r"(\d+\.\d+)\s*版本", subject_text + content_text)
    version_tag = version_match.group(1) if version_match else ""

    # 正确从 post 取 images 和 vod_list
    images   = post.get("images", []) or []
    vod_list = post.get("vod_list", []) or []

    return {
        "post_id":       post_id,
        "game_id":       game_id,
        "forum_id":      forum_id,
        "forum_name":    str(forum.get("name") or ""),
        "is_official":   is_official,
        "author_uid":    str(user.get("uid") or ""),
        "author_name":   str(user.get("nickname") or ""),
        "created_at":    created_at,
        "version_tag":   version_tag,
        "like_num":      like_num,
        "quality_score": quality,
        "entities":      entities,
        "intent_tags":   "",
        "post_title":    str(post.get("subject") or "")[:200],
        "post_url":      make_post_url(post_id, game_id),
        "has_image":     len(images) > 0,
        "has_video":     len(vod_list) > 0,
    }


# ── Router Agent ───────────────────────────────────────────

def router_agent(state: ArchiveState) -> ArchiveState:
    """分析帖子模态，设置路由标志"""
    raw      = state["raw_data"]
    post     = raw.get("post", {})
    content  = post.get("content") or post.get("text_summary") or ""
    images   = post.get("images", []) or []
    # vod_list 在 item 顶层，与 post 同级
    vod_list = raw.get("vod_list", []) or []

    state["has_text"]  = bool(content.strip())
    state["has_image"] = len(images) > 0
    state["has_video"] = len(vod_list) > 0
    print(f"[Router] post={post.get('post_id')} text={state['has_text']} image={state['has_image']} video={state['has_video']} vod_count={len(vod_list)}")
    return state


# ── Text Agent ─────────────────────────────────────────────

def text_agent(state: ArchiveState) -> ArchiveState:
    """文本 Agent：清洗 → 分块 → 构建文档"""
    if not state.get("has_text"):
        state["text_result"] = []
        return state

    raw  = state["raw_data"]
    post = raw.get("post", {})
    base = build_base_metadata(raw)

    subject   = str(post.get("subject") or "")
    content   = clean_content(post.get("content") or post.get("text_summary") or "")
    full_text = f"{subject}\n{content}".strip()

    if not full_text:
        state["text_result"] = []
        return state

    chunks  = SPLITTER.split_text(full_text) if len(full_text) > 50 else [full_text]
    results = []
    for i, chunk in enumerate(chunks):
        doc_id = f"doc_{base['post_id']}_text_{i:03d}"
        meta   = {**base, "modality": "text", "media_url": "", "chunk_index": i}
        results.append({"doc_id": doc_id, "document": chunk, "metadata": meta})

    state["text_result"] = results
    return state


# ── Image Agent ────────────────────────────────────────────

def image_agent(state: ArchiveState) -> ArchiveState:
    """图片 Agent：并发调用 qwen-vl-max 生成描述 → 构建文档"""
    if not state.get("has_image"):
        state["image_result"] = []
        return state

    raw    = state["raw_data"]
    post   = raw.get("post", {})
    base   = build_base_metadata(raw)
    images = (post.get("images", []) or [])[:5]  # 最多处理 5 张

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def process_image(args):
        i, img_url = args
        description = describe_image(img_url)
        return i, img_url, description

    results = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(process_image, (i, url)): i
                   for i, url in enumerate(images)}
        # 按原始顺序收集结果
        img_results = {}
        for future in as_completed(futures):
            i, img_url, description = future.result()
            img_results[i] = (img_url, description)

    for i in sorted(img_results):
        img_url, description = img_results[i]
        if not description:
            continue
        doc_id   = f"doc_{base['post_id']}_image_{i:03d}"
        document = f"[图片描述] {description}"
        meta     = {
            **base,
            "modality":    "image",
            "media_url":   img_url,
            "chunk_index": i,
        }
        results.append({"doc_id": doc_id, "document": document, "metadata": meta})
        print(f"[ImageAgent] post={base['post_id']} img={i} 描述完成")

    state["image_result"] = results
    return state


# ── Audio Agent ────────────────────────────────────────────

def audio_agent(state: ArchiveState) -> ArchiveState:
    """音频 Agent：对 vod_list 视频做 ASR 转写并分块"""
    if not state.get("has_video"):
        state["audio_result"] = []
        return state

    raw    = state["raw_data"]
    post   = raw.get("post", {})
    base   = build_base_metadata(raw)
    # vod_list 在 item 顶层，与 post 同级
    vods   = (raw.get("vod_list", []) or [])[:2]  # 每帖最多处理 2 个视频

    results = []
    for i, vod in enumerate(vods):
        media_url = pick_vod_url(vod)
        if not media_url:
            continue

        transcript = transcribe_video_audio(media_url)
        transcript = clean_content(transcript)
        if not transcript:
            continue

        chunks = SPLITTER.split_text(transcript) if len(transcript) > 300 else [transcript]
        for j, chunk in enumerate(chunks):
            doc_id = f"doc_{base['post_id']}_audio_{i:03d}_{j:03d}"
            document = f"[音频转写] {chunk}"
            meta = {
                **base,
                "modality": "audio",
                "media_url": media_url,
                "chunk_index": j,
            }
            results.append({"doc_id": doc_id, "document": document, "metadata": meta})

        print(f"[AudioAgent] post={base['post_id']} vod={i} 转写完成，chunks={len(chunks)}")

    state["audio_result"] = results
    return state


# ── Merge Agent ────────────────────────────────────────────

def merge_agent(state: ArchiveState) -> ArchiveState:
    """合并 Text + Image + Audio 文档"""
    unified = []
    unified.extend(state.get("text_result", []))
    unified.extend(state.get("image_result", []))
    unified.extend(state.get("audio_result", []))
    state["unified_docs"] = unified
    return state


# ── Indexer Agent ──────────────────────────────────────────

def indexer_agent(state: ArchiveState) -> ArchiveState:
    """Embedding → 批量写入 ChromaDB"""
    docs    = state.get("unified_docs", [])
    post_id = state["post_id"]

    if not docs:
        state["index_status"] = {"post_id": post_id, "indexed": 0, "skipped": 0}
        return state

    doc_ids    = []
    embeddings = []
    documents  = []
    metadatas  = []

    for doc in docs:
        try:
            emb = get_embedding(doc["document"])
        except Exception as e:
            print(f"[Indexer] Embedding 失败 {doc['doc_id']}: {e}")
            continue
        doc_ids.append(doc["doc_id"])
        embeddings.append(emb)
        documents.append(doc["document"])
        metadatas.append(doc["metadata"])

    if doc_ids:
        chroma.add_documents(doc_ids, embeddings, documents, metadatas)

    state["index_status"] = {
        "post_id": post_id,
        "indexed": len(doc_ids),
        "skipped": len(docs) - len(doc_ids),
    }
    return state


# ── 归档入口 ───────────────────────────────────────────────

def archive_post(raw_item: dict) -> dict:
    """归档单条收藏帖（Router → Text + Image → Merge → Index）"""
    post_id = str(raw_item.get("post", {}).get("post_id", ""))
    if not post_id:
        return {"error": "无效的 post_id"}

    if chroma.post_already_indexed(post_id):
        return {"post_id": post_id, "status": "skipped", "indexed": 0}

    state: ArchiveState = {
        "post_id":      post_id,
        "raw_data":     raw_item,
        "has_text":     False,
        "has_image":    False,
        "has_video":    False,
        "text_result":  [],
        "image_result": [],
        "audio_result": [],
        "unified_docs": [],
        "index_status": {},
    }
    state = router_agent(state)
    state = text_agent(state)
    state = image_agent(state)
    state = audio_agent(state)
    state = merge_agent(state)
    state = indexer_agent(state)
    return {"post_id": post_id, "status": "ok", **state["index_status"]}


def archive_favourite_list(items: list) -> dict:
    """批量归档收藏夹列表（并发处理帖子）"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = {"total": len(items), "indexed": 0, "skipped": 0, "errors": 0}

    # 最多 3 个帖子并发，避免超出 DashScope QPS 限制
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(archive_post, item): item for item in items}
        for future in as_completed(futures):
            try:
                r = future.result()
                if r.get("status") == "ok":
                    results["indexed"] += r.get("indexed", 0)
                elif r.get("status") == "skipped":
                    results["skipped"] += 1
                else:
                    results["errors"] += 1
            except Exception as e:
                print(f"[Archive] 失败: {e}")
                results["errors"] += 1
    return results
