with open("max_bot/native_handlers.py", "r", encoding="utf-8") as f:
    text = f.read()

import re
# Ensure no caption and pure text and markup sent separately
replacement = """            api.send_document(chat_id, bio, f"{normalized_title}.txt", caption=caption)
            try:
                api.send_message(chat_id, "Действия по заметке:", reply_markup=reply_markup)
            except Exception:
                pass"""

text = re.sub(
r'            api\.send_document\(chat_id, bio, f"\{normalized_title\}\.txt"\).*?except Exception:\s*pass',
replacement,
text,
flags=re.DOTALL
)

with open("max_bot/native_handlers.py", "w", encoding="utf-8") as f:
    f.write(text)
