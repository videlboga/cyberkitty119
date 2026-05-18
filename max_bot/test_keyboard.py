
import os, requests
token = os.getenv("MAX_BOT_TOKEN")
url = "https://platform-api.max.ru/messages"
headers = {"Authorization": token, "Content-Type": "application/json"}
body = {
    "user_id": 632523955681, 
    "text": "test regular keyboard", 
    "attachments": [
        {
            "type": "keyboard", 
            "payload": {
                "buttons": [
                    [
                        {"type": "message", "text": "Test regular button"}
                    ]
                ]
            }
        }
    ]
}
r = requests.post(url, headers=headers, json=body)
print(r.status_code, r.text)
