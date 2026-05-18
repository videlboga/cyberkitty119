import requests
import json
import time

token = "f9LHodD0cOIazRdjSjn-sR8uuDHBo2QgSd-4B5YschVf38u0XKdAIAedZQoGMeMOKfUFOAvcnShzhjvU4kas"
headers = {"Authorization": f"{token}"}
base_url = "https://platform-api.max.ru"

r1 = requests.post(f"{base_url}/uploads?type=file", headers=headers)
url = r1.json()["url"]

files = {"file": ("test.txt", b"Hello MAX uploaded file with 'file' key")}
r2 = requests.post(url, headers=headers, files=files)
print("With 'file':", r2.status_code, r2.text)

r1 = requests.post(f"{base_url}/uploads?type=file", headers=headers)
url = r1.json()["url"]
files = {"data": ("test.txt", b"Hello MAX uploaded file with 'data' key")}
r2 = requests.post(url, headers=headers, files=files)
print("With 'data':", r2.status_code, r2.text)

