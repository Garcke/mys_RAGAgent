import requests
import time


url = "https://public-data-api.mihoyo.com/device-fp/api/getFp"

params = {
    "device_id": "78083f6d-2360-31ed-ad9d-70be3877c64b",
    "seed_id": "20c610421af1d8bd",
    "seed_time": f"{time.time()}",
    "platform": "5",
    "device_fp": "38d7eeb3cb5e7",
    "app_name": "account_cn",
    "ext_fields": '{"userAgent":"Mozilla/5.0 (Linux; Android 12; 23117RK66C Build/TKQ1.220829.002; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/113.0.5672.76 Mobile Safari/537.36 miHoYoBBS/2.102.1","browserScreenSize":343089,"maxTouchPoints":5,"isTouchSupported":true,"browserLanguage":"zh-CN","browserPlat":"Linux aarch64","browserTimeZone":"Asia/Shanghai","webGlRender":"Adreno (TM) 642","webGlVendor":"Qualcomm","numOfPlugins":0,"listOfPlugins":"unknown","screenRatio":2.75,"deviceMemory":"8","hardwareConcurrency":"8","cpuClass":"unknown","ifNotTrack":"unknown","ifAdBlock":0,"hasLiedResolution":1,"hasLiedOs":0,"hasLiedBrowser":0}',
}

response = requests.post(url, params=params).json()
device_fp = response['data']['device_fp']
print(device_fp)