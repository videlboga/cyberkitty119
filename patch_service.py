from pathlib import Path

content = Path('max_bot/native_service.py').read_text()

# We need to insert this fix around line 105 where the user sender is determined.
old_user_logic = '''    # user
    sender = None
    if isinstance(msg, dict):
        sender = msg.get("sender") or msg.get("from") or msg.get("user")
    if sender is None:
        sender = upd.get("sender") or upd.get("from") or {}'''

new_user_logic = '''    # user
    sender = None
    # For callbacks, the sender is often the user inside the callback dict
    cb = upd.get("callback_query") or upd.get("callback")
    if isinstance(cb, dict):
        sender = cb.get("from") or cb.get("user")
        
    if sender is None and isinstance(msg, dict):
        sender = msg.get("sender") or msg.get("from") or msg.get("user")
        
    if sender is None:
        sender = upd.get("sender") or upd.get("from") or {}'''

content = content.replace(old_user_logic, new_user_logic)

# Also fix the callback data logic:
old_cb_logic = '''    callback_data = None
    cb = upd.get("callback_query") or upd.get("callback")
    if isinstance(cb, dict):
        callback_data = cb.get("data") or cb.get("payload")'''

new_cb_logic = '''    callback_data = None
    cb = upd.get("callback_query") or upd.get("callback")
    if isinstance(cb, dict):
        callback_data = cb.get("data") or cb.get("payload") or cb.get("callback_data")'''

content = content.replace(old_cb_logic, new_cb_logic)

Path('max_bot/native_service.py').write_text(content)
