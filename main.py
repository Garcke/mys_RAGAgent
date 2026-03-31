import base64
import io
import json
import random
import string
import time
import uuid
from hashlib import md5
from typing import Optional
from urllib.parse import urlparse, parse_qs

import qrcode
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# ═══════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════

APP_ID = "12"

QR_FETCH_URL  = "https://hk4e-sdk.mihoyo.com/hk4e_cn/combo/panda/qrcode/fetch"
QR_QUERY_URL  = "https://hk4e-sdk.mihoyo.com/hk4e_cn/combo/panda/qrcode/query"
FP_URL        = "https://public-data-api.mihoyo.com/device-fp/api/getFp"
ROLES_URL     = "https://api-takumi.miyoushe.com/binding/api/getUserGameRolesByStoken"
FAVOURITE_URL  = "https://bbs-api.miyoushe.com/painter/api/userFavouritePostList"
POST_FULL_URL  = "https://bbs-api.miyoushe.com/post/api/getPostFull"

# DS 盐值（来自 mys_GetDS1.py）
DS_SALT = "lX8m5VO5at5JG7hR8hzqFwzyL5aB1tYo"

# 固定设备信息（与原脚本保持一致）
DEVICE_ID = "78083f6d-2360-31ed-ad9d-70be3877c64b"
DEVICE_FP = "38d816a694e81"


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def gen_ds() -> str:
    """生成动态签名 DS（来自 mys_GetDS1.py）"""
    chars = string.ascii_letters + string.digits
    t = int(time.time())
    r = "".join(random.choices(chars, k=6))
    main = f"salt={DS_SALT}&t={t}&r={r}"
    ds = md5(main.encode("UTF-8")).hexdigest()
    return f"{t},{r},{ds}"


def qr_headers(device_id: str) -> dict:
    """扫码接口请求头（与 mys_GetQR.py 保持一致）"""
    return {
        "x-rpc-client_type": "5",
        "x-rpc-app_version": "2.102.1",
        "x-rpc-sys_version": "12",
        "x-rpc-channel": "miyousheluodi",
        "x-rpc-device_id": device_id,
        "x-rpc-device_fp": DEVICE_FP,
        "x-rpc-device_name": "Redmi 23117RK66C",
        "x-rpc-device_model": "23117RK66C",
        "x-rpc-h265_supported": "1",
        "referer": "https://app.mihoyo.com",
        "x-rpc-verify_key": "bll8iq97cem8",
        "x-rpc-csm_source": "myself",
        "accept-encoding": "gzip",
        "user-agent": "okhttp/4.9.3",
    }


def api_headers(stuid: str, stoken: str, mid: str) -> dict:
    """通用 API 请求头（Cookie + DS）"""
    return {
        "User-Agent": "okhttp/4.9.3",
        "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip",
        "DS": gen_ds(),
        "x-rpc-client_type": "2",
        "x-rpc-app_version": "2.102.1",
        "x-rpc-sys_version": "12",
        "x-rpc-channel": "miyousheluodi",
        "x-rpc-device_id": DEVICE_ID,
        "x-rpc-device_fp": DEVICE_FP,
        "x-rpc-device_name": "Redmi 23117RK66C",
        "x-rpc-device_model": "23117RK66C",
        "x-rpc-h265_supported": "1",
        "Referer": "https://app.mihoyo.com",
        "x-rpc-verify_key": "bll8iq97cem8",
        "x-rpc-csm_source": "myself",
        "Cookie": f"stuid={stuid};stoken={stoken};mid={mid};",
    }


def extract_credentials(raw: str) -> dict:
    """
    从扫码确认 payload 提取凭证。
    raw = '{"uid":"82463740","mid":"0yjtygxmpo_mhy","token":"v2_..."}'
    stoken 的组装方式：mid + token（与各脚本 Cookie 头一致）
    """
    data = json.loads(raw)
    uid   = data["uid"]
    mid   = data["mid"]
    token = data["token"]
    stoken = mid + token          # 业务约定：stoken = mid + token
    return {
        "stuid":  uid,
        "mid":    mid,
        "token":  token,
        "stoken": stoken,
    }


# ═══════════════════════════════════════════════════════════════
# 业务函数
# ═══════════════════════════════════════════════════════════════

