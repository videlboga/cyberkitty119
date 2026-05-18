import re
with open("max_bot/native_handlers.py", "r", encoding="utf-8") as f:
    text = f.read()

old_cap = 'caption = _build_note_delivery_caption(note, normalized_title)'
new_cap = 'caption = "🐱 CyberKitty119 Транскрибатор"'
old_cap2 = 'caption="Транскрипция"'
new_cap2 = 'caption="🐱 CyberKitty119 Транскрибатор | Транскрипция"'

text = text.replace(old_cap, new_cap)
text = text.replace(old_cap2, new_cap2)

with open("max_bot/native_handlers.py", "w", encoding="utf-8") as f:
    f.write(text)
