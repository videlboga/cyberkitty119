import re
with open("max_bot/native_handlers.py", "r", encoding="utf-8") as f:
    content = f.read()

# I want to find the line: api.send_document(...) with reply_markup=reply_markup
# and change it to send the document, then send a message with the keyboard.
content = content.replace('api.send_document(chat_id, bio, f"{normalized_title}.txt", caption=caption.replace("Бот: https://max.ru/id632523990270_bot", "[Бот](https://max.ru/id632523990270_bot)"), parse_mode="Markdown", reply_markup=reply_markup)',
'api.send_document(chat_id, bio, f"{normalized_title}.txt", caption=caption.replace("Бот: https://max.ru/id632523990270_bot", "[Бот](https://max.ru/id632523990270_bot)"), parse_mode="Markdown")\n            api.send_message(chat_id, "Действия:", reply_markup=reply_markup)')

with open("max_bot/native_handlers.py", "w", encoding="utf-8") as f:
    f.write(content)
