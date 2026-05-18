from pathlib import Path
lines = Path('max_bot/native_handlers.py').read_text().splitlines()
for i, line in enumerate(lines):
    if "_ACTIVE_MAX_QA_SESSIONS.pop(event.user.id, None)" in line and "return" in lines[i+1]:
        lines[i] = "            _ACTIVE_MAX_QA_SESSIONS.pop(event.user.id, None)"
Path('max_bot/native_handlers.py').write_text('\n'.join(lines) + '\n')
