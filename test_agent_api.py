import requests

telegram_id = 99999999

# Let's create a note first so it can be active
from urllib.parse import urlencode

# Mock a note creation by invoking the endpoint or we just set active note to 1.
r = requests.post("http://bot-v2-core-api:8000/api/v1/agent/active_note", json={
    "telegram_id": telegram_id,
    "note_id": 1,
    "local_artifact": False
})
print("Set Active:", r.status_code, r.text)

r = requests.post(
    "http://bot-v2-core-api:8000/api/v1/agent/chat",
    json={
        "telegram_id": telegram_id,
        "text": "What is in my note?",
    }
)
print("Chat status:", r.status_code)
print("Chat body:", r.text)

