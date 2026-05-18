import re

with open("max_bot/native_handlers.py", "r", encoding="utf-8") as f:
    text = f.read()

# patch _deliver_result_max calls to send_document
text = text.replace('api.send_document(chat_id, bio, f"{normalized_title}.txt", caption=caption)',
'api.send_document(chat_id, bio, f"{normalized_title}.txt", caption=caption.replace("Бот: https://max.ru/id632523990270_bot", "[Бот](https://max.ru/id632523990270_bot)"), parse_mode="Markdown")')

text = text.replace('api.send_document(chat_id, bio, f"{Path(filename).stem}_transcript.txt", caption="🐱 CyberKitty119 Транскрибатор | Транскрипция\\nБот: https://max.ru/id632523990270_bot")',
'api.send_document(chat_id, bio, f"{Path(filename).stem}_transcript.txt", caption="🐱 CyberKitty119 Транскрибатор | Транскрипция\\n[Бот](https://max.ru/id632523990270_bot)", parse_mode="Markdown")')

with open("max_bot/native_handlers.py", "w", encoding="utf-8") as f:
    f.write(text)

print("Patched native_handlers.py")
