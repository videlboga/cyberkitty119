import re
with open("transkribator_modules/bot/commands.py") as f:
    text = f.read()

s1 = text.split("def personal_cabinet_command")[1]
print(s1[:500])
