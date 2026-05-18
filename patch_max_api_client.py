import re

with open("max_bot/api_client.py", "r", encoding="utf-8") as f:
    text = f.read()

# patch send_message signature
text = re.sub(r'def send_message\(self, chat_id: str, text: str, reply_markup: Optional\[Any\] = None\) -> dict:', 'def send_message(self, chat_id: str, text: str, reply_markup: Optional[Any] = None, parse_mode: Optional[str] = None) -> dict:', text)

# add to _post inside send_message
text = text.replace('json_body["reply_markup"] = formatted_markup\n            \n            try:\n                logger.info("send_message POST url=%s params=%s json=%s", url, params, json_body)',
'json_body["reply_markup"] = formatted_markup\n            if parse_mode and parse_mode.lower() == "markdown":\n                json_body["format"] = "markdown"\n            \n            try:\n                logger.info("send_message POST url=%s params=%s json=%s", url, params, json_body)')

# add to attempts inside send_message
text = text.replace('for payload in attempts:\n            if formatted_markup is not None:',
'for payload in attempts:\n            if parse_mode and parse_mode.lower() == "markdown":\n                payload["format"] = "markdown"\n            if formatted_markup is not None:')

# patch edit_message signature
text = re.sub(r'def edit_message\(self, chat_id: str, message_id: str, text: str, reply_markup: Optional\[Any\] = None\) -> dict:', 'def edit_message(self, chat_id: str, message_id: str, text: str, reply_markup: Optional[Any] = None, parse_mode: Optional[str] = None) -> dict:', text)

# add format to edit_message
text = text.replace('payload = {"text": text}\n        params = {"message_id": message_id}\n        if reply_markup is not None:',
'payload = {"text": text}\n        params = {"message_id": message_id}\n        if parse_mode and parse_mode.lower() == "markdown":\n            payload["format"] = "markdown"\n        if reply_markup is not None:')

# patch fallbacks in edit_message
text = text.replace('return self.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)',
'return self.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)')

# patch send_document signature
text = re.sub(r'def send_document\(self, chat_id: str, file_obj: BinaryIO, filename: str, caption: Optional\[str\] = None\) -> dict:', 'def send_document(self, chat_id: str, file_obj: BinaryIO, filename: str, caption: Optional[str] = None, parse_mode: Optional[str] = None) -> dict:', text)

# add format to send_document
text = text.replace('            json_body = {\n                "text": text,\n                "attachments": [\n                    {\n                        "type": "file",\n                        "payload": payload_dict\n                    }\n                ]\n            }\n            \n            # Since MAX API can take a moment to process the file, we add retries',
'            json_body = {\n                "text": text,\n                "attachments": [\n                    {\n                        "type": "file",\n                        "payload": payload_dict\n                    }\n                ]\n            }\n            if parse_mode and parse_mode.lower() == "markdown":\n                json_body["format"] = "markdown"\n            \n            # Since MAX API can take a moment to process the file, we add retries')

with open("max_bot/api_client.py", "w", encoding="utf-8") as f:
    f.write(text)

print("Patched api_client.py")
