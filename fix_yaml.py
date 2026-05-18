import sys

def process(file_path):
    with open(file_path, "r") as f:
        lines = f.readlines()

    out_lines = []
    found_bot_api = False
    for line in lines:
        if line.strip().startswith("telegram-bot-api:"):
            found_bot_api = True
            out_lines.append("services:\n")
        
        if found_bot_api:
            # Also replace any lingering occurrences just attached to volume arrays
            # Since my fix script ran before, the var/lib/telegram-bot-api-vpn might still be there for worker/bot?
            out_lines.append(line)

    with open(file_path, "w") as f:
        f.writelines(out_lines)
    print("Fixed yaml structure")

if __name__ == "__main__":
    process("docker-compose.bot-v2.yml")
