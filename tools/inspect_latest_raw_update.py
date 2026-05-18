import re
import ast
from pathlib import Path

LOG = Path('logs/max_poller.log')
if not LOG.exists():
    print('log not found:', LOG)
    raise SystemExit(1)

text = LOG.read_text(encoding='utf-8')
# find last occurrence of 'poller: raw update:'
m = list(re.finditer(r"poller: raw update: (\{.*)$", text, re.M))
if not m:
    print('no raw update found')
    raise SystemExit(1)
last = m[-1].group(1)
# The log may cut or shorten; try to recover a balanced dict by finding first '{' to last '}'
start = last.find('{')
if start != -1:
    s = last[start:]
else:
    s = last
# Attempt to find a balanced JSON-like ending by scanning the file forward until braces balance
# We'll search across the remaining log chunk
remaining = text[m[-1].start(1):]
level = 0
end_idx = None
for i, ch in enumerate(remaining):
    if ch == '{':
        level += 1
    elif ch == '}':
        level -= 1
        if level == 0:
            end_idx = i
            break
if end_idx is not None:
    blk = remaining[: end_idx + 1]
else:
    blk = remaining

print('raw block (truncated 2000 chars):')
print(blk[:2000])

# Try to parse with ast.literal_eval after replacing 'null'/'true'/'false' if any
blk_fixed = blk.replace('null', 'None').replace('true', 'True').replace('false', 'False')
try:
    obj = ast.literal_eval(blk_fixed)
except Exception as e:
    print('ast parse failed:', e)
    # fallback to eval in limited namespace
    try:
        obj = eval(blk_fixed, {})
    except Exception as e2:
        print('eval failed:', e2)
        raise SystemExit(1)

from max_bot.poller import map_update_to_event

print('\nMapping result:')
print(map_update_to_event(obj))

# Inspect likely paths
msg = obj.get('message') if isinstance(obj.get('message'), dict) else None
print('\nmessage present:', bool(msg))
if msg:
    print('message keys:', list(msg.keys()))
    if 'link' in msg and isinstance(msg.get('link'), dict):
        print('link keys:', list(msg.get('link').keys()))
        lm = msg.get('link').get('message') if isinstance(msg.get('link').get('message'), dict) else None
        print('link.message present:', bool(lm))
        if lm:
            print('link.message keys:', list(lm.keys()))
            att = lm.get('attachments') or lm.get('files') or lm.get('documents')
            print('link.message attachments type:', type(att), 'len=', len(att) if isinstance(att, list) else 'n/a')
            if isinstance(att, list) and att:
                for a in att:
                    print(' - attachment keys:', list(a.keys()) if isinstance(a, dict) else type(a))
                    if isinstance(a, dict):
                        p = a.get('payload') if isinstance(a.get('payload'), dict) else a
                        print('   payload keys:', list(p.keys()) if isinstance(p, dict) else type(p))
                        if isinstance(p, dict):
                            for k in ('url','file_url','download_url','content_url'):
                                if p.get(k):
                                    print('   found url in payload key', k, '->', p.get(k)[:200])
    # body attachments
    body = msg.get('body') if isinstance(msg.get('body'), dict) else None
    print('\nbody present:', bool(body))
    if body:
        print('body keys:', list(body.keys()))
        batt = body.get('attachments') or body.get('files') or body.get('documents')
        print('body attachments type:', type(batt), 'len=', len(batt) if isinstance(batt, list) else 'n/a')
        if isinstance(batt, list) and batt:
            for a in batt:
                print(' - body attachment keys:', list(a.keys()) if isinstance(a, dict) else type(a))
                if isinstance(a, dict):
                    p = a.get('payload') if isinstance(a.get('payload'), dict) else a
                    if isinstance(p, dict):
                        for k in ('url','file_url','download_url','content_url'):
                            if p.get(k):
                                print('   found url in body payload key', k, '->', p.get(k)[:200])

print('\nDone')
