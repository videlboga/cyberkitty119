import requests
import json
import time

token = "f9LHodD0cOIazRdjSjn-sR8uuDHBo2QgSd-4B5YschVf38u0XKdAIAedZQoGMeMOKfUFOAvcnShzhjvU4kas"
headers = {"Authorization": f"{token}"}
base_url = "https://platform-api.max.ru"

print("1. Requesting upload url...")
r1 = requests.post(f"{base_url}/uploads?type=file", headers=headers)
print(r1.status_code, r1.text)
url_data = r1.json()
upload_url = url_data.get("url")
print("Upload URL:", upload_url)

print("2. Uploading file...")
files = {"data": ("test.txt", b"Hello MAX uploaded file")}
r2 = requests.post(upload_url, headers=headers, files=files)
print(r2.status_code, r2.text)
file_data = r2.json()

token_or_payload = file_data.get("token") or file_data

print("3. Sending message")
msg_data = {
    "chat_id": 233211983,
    "text": "Here is the file attachment",
    "attachments": [
        {
            "type": "file",
            "payload": token_or_payload
        }
    ]
}
r3 = requests.post(f"{base_url}/messages", headers=headers, json=msg_data)
print(r3.status_code, r3.text)

