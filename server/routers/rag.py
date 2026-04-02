import uuid

from fastapi import APIRouter, HTTPException, Query

from rag.agents import archive_favourite_list
from rag.chroma import get_count, get_stats
from rag.retrieval import query_rag
from server.models import RAGIngestRequest, RAGQueryRequest
from server.services.ingest_state import get_ingest_task, set_ingest_task
from server.services.mys_api import get_favourite, get_post_full

router = APIRouter(prefix="/api/rag", tags=["rag"])

# 启动时预热 ChromaDB 连接
try:
    get_count()
except Exception:
    pass


def _collect_favourite_items(req: RAGIngestRequest) -> list:
    all_items = []
    offset = ""
    page_size = 20
    max_pages = 50

    for _ in range(max_pages):
        fav_data = get_favourite(
            stuid=req.stuid,
            stoken=req.stoken,
            mid=req.mid,
            game_uid=req.game_uid,
            game_region=req.game_region,
            offset=offset,
            size=page_size,
        )
        if fav_data.get("retcode") != 0:
            raise HTTPException(status_code=400, detail=fav_data.get("message", "收藏夹获取失败"))

        data = fav_data.get("data") or {}
        page = data.get("list") or []
        all_items.extend(page)

        is_last = data.get("is_last", True)
        if is_last or len(page) < page_size:
            break
        offset = data.get("next_offset") or ""

    if req.selected_game_id is not None:
        all_items = [
            item for item in all_items
            if (item.get("post") or {}).get("game_id") == req.selected_game_id
        ]

    return all_items


def _enrich_vod_list(items: list, stuid: str, stoken: str, mid: str):
    for item in items:
        post = item.get("post", {})
        if not item.get("vod_list"):
            try:
                full = get_post_full(str(post.get("post_id", "")), stuid, stoken, mid)
                full_data = (full.get("data") or {})
                full_post_obj = full_data.get("post") or {}
                full_vod = full_post_obj.get("vod_list") or []
                if full_vod:
                    item["vod_list"] = full_vod
            except Exception as e:
                print(f"[Ingest] post={post.get('post_id')} 补全 vod_list 失败: {e}")


@router.post("/ingest/favourites/start")
async def rag_ingest_start(req: RAGIngestRequest):
    try:
        all_items = _collect_favourite_items(req)
        scope_label = f"分区 {req.selected_game_id}" if req.selected_game_id is not None else "全部分区"

        task_id = str(uuid.uuid4())
        total = len(all_items)
        set_ingest_task(task_id, {
            "task_id": task_id,
            "status": "running",
            "current": 0,
            "total": total,
            "indexed": 0,
            "skipped": 0,
            "errors": 0,
            "message": f"归档进行中（{scope_label}）",
            "selected_game_id": req.selected_game_id,
        })

        if total == 0:
            set_ingest_task(task_id, {
                "status": "done",
                "message": "所选分区收藏为空，无需归档",
            })
            return {
                "status": "ok",
                "task_id": task_id,
                "total": 0,
                "selected_game_id": req.selected_game_id,
                "message": "所选分区收藏为空，无需归档",
            }

        import asyncio

        def _run_task():
            try:
                _enrich_vod_list(all_items, req.stuid, req.stoken, req.mid)

                def _on_progress(current, total_count, _last_result, partial):
                    set_ingest_task(task_id, {
                        "status": "running",
                        "current": current,
                        "total": total_count,
                        "indexed": partial.get("indexed", 0),
                        "skipped": partial.get("skipped", 0),
                        "errors": partial.get("errors", 0),
                        "message": f"归档进行中：{current}/{total_count}",
                    })

                result = archive_favourite_list(all_items, progress_cb=_on_progress)
                set_ingest_task(task_id, {
                    "status": "done",
                    "current": result.get("total", 0),
                    "total": result.get("total", 0),
                    "indexed": result.get("indexed", 0),
                    "skipped": result.get("skipped", 0),
                    "errors": result.get("errors", 0),
                    "message": f"归档完成（{scope_label}）：共 {result.get('total', 0)} 篇，新增 {result.get('indexed', 0)} 块，跳过 {result.get('skipped', 0)} 篇，失败 {result.get('errors', 0)} 篇",
                })
            except Exception as e:
                set_ingest_task(task_id, {
                    "status": "error",
                    "message": str(e),
                })

        asyncio.get_event_loop().run_in_executor(None, _run_task)

        return {
            "status": "ok",
            "task_id": task_id,
            "total": total,
            "selected_game_id": req.selected_game_id,
            "message": f"归档任务已启动（{scope_label}）",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ingest/favourites/progress")
async def rag_ingest_progress(task_id: str = Query(...)):
    task = get_ingest_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.post("/ingest/favourites")
async def rag_ingest(req: RAGIngestRequest):
    try:
        all_items = _collect_favourite_items(req)

        if not all_items:
            return {
                "status": "ok",
                "message": "所选分区收藏为空，无需归档",
                "total": 0,
                "selected_game_id": req.selected_game_id,
            }

        _enrich_vod_list(all_items, req.stuid, req.stoken, req.mid)

        import asyncio
        result = await asyncio.get_event_loop().run_in_executor(None, archive_favourite_list, all_items)

        scope_label = f"分区 {req.selected_game_id}" if req.selected_game_id is not None else "全部分区"
        return {
            "status": "ok",
            "message": f"归档完成（{scope_label}）：共 {result['total']} 篇，新增 {result['indexed']} 块，跳过 {result['skipped']} 篇，失败 {result['errors']} 篇",
            "selected_game_id": req.selected_game_id,
            **result,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def rag_stats():
    try:
        stats = get_stats()
        return {
            "posts": stats["posts"],
            "docs": stats["docs"],
            "vectors": stats["vectors"],
            "by_type": stats["by_type"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query")
async def rag_query(req: RAGQueryRequest):
    try:
        import asyncio
        result = await asyncio.get_event_loop().run_in_executor(None, query_rag, req.question, req.game_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/reset")
async def rag_reset():
    try:
        import rag.chroma as chroma_mod

        chroma_mod._get_collection()

        try:
            chroma_mod._client.delete_collection(chroma_mod.COLLECTION)
        except Exception:
            pass

        chroma_mod._collection = None
        chroma_mod._get_collection()

        return {"status": "ok", "message": "知识库已清空"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
