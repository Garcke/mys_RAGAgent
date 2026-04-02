import base64
import io
import json
import random
import string
import time
import uuid
from hashlib import md5
from urllib.parse import parse_qs, urlparse

import qrcode
import requests

APP_ID = "12"

QR_FETCH_URL = "https://hk4e-sdk.mihoyo.com/hk4e_cn/combo/panda/qrcode/fetch"
QR_QUERY_URL = "https://hk4e-sdk.mihoyo.com/hk4e_cn/combo/panda/qrcode/query"
ROLES_URL = "https://api-takumi.miyoushe.com/binding/api/getUserGameRolesByStoken"
FAVOURITE_URL = "https://bbs-api.miyoushe.com/painter/api/userFavouritePostList"
POST_FULL_URL = "https://bbs-api.miyoushe.com/post/api/getPostFull"

DS_SALT = "lX8m5VO5at5JG7hR8hzqFwzyL5aB1tYo"
DEVICE_ID = "78083f6d-2360-31ed-ad9d-70be3877c64b"
DEVICE_FP = "38d816a694e81"


def gen_ds() -> str:
    chars = string.ascii_letters + string.digits
    t = int(time.time())
    r = "".join(random.choices(chars, k=6))
    main = f"salt={DS_SALT}&t={t}&r={r}"
    ds = md5(main.encode("UTF-8")).hexdigest()
    return f"{t},{r},{ds}"


def qr_headers(device_id: str) -> dict:
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
    data = json.loads(raw)
    uid = data["uid"]
    mid = data["mid"]
    token = data["token"]
    stoken = mid + token
    return {
        "stuid": uid,
        "mid": mid,
        "token": token,
        "stoken": stoken,
    }


def fetch_qrcode() -> dict:
    device_id = str(uuid.uuid4())
    params = {"app_id": APP_ID, "device": device_id}
    resp = requests.get(QR_FETCH_URL, params=params, headers=qr_headers(device_id), timeout=10)
    resp.raise_for_status()
    res_url = resp.json()["data"]["url"]

    ticket = parse_qs(urlparse(res_url).query)["ticket"][0]

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
    params = {"app_id": APP_ID, "device": device_id, "ticket": ticket}
    resp = requests.post(QR_QUERY_URL, params=params, headers=qr_headers(device_id), timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_roles_by_stoken(stuid: str, stoken: str, mid: str) -> dict:
    params = {"game_biz": "hk4e_cn"}
    resp = requests.get(ROLES_URL, params=params, headers=api_headers(stuid, stoken, mid), timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_post_full(post_id: str, stuid: str, stoken: str, mid: str) -> dict:
    params = {"post_id": post_id}
    resp = requests.get(POST_FULL_URL, params=params, headers=api_headers(stuid, stoken, mid), timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_favourite(
    stuid: str,
    stoken: str,
    mid: str,
    game_uid: str,
    game_region: str,
    offset: str = "",
    size: int = 20,
) -> dict:
    params = {
        "aid": stuid,
        "offset": offset or "",
        "size": size,
        "game_region": game_region,
        "game_uid": game_uid,
    }
    resp = requests.get(FAVOURITE_URL, params=params, headers=api_headers(stuid, stoken, mid), timeout=15)
    resp.raise_for_status()
    return resp.json()
