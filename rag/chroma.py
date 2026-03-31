"""
ChromaDB 单库封装 (单 ChromaDB 版)
按设计文档 3.1 节，Collection: miyou_favorites
"""
import os
from typing import List

import chromadb
from chromadb.config import Settings

CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "chroma")
COLLECTION = "miyou_favorites"

_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is None:
        os.makedirs(CHROMA_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=os.path.abspath(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        _collection = _client.get_or_create_collection(
            name=COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def add_documents(
    doc_ids: List[str],
    embeddings: List[List[float]],
    documents: List[str],
    metadatas: List[dict],
):
    """批量写入，自动 upsert"""
    _get_collection().upsert(
        ids=doc_ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )


def query(
    embedding: List[float],
    n_results: int = 50,
    where: dict = None,
) -> dict:
    """向量相似度检索（含 metadata 过滤）"""
    col = _get_collection()
    kwargs = dict(
        query_embeddings=[embedding],
        n_results=min(n_results, col.count() or 1),
        include=["documents", "metadatas", "distances"],
    )
    if where:
        kwargs["where"] = where
    return col.query(**kwargs)


def get_count() -> int:
    """获取向量总数"""
    return _get_collection().count()


def get_stats() -> dict:
    """统计各 modality 数量"""
    col = _get_collection()
    total = col.count()
    # 按 modality 分组统计
    by_modality = {"text": 0, "image": 0, "audio": 0, "video": 0}
    if total > 0:
        for mod in ["text", "image", "audio", "video"]:
            try:
                r = col.get(where={"modality": mod}, include=[])
                by_modality[mod] = len(r["ids"])
            except Exception:
                pass
    # 统计唯一 post 数
    posts = 0
    if total > 0:
        try:
            all_meta = col.get(include=["metadatas"])
            post_ids = {m.get("post_id") for m in all_meta["metadatas"] if m.get("post_id")}
            posts = len(post_ids)
        except Exception:
            pass
    return {
        "posts":   posts,
        "vectors": total,
        "docs":    total,
        "by_type": by_modality,
    }


def post_already_indexed(post_id: str) -> bool:
    """检查 post_id 是否已有任意分块入库"""
    col = _get_collection()
    if col.count() == 0:
        return False
    try:
        r = col.get(where={"post_id": post_id}, include=[], limit=1)
        return len(r["ids"]) > 0
    except Exception:
        return False
