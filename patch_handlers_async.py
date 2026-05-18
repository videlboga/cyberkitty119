import re

with open("max_bot/native_handlers.py", "r") as f:
    text = f.read()

# Add import asyncio if not present
if "import asyncio" not in text:
    text = "import asyncio\n" + text

text = text.replace("if not extract_audio_from_video(dest, audio_path):", "if not asyncio.run(extract_audio_from_video(dest, audio_path)):")
text = text.replace("compressed = compress_audio_for_api(audio_path)", "compressed = asyncio.run(compress_audio_for_api(audio_path))")
text = text.replace("compressed = compress_audio_for_api(dest)", "compressed = asyncio.run(compress_audio_for_api(dest))")

with open("max_bot/native_handlers.py", "w") as f:
    f.write(text)

print("patched native_handlers.py")
