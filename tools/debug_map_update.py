import json
from pathlib import Path

from max_bot.poller import map_update_to_event

DATA = Path("data/max_forward_examples.log")

if not DATA.exists():
    print("data/max_forward_examples.log not found")
    raise SystemExit(1)

text = DATA.read_text(encoding="utf-8")
# file contains multiple python-like repr blocks; try to extract JSON-like dicts
# We'll attempt to find lines starting with '{' and parse balanced braces

blocks = []
start = None
level = 0
for i, ch in enumerate(text):
    if ch == '{':
        if start is None:
            start = i
        level += 1
    elif ch == '}':
        level -= 1
        if level == 0 and start is not None:
            block = text[start:i+1]
            blocks.append(block)
            start = None

print(f"Found {len(blocks)} candidate blocks")

for idx, blk in enumerate(blocks[:10]):
    # try to convert single quotes to double quotes safely for JSON
    s = blk.replace("'", '"')
    try:
        obj = json.loads(s)
    except Exception:
        # fallback: use eval in controlled namespace
        try:
            obj = eval(blk, {})
        except Exception as e:
            print(idx, "failed to parse block:", e)
            continue
    ev = map_update_to_event(obj)
    print(f"--- Block {idx} -> event:")
    print(json.dumps({k: ev[k] for k in ("chat_id", "file_url", "file_id", "text")}, ensure_ascii=False, indent=2))

print("done")
