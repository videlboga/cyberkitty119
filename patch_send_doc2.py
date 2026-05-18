import re
with open("max_bot/native_handlers.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace(
    'api.send_document(chat_id, bio, f"{normalized_title}.txt", caption=caption.replace("Бот: https://max.ru/id632523990270_bot", "[Бот](https://max.ru/id632523990270_bot)"), parse_mode="Markdown")',
    'api.send_document(chat_id, bio, f"{normalized_title}.txt", caption="Транскрипция готова")'
)

with open("max_bot/native_handlers.py", "w", encoding="utf-8") as f:
    f.write(content)
