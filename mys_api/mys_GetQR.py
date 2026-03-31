import requests
import time
import uuid
from urllib.parse import urlparse, parse_qs
import qrcode
import json

url_FetchQrcode = "https://hk4e-sdk.mihoyo.com/hk4e_cn/combo/panda/qrcode/fetch"
url_QueryQrcodeStatus = "https://hk4e-sdk.mihoyo.com/hk4e_cn/combo/panda/qrcode/query"
device_id = str(uuid.uuid4())
params_FetchQrcode = {"app_id": "12", "device": f"{device_id}"}

headers = {
    "x-rpc-client_type": "5",
    "x-rpc-app_version": "2.102.1",
    "x-rpc-sys_version": "12",
    "x-rpc-channel": "miyousheluodi",
    "x-rpc-device_id": f"{device_id}",
    "x-rpc-device_fp": "38d816a694e81",
    "x-rpc-device_name": "Redmi 23117RK66C",
    "x-rpc-device_model": "23117RK66C",
    "x-rpc-h265_supported": "1",
    "referer": "https://app.mihoyo.com",
    "x-rpc-verify_key": "bll8iq97cem8",
    "x-rpc-csm_source": "myself",
    "accept-encoding": "gzip",
    "user-agent": "okhttp/4.9.3",
}


# print(params)
session = requests.Session()

response1 = session.get(url_FetchQrcode, params=params_FetchQrcode, headers=headers)

res_url = response1.json()['data'].get("url")


# 创建二维码对象并配置参数
qr = qrcode.QRCode(
   version=1, # 控制二维码尺寸（1-40）
   error_correction=qrcode.constants.ERROR_CORRECT_L, # 纠错等级
   box_size=10, # 每个小方格像素大小
   border=4, # 边框厚度
)
# 添加URL数据
qr.add_data(res_url)
qr.make(fit=True)

# 生成并保存图片
img = qr.make_image(fill_color="black", back_color="white")
img.save("qrcode.png")



# 获取ticket
qs = parse_qs(urlparse(res_url).query)
ticket = qs.get("ticket", [None])[0]

# 查询二维码状态
params_QueryQrcode = {
    "app_id": "12",
    "device": f"{device_id}",
    "ticket": ticket
}

while True:
    respon2 = session.post(url_QueryQrcodeStatus, params=params_QueryQrcode, headers=headers)
    print(respon2.json())

    if respon2.json()['data']['stat'] == 'Confirmed':
        break
    time.sleep(3)




