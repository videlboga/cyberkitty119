from pathlib import Path
txt = Path('max_bot/native_handlers.py').read_text()
txt = txt.replace('_ACTIVE_MAX_SEARCH_USERS.discard(event.user.id)\\n        logger.info("native_handlers: received callback_data=%s user=%s"', '_ACTIVE_MAX_SEARCH_USERS.discard(event.user.id)\n        logger.info("native_handlers: received callback_data=%s user=%s"')
Path('max_bot/native_handlers.py').write_text(txt)
