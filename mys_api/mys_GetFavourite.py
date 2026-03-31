import requests
import json

url = "https://bbs-api.miyoushe.com/painter/api/userFavouritePostList"

params = {
  'aid': "82463740",
  'offset': "",
  'size': "20",
  'game_region': "cn_gf01",
  'game_uid': "116084021"
}

headers = {
  'User-Agent': "okhttp/4.9.3",
  'Accept-Encoding': "gzip",
  'ds': "1773040266,ooblgj,4b85619146e238b5a66e9003e48d204a",
  'x-rpc-client_type': "2",
  'x-rpc-app_version': "2.102.1",
  'x-rpc-sys_version': "12",
  'x-rpc-channel': "miyousheluodi",
  'x-rpc-device_id': "78083f6d-2360-31ed-ad9d-70be3877c64b",
  'x-rpc-device_fp': "38d816a694e81",
  'x-rpc-device_name': "Redmi 23117RK66C",
  'x-rpc-device_model': "23117RK66C",
  'x-rpc-h265_supported': "1",
  'referer': "https://app.mihoyo.com",
  'x-rpc-verify_key': "bll8iq97cem8",
  'x-rpc-csm_source': "myself",
  'Cookie': "stuid=82463740;stoken=v2_kAkSdWa9AKhaG2jz5qgKjlUTGISgb8ZUhZTHyfFT3-uZaukEp-Y-gKPBTFvUxo2FW_HFPbNOMHKCr_EOOM5EiH9Hjs3II2NTStEwgGtPkoLypcFtFgvQdVU=.CAE=;mid=0yjtygxmpo_mhy;"
}

response = requests.get(url, params=params, headers=headers)

userFavourite = json.dumps(response.json(),ensure_ascii=False)

with open("userFavourite_data.json", "w",encoding='utf-8') as f:
  f.write(userFavourite)


