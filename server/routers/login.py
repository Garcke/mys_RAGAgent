from fastapi import APIRouter, HTTPException, Query

from server.services.mys_api import extract_credentials, fetch_qrcode, query_qrcode_status

router = APIRouter(prefix="/api/login", tags=["login"])


@router.post("/qrcode/generate")
async def generate_qrcode():
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


@router.post("/qrcode/status")
async def check_qrcode_status(ticket: str = Query(...), device_id: str = Query(...)):
    try:
        result = query_qrcode_status(ticket, device_id)
        if result.get("retcode") != 0:
            raise HTTPException(status_code=400, detail=result.get("message", "未知错误"))

        stat = result["data"]["stat"]
        if stat == "Confirmed":
            raw = result["data"]["payload"]["raw"]
            creds = extract_credentials(raw)
            return {"status": "confirmed", "credentials": creds}

        return {"status": "pending", "stat": stat}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
