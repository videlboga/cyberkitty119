import re
with open("transkribator_modules/bot/callbacks.py", "r") as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    if line.strip() == "pass" and "except" not in lines[i-1] and "else:" not in lines[i-1]:
        # we have a rogue pass, comment it out
        if i == 543 or i == 544:
            new_lines.append("#" + line)
            continue
    new_lines.append(line)

with open("transkribator_modules/bot/callbacks.py", "w") as f:
    f.writelines(new_lines)
