import re
with open("max_bot/native_handlers.py", "r", encoding="utf-8") as f:
    content = f.read()

# Make sure we don't send *any* caption for the document, in case that's the trigger for max API remote disconnects, and let's send a separate message for everything except the document purely.

# Instead of patching with logic, let's just make it exactly what works for the transcript
with open("max_bot/native_handlers.py", "w", encoding="utf-8") as f:
    f.write(content.replace(
        'api.send_document(chat_id, bio, f"{normalized_title}.txt", caption="Транскрипция готова")',
        'api.send_document(chat_id, bio, f"{normalized_title}.txt")\n            api.send_message(chat_id, caption)\n            if reply_markup:\n                api.send_message(chat_id, "Действия по заметке:", reply_markup=reply_markup)'
    ))
