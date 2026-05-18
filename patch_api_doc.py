import re
with open("max_bot/api_client.py", "r", encoding="utf-8") as f:
    content = f.read()

# I will log the exact json payload being sent
content = content.replace(
    'r3 = self.session.post(msg_url, params={"chat_id": str(chat_id).strip()}, json=json_body, timeout=60)',
    'logger.info(f"Sending MSG document payload: {json_body}"); r3 = self.session.post(msg_url, params={"chat_id": str(chat_id).strip()}, json=json_body, timeout=60)'
)
with open("max_bot/api_client.py", "w", encoding="utf-8") as f:
    f.write(content)
