for filename in ['transkribator_modules/bot/payments.py', 'transkribator_modules/bot/yukassa_webhook.py', 'transkribator_modules/bot/callbacks.py']:
    try:
        with open(filename, 'r') as f:
            text = f.read()
        
        text = text.replace('import httpx\ntry: pass\nfinally: pass', 'import httpx\n        try:\n            pass\n        except Exception:\n            pass')
        text = text.replace('try: pass\nfinally: pass', '        try:\n            pass\n        except Exception:\n            pass')
        
        with open(filename, 'w') as f:
            f.write(text)
        print(f"Fixed {filename}")
    except FileNotFoundError:
        pass
