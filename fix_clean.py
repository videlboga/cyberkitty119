import re
for f in ['transkribator_modules/bot/payments.py', 'transkribator_modules/bot/yukassa_webhook.py']:
    with open(f, 'r') as file:
        content = file.read()
    content = content.replace('db = SessionLocal()', 'pass #db = SessionLocal()')
    content = content.replace('session = SessionLocal()', 'pass #session = SessionLocal()')
    with open(f, 'w') as file:
        file.write(content)
