import requests

BOT_TOKEN="f9LHodD0cOIazRdjSjn-sR8uuDHBo2QgSd-4B5YschVf38u0XKdAIAedZQoGMeMOKfUFOAvcnShzhjvU4kas"
base_url = f"https://platform-api.max.ru"
headers = {"Authorization": f"{BOT_TOKEN}"}
url = f"{base_url}/messages"
files = {"file": ("test.txt", b"Hello MAX API! File upload test.")}
data = {"chat_id": 233211983, "text": "This is a document."}

r = requests.post(url, headers=headers, data=data, files=files)
print(r.status_code, r.text)

