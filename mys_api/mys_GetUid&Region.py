import requests
import json

url = "https://api-takumi.miyoushe.com/binding/api/getUserGameRolesByStoken"

headers = {
  'User-Agent': "okhttp/4.9.3",
  'Connection': "Keep-Alive",
  'Accept-Encoding': "gzip",
  'DS': "1774262045,57dbff,0724985c2844a2bd9248dc87cc5d1830",
  'x-rpc-client_type': "2",
  'x-rpc-app_version': "2.102.1",
  'x-rpc-sys_version': "12",
  'x-rpc-channel': "miyousheluodi",
  'x-rpc-device_id': "78083f6d-2360-31ed-ad9d-70be3877c64b",
  'x-rpc-device_fp': "38d816a694e81",
  'x-rpc-device_name': "Redmi 23117RK66C",
  'x-rpc-device_model': "23117RK66C",
  'x-rpc-h265_supported': "1",
  'Referer': "https://app.mihoyo.com",
  'x-rpc-verify_key': "bll8iq97cem8",
  'x-rpc-csm_source': "myself",
  'Cookie': "stuid=82463740;stoken=v2_oEmHop7v3-wEUbgdmQZqG9lHT4bXRH0vFoReMqu1nY5zGL_6gOGWlaCf7udFM1xTqd6H5z8JVMCdsORRxK6IAbyd4rqlpGoRmgXi-wsnHVAvFQ15kMg2vtk=.CAE=;mid=0yjtygxmpo_mhy;"
}

response = requests.get(url, headers=headers)


RolesByStoken = json.dumps(response.json(),ensure_ascii=False)

with open("RolesByStoken_data.json", "w",encoding='utf-8') as f:
  f.write(RolesByStoken)