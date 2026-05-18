import re

with open("max_bot/native_service.py", "r") as f:
    content = f.read()

repl_callback = """    # callback_data
    callback_data = None
    cb = upd.get("callback_query") or upd.get("callback")
    if isinstance(cb, dict):
        callback_data = cb.get("data") or cb.get("payload")
    elif upd.get("type") == "callback_query":
        callback_data = upd.get("data") or upd.get("payload")
    else:
        pd = upd.get("callbackData") or upd.get("data") or upd.get("payload")
        if isinstance(pd, str):
            callback_data = pd
        elif isinstance(msg, dict):"""

content = re.sub(
    r'    # callback_data\n    callback_data = None\n    cb = upd\.get\("callback_query"\)\n    if isinstance\(cb, dict\):\n        callback_data = cb\.get\("data"\)\n    elif upd\.get\("type"\) == "callback_query":\n        callback_data = upd\.get\("data"\)\n    else:\n        pd = upd\.get\("callbackData"\) or upd\.get\("data"\)\n        if isinstance\(pd, str\):\n            callback_data = pd\n        elif isinstance\(msg, dict\):',
    repl_callback,
    content
)

with open("max_bot/native_service.py", "w") as f:
    f.write(content)
