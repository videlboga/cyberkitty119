import sys

def process(file_path):
    with open(file_path, "r") as f:
        data = f.read()

    data = data.replace("/var/lib/telegram-bot-api-vpn:/var/lib/telegram-bot-api", "./telegram-bot-api-data:/var/lib/telegram-bot-api")

    with open(file_path, "w") as f:
        f.write(data)
    print("Done")

if __name__ == "__main__":
    process("docker-compose.bot-v2.yml")
