import re

with open("max_bot/api_client.py", "r") as f:
    content = f.read()

repl_payload = """        last_resp = None
        for payload in attempts:
            if formatted_markup is not None:
                if isinstance(formatted_markup, dict) and "inline_keyboard" in formatted_markup:
                    buttons = []
                    for row in formatted_markup.get("inline_keyboard", []):
                        new_row = []
                        for btn in row:
                            new_row.append({
                                "text": btn.get("text", ""),
                                "type": "callback",
                                "payload": btn.get("callback_data") or btn.get("payload") or btn.get("callbackData") or "btn"
                            })
                        buttons.append(new_row)
                    payload["attachments"] = [
                        {
                            "type": "inline_keyboard",
                            "payload": {
                                "buttons": buttons
                            }
                        }
                    ]
                else:
                    payload["reply_markup"] = formatted_markup
            try:"""

content = re.sub(
    r'        last_resp = None\n        for payload in attempts:\n            if formatted_markup is not None:\n                payload\["reply_markup"\] = formatted_markup\n                if isinstance\(formatted_markup, dict\) and "inline_keyboard" in formatted_markup:\n                    payload\["inline_keyboard"\] = formatted_markup\["inline_keyboard"\]\n            \n            try:',
    repl_payload,
    content
)

with open("max_bot/api_client.py", "w") as f:
    f.write(content)
