from fastapi import APIRouter, HTTPException

from server.models import FavouriteRequest, RolesRequest
from server.services.mys_api import get_favourite, get_roles_by_stoken

router = APIRouter(prefix="/api", tags=["mys"])


@router.post("/roles/list")
async def roles_list(req: RolesRequest):
    try:
        return get_roles_by_stoken(req.stuid, req.stoken, req.mid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/favourite/get")
async def favourite_get(req: FavouriteRequest):
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
