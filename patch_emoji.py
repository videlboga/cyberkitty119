with open("max_bot/native_service.py", "r", encoding="utf-8") as f:
    t = f.read()

t = t.replace(' Задать вопросы', '🔎 Задать вопросы')

with open("max_bot/native_service.py", "w", encoding="utf-8") as f:
    f.write(t)
