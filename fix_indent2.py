from pathlib import Path
lines = Path('max_bot/native_handlers.py').read_text().splitlines()
lines[439] = "            _ACTIVE_MAX_QA_SESSIONS.pop(event.user.id, None)"
Path('max_bot/native_handlers.py').write_text('\n'.join(lines) + '\n')
