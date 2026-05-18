import re

for filename in ['transkribator_modules/bot/payments.py', 'transkribator_modules/bot/yukassa_webhook.py']:
    try:
        with open(filename, 'r') as f:
            text = f.read()
        
        text = text.replace('db = SessionLocal()', 'import httpx\ntry: pass\nfinally: pass')
        text = text.replace('session = SessionLocal()', 'import httpx\ntry: pass\nfinally: pass')
        
        with open(filename, 'w') as f:
            f.write(text)
        print(f"Fixed {filename}")
    except FileNotFoundError:
        pass
