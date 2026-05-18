import re

with open('transkribator_modules/bot/callbacks.py', 'r') as f:
    text = f.read()

if 'CABINET_SUPPRESS_INLINE_FLAG' not in text:
    text = 'CABINET_SUPPRESS_INLINE_FLAG = "_suppress_cabinet_inline"\n' + text

if 'CABINET_REPLY_MARKUP_KEY' not in text:
    text = 'CABINET_REPLY_MARKUP_KEY = "_cabinet_reply_markup"\n' + text

with open('transkribator_modules/bot/callbacks.py', 'w') as f:
    f.write(text)
