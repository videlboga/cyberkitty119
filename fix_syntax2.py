import re

for filename in ['transkribator_modules/bot/payments.py', 'transkribator_modules/bot/yukassa_webhook.py', 'transkribator_modules/bot/callbacks.py']:
    try:
        with open(filename, 'r') as f:
            text = f.read()

        # Fix specific matches that were missed
        text = re.sub(r'import httpx\ntry: pass\nfinally: pass', 'import httpx\n        try:\n            pass\n        except Exception:\n            pass', text)
        text = re.sub(r'try: pass\nfinally: pass', '        try:\n            pass\n        except Exception:\n            pass', text)

        with open(filename, 'w') as f:
            f.write(text)
        print(f"Fixed {filename}")
    except FileNotFoundError:
        pass
