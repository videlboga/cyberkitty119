from pathlib import Path
txt = Path('max_bot/native_handlers.py').read_text()
txt = txt.replace('_ACTIVE_MAX_SEARCH_USERS = set()\\n_ACTIVE_MAX_QA_SESSIONS = {}\\n', '_ACTIVE_MAX_SEARCH_USERS = set()\n_ACTIVE_MAX_QA_SESSIONS = {}\n')
Path('max_bot/native_handlers.py').write_text(txt)