def fetch_qrcode() -> dict:
    """生成扫码登录二维码，返回 ticket / device_id / base64 图片"""
    device_id = str(uuid.uuid4())
    params = {"app_id": APP_ID, "device": device_id}
    resp = requests.get(QR_FETCH_URL, params=params,
                        headers=qr_headers(device_id), timeout=10)
    resp.raise_for_status()
    res_url = resp.json()["data"]["url"]

    # 解析 ticket
    ticket = parse_qs(urlparse(res_url).query)["ticket"][0]

    # 生成 base64 二维码图片（与 mys_GetQR.py 参数一致）
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(res_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode()

    return {"ticket": ticket, "device_id": device_id, "qr_image": img_b64}


def query_qrcode_status(ticket: str, device_id: str) -> dict:
    """轮询二维码扫码状态"""
    params = {"app_id": APP_ID, "device": device_id, "ticket": ticket}
    resp = requests.post(QR_QUERY_URL, params=params,
                         headers=qr_headers(device_id), timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_roles_by_stoken(stuid: str, stoken: str, mid: str) -> dict:
    """获取游戏角色列表（来自 mys_GetUid&Region.py）"""
    params = {"game_biz": "hk4e_cn"}
    resp = requests.get(ROLES_URL, params=params,
                        headers=api_headers(stuid, stoken, mid), timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_post_full(post_id: str, stuid: str, stoken: str, mid: str) -> dict:
    """获取帖子完整数据（含 vod_list）"""
    params = {"post_id": post_id}
    resp = requests.get(POST_FULL_URL, params=params,
                        headers=api_headers(stuid, stoken, mid), timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_favourite(stuid: str, stoken: str, mid: str,
                  game_uid: str, game_region: str,
                  offset: str = "", size: int = 20) -> dict:
    """获取收藏夹列表（来自 mys_GetFavourite.py）"""
    params = {
        "aid": stuid,
        "offset": offset or "",
        "size": size,
        "game_region": game_region,
        "game_uid": game_uid,
    }
    resp = requests.get(FAVOURITE_URL, params=params,
                        headers=api_headers(stuid, stoken, mid), timeout=15)
    resp.raise_for_status()
    return resp.json()


# ═══════════════════════════════════════════════════════════════
# FastAPI 应用
# ═══════════════════════════════════════════════════════════════

app = FastAPI(title="米游社收藏夹 RAG 服务", version="1.0.0")

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    print(f"[422] {request.url} body validation error: {exc.errors()}")
    return JSONResponse(status_code=422, content={"detail": str(exc.errors())})

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Pydantic 模型 ───────────────────────────────────────────────

class FavouriteRequest(BaseModel):
    stuid: str
    stoken: str
    mid: str
    game_uid: str
    game_region: str = "cn_gf01"
    offset: str = ""
    size: int = 20


class RolesRequest(BaseModel):
    stuid: str
    stoken: str
    mid: str


# ── 路由 ────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    """首页返回 index.html"""
    return FileResponse("static/index.html")


@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": int(time.time())}


# ── 登录 ────────────────────────────────────────────────────────

@app.post("/api/login/qrcode/generate")
async def generate_qrcode():
    """生成米游社扫码登录二维码，返回 base64 PNG 图片"""
    try:
        result = fetch_qrcode()
        return {
            "status": "pending",
            "ticket": result["ticket"],
            "device_id": result["device_id"],
            "qr_image": result["qr_image"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/login/qrcode/status")
async def check_qrcode_status(
    ticket: str = Query(...),
    device_id: str = Query(...),
):
    """
    轮询扫码状态。
    - stat == 'Confirmed' 时提取凭证并返回 credentials
    - 其他状态返回 status: 'pending'
    """
    try:
        result = query_qrcode_status(ticket, device_id)
        if result.get("retcode") != 0:
            raise HTTPException(status_code=400, detail=result.get("message", "未知错误"))

        stat = result["data"]["stat"]

        if stat == "Confirmed":
            raw = result["data"]["payload"]["raw"]
            creds = extract_credentials(raw)
            return {"status": "confirmed", "credentials": creds}
        else:
            # Init / Scanned 等中间态
            return {"status": "pending", "stat": stat}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 角色列表 ─────────────────────────────────────────────────────

@app.post("/api/roles/list")
async def roles_list(req: RolesRequest):
    """获取用户游戏角色列表（game_uid + game_region）"""
    try:
        data = get_roles_by_stoken(req.stuid, req.stoken, req.mid)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 收藏夹 ───────────────────────────────────────────────────────

@app.post("/api/favourite/get")
async def favourite_get(req: FavouriteRequest):
    """获取收藏夹帖子列表"""
    try:
        data = get_favourite(
            stuid=req.stuid,
            stoken=req.stoken,
            mid=req.mid,
            game_uid=req.game_uid,
            game_region=req.game_region,
            offset=req.offset,
            size=req.size,
        )
        if data.get("retcode") != 0:
            raise HTTPException(status_code=400, detail=data.get("message", "API 错误"))
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── RAG 真实接口 ─────────────────────────────────────────────

from rag.agents import archive_favourite_list
from rag.retrieval import query_rag
from rag.chroma import get_stats, get_count

# 启动时预热 ChromaDB 连接
try:
    get_count()
except Exception:
    pass


class RAGIngestRequest(BaseModel):
    stuid: str
    stoken: str
    mid: str
    game_uid: str = ""
    game_region: str = "cn_gf01"
    size: int = 20
    selected_game_id: int | None = None


class RAGQueryRequest(BaseModel):
    question: str
    game_id: int | None = None


@app.post("/api/rag/ingest/favourites")
async def rag_ingest(req: RAGIngestRequest):
    """拉取收藏夹（全量翻页）并归档到 RAG 知识库"""
    try:
        # 全量翻页拉取收藏夹
        all_items = []
        offset = ""
        page_size = 20
        max_pages = 50  # 最多拉 50 页，防止死循环

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

            data   = fav_data.get("data") or {}
            page   = data.get("list") or []
            all_items.extend(page)

            # 判断是否还有更多页
            is_last = data.get("is_last", True)
            if is_last or len(page) < page_size:
                break
            # 使用 next_offset 翻页（米游社 API 用字符串游标）
            offset = data.get("next_offset") or ""

        # 按分区筛选（selected_game_id 存在时）
        if req.selected_game_id is not None:
            all_items = [
                item for item in all_items
                if (item.get("post") or {}).get("game_id") == req.selected_game_id
            ]

        if not all_items:
            return {
                "status": "ok",
                "message": "所选分区收藏为空，无需归档",
                "total": 0,
                "selected_game_id": req.selected_game_id,
            }

        # 对 vod_list 为空的帖子，调用详情接口补全
        for item in all_items:
            post = item.get("post", {})
            if not item.get("vod_list"):  # vod_list 在 item 顶层
                try:
                    full = get_post_full(str(post.get("post_id", "")), req.stuid, req.stoken, req.mid)
                    full_data = (full.get("data") or {})
                    full_post_obj = full_data.get("post") or {}
                    full_vod = full_post_obj.get("vod_list") or []
                    if full_vod:
                        item["vod_list"] = full_vod
                except Exception as e:
                    print(f"[Ingest] post={post.get('post_id')} 补全 vod_list 失败: {e}")

        # 异步归档（在线程池中执行避免阻塞）
        import asyncio
        result = await asyncio.get_event_loop().run_in_executor(
            None, archive_favourite_list, all_items
        )

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


@app.get("/api/rag/stats")
async def rag_stats():
    """知识库统计"""
    try:
        stats = get_stats()
        return {
            "posts":   stats["posts"],
            "docs":    stats["docs"],
            "vectors": stats["vectors"],
            "by_type": stats["by_type"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/rag/query")
async def rag_query(req: RAGQueryRequest):
    """RAG 知识库问答"""
    try:
        import asyncio
        result = await asyncio.get_event_loop().run_in_executor(
            None, query_rag, req.question, req.game_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/rag/reset")
async def rag_reset():
    """清空知识库（删除 ChromaDB collection 并重建）"""
    try:
        import rag.chroma as chroma_mod

        # 确保 client 已初始化
        chroma_mod._get_collection()

        # 删除旧 collection（若不存在则忽略）
        try:
            chroma_mod._client.delete_collection(chroma_mod.COLLECTION)
        except Exception:
            pass

        # 重置模块级缓存并重建空 collection
        chroma_mod._collection = None
        chroma_mod._get_collection()

        return {"status": "ok", "message": "知识库已清空"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# ═══════════════════════════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 