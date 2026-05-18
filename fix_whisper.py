import sys

def process(file_path):
    with open(file_path, "r") as f:
        data = f.read()

    data = data.replace('or "openai/whisper-large-v3-turbo"', 'or "openai/whisper-large-v3"')

    with open(file_path, "w") as f:
        f.write(data)
    print("Done replace whisper turbo")

if __name__ == "__main__":
    process("transcribe_client/openrouter.py")
