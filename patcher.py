import re
with open("max_bot/native_service.py", "r") as f:
    text = f.read()

pattern = r'if text_path and __import__\("os"\)\.path\.exists\(text_path\):[\s\S]*?api\.send_document[^\n]+\n'

replacement = """transcript_text = result.get("final_transcript") or result.get("raw_transcript")
                                if transcript_text:
                                    import tempfile
                                    import os
                                    fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix=f"transcription_{job.id}_")
                                    with os.fdopen(fd, 'w', encoding='utf-8') as f:
                                        f.write(transcript_text)
                                    with open(tmp_path, "rb") as f:
                                        api.send_document(chat_id, f, f"transcription_{job.id}.txt", caption="📄 Транскрипция готова.")
                                    try:
                                        os.unlink(tmp_path)
                                    except Exception:
                                        pass
"""

new_text = re.sub(pattern, replacement, text)
if new_text == text:
    print("FAILED")
else:
    with open("max_bot/native_service.py", "w") as f:
        f.write(new_text)
    print("SUCCESS")
