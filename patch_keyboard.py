import re

with open("max_bot/api_client.py", "r") as f:
    content = f.read()

repl_post = """        # Helper to perform a single POST and handle rate limit/errors
        def _post(params: dict, json_body: dict):
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
                    json_body["attachments"] = [
                        {
                            "type": "inline_keyboard",
                            "payload": {
                                "buttons": buttons
                            }
                        }
                    ]
                else:
                    json_body["reply_markup"] = formatted_markup
            
            try:"""

content = re.sub(
    r'        # Helper to perform a single POST and handle rate limit/errors\n        def _post\(params: dict, json_body: dict\):\n            if formatted_markup is not None:\n                json_body\["reply_markup"\] = formatted_markup\n                # Some API specs expect attachments or inline_keyboard specifically:\n                if isinstance\(formatted_markup, dict\) and "inline_keyboard" in formatted_markup:\n                    json_body\["inline_keyboard"\] = formatted_markup\["inline_keyboard"\]\n            \n            try:',
    repl_post,
    content
)

repl_edit = """        payload = {"text": text}
        if reply_markup is not None:
            try:
                fm = reply_markup.to_dict() if hasattr(reply_markup, 'to_dict') else reply_markup
                if isinstance(fm, dict) and "inline_keyboard" in fm:
                    buttons = []
                    for row in fm.get("inline_keyboard", []):
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
                    payload["reply_markup"] = fm
            except Exception:
                pass
                
        r = self.session.patch(url, json=payload, timeout=30)"""

content = re.sub(
    r'        payload = \{"text": text\}\n        if reply_markup is not None:\n            try:\n                fm = reply_markup\.to_dict\(\) if hasattr\(reply_markup, \'to_dict\'\) else reply_markup\n                payload\["reply_markup"\] = fm\n                if isinstance\(fm, dict\) and "inline_keyboard" in fm:\n                    payload\["inline_keyboard"\] = fm\["inline_keyboard"\]\n            except Exception:\n                pass\n                \n        r = self\.session\.patch\(url, json=payload, timeout=30\)',
    repl_edit,
    content
)

with open("max_bot/api_client.py", "w") as f:
    f.write(content)
