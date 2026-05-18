#!/usr/bin/env python3
import os, sys, requests, traceback

if len(sys.argv) < 2:
    print('Usage: raw_deepinfra_probe.py <path-to-audio>')
    raise SystemExit(2)

file_path = sys.argv[1]
api_key = os.environ.get('DEEPINFRA_API_KEY')
if not api_key:
    print('DEEPINFRA_API_KEY not set in environment')
    raise SystemExit(2)

url = 'https://api.deepinfra.com/v1/inference/openai/whisper-large-v3-turbo'
headers = {'Authorization': f'Bearer {api_key}'}

print('Posting to', url, 'file=', file_path)
try:
    with open(file_path, 'rb') as f:
        files = {'audio': (os.path.basename(file_path), f, 'application/octet-stream')}
        resp = requests.post(url, headers=headers, files=files, timeout=60)
        print('HTTP', resp.status_code)
        try:
            print('JSON:', resp.json())
        except Exception:
            print('TEXT:', resp.text[:2000])
except Exception as e:
    print('EXCEPTION:', type(e).__name__, str(e))
    traceback.print_exc()
    raise
