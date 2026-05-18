import re
with open("max_bot/native_service.py", "r", encoding="utf-8") as f:
    text = f.read()

prefix = '                            keyboard = {\n                                "inline_keyboard": [\n                                    [{"text": " Задать вопросы"'
new_prefix = '                            keyboard = {\n                                "inline_keyboard": [\n                                    [{"text": "🔎 Задать вопросы"'
text = text.replace(prefix, new_prefix)

old_block = """                            try:
                                transcript_text = result.get("final_transcript") or result.get("raw_transcript")
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
                                api.send_message(chat_id, result_message, reply_markup=keyboard)
                            except Exception as e:
                                logger.error(f"Failed to send result to max for job {job.id}: {e}")"""

new_block = """                            try:
                                api.send_message(chat_id, result_message, reply_markup=keyboard)
                            except Exception as e:
                                logger.error(f"Failed to send result to max for job {job.id}: {e}")"""

text = text.replace(old_block, new_block)

with open("max_bot/native_service.py", "w", encoding="utf-8") as f:
    f.write(text)
