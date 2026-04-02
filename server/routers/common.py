import time

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/", include_in_schema=False)
async def root():
    return FileResponse("static/index.html")


@router.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": int(time.time())}
