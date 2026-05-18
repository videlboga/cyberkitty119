with open("max_bot/native_handlers.py", "r", encoding="utf-8") as f:
    text = f.read()

import re
replacement = """            api.send_document(chat_id, bio, f"{normalized_title}.txt")
            api.send_message(chat_id, caption)
            if reply_markup:
                api.send_message(chat_id, "Действия по заметке:", reply_markup=reply_markup)
            try:"""

text = re.sub(
r'            api\.send_document\(chat_id, bio, f"\{normalized_title\}\.txt"\).*?try:',
replacement,
text,
flags=re.DOTALL
)

with open("max_bot/native_handlers.py", "w", encoding="utf-8") as f:
    f.write(text)
