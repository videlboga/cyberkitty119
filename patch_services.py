import re

with open("transkribator_modules/jobs/services.py", "r") as f:
    content = f.read()

def patch_file():
    pattern = r'(if USE_LOCAL_BOT_API:.*?message_text = "✅ Ваша задача обработана, текст не найден."\n)'
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        print("Not found")
        return content
    
    old_part = match.group(1)
    
    new_part = """is_max = getattr(context.job.payload, "extra", {}).get("platform") == "max"
        chat_id = getattr(context.job.payload, "extra", {}).get("chat_id")

        note_id = context.artifacts.get("note_id")
        transcript = context.artifacts.get("final_transcript")
        
        if note_id:
            message_text = "✅ Обработка завершена!"
        elif transcript:
            message_text = f"✅ Ваша расшифровка:\\n{transcript}"
            if len(message_text) > 4000:
                message_text = message_text[:3990] + "..."
        else:
            message_text = "✅ Ваша задача обработана, текст не найден."

        if is_max:
            from transkribator_modules.config import MAX_API_TOKEN, MAX_API_URL
            import requests

            max_url = f"{MAX_API_URL or 'https://platform-api.max.ru'}/messages?chat_id={chat_id or user.telegram_id}"
            try:
                r = requests.post(
                    max_url,
                    json={"text": message_text},
                    headers={"Authorization": MAX_API_TOKEN or ""},
                    timeout=30.0,
                )
                r.raise_for_status()
                logger.info("MAX delivery successful via worker fallback")
                return
            except Exception as e:
                logger.error("Failed to deliver via MAX API: %s", str(e))
                return

        """ + old_part

    return content.replace(old_part, new_part)

new_content = patch_file()
with open("transkribator_modules/jobs/services.py", "w") as f:
    f.write(new_content)
print("PATCH DONE")
