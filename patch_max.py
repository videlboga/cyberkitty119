with open("max_bot/api_client.py", "r") as f:
    text = f.read()

old_block = """            # Since MAX API can take a moment to process the file, we add retries
            for attempt in range(5):
                try:
                    r3 = self.session.post(msg_url, params={"chat_id": str(chat_id).strip()}, json=json_body, timeout=60)
                    if r3.status_code == 400 and "attachment.not.ready" in r3.text:
                        logger.info("Attachment not ready, waiting 1s (attempt %d/5)", attempt + 1)
                        time.sleep(1)
                        continue
                    r3.raise_for_status()
                    return r3.json()
                except requests.exceptions.ReadTimeout as e:
                    logger.warning("send_document step 3 read timeout (attempt %d/5): %s", attempt + 1, e)"""

new_block = """            # Since MAX API can take a moment to process the file, we add retries
            for attempt in range(5):
                try:
                    r3 = self.session.post(msg_url, params={"chat_id": str(chat_id).strip()}, json=json_body, timeout=60)
                    if r3.status_code == 400 and "attachment.not.ready" in r3.text:
                        logger.info("Attachment not ready, waiting 1s (attempt %d/5)", attempt + 1)
                        time.sleep(1)
                        continue
                    if r3.status_code == 400:
                        logger.error(f"HTTP 400 payload {json_body} resp {r3.text}")
                    r3.raise_for_status()
                    return r3.json()
                except requests.exceptions.ReadTimeout as e:
                    logger.warning("send_document step 3 read timeout (attempt %d/5): %s", attempt + 1, e)"""

if old_block in text:
    with open("max_bot/api_client.py", "w") as f:
        f.write(text.replace(old_block, new_block))
    print("Patched successfully")
else:
    print("Could not find block. Trying fallback.")
    old_block_2 = """                    if r3.status_code == 400 and "attachment.not.ready" in r3.text:
                        logger.info("Attachment not ready, waiting 1s (attempt %d/5)", attempt + 1)
                        time.sleep(1)
                        continue
                    r3.raise_for_status()
                    return r3.json()"""
    new_block_2 = """                    if r3.status_code == 400 and "attachment.not.ready" in r3.text:
                        logger.info("Attachment not ready, waiting 1s (attempt %d/5)", attempt + 1)
                        time.sleep(1)
                        continue
                    if r3.status_code == 400:
                        logger.error(f"HTTP 400 payload {json_body} resp {r3.text}")
                    r3.raise_for_status()
                    return r3.json()"""
    
    if old_block_2 in text:
        with open("max_bot/api_client.py", "w") as f:
            f.write(text.replace(old_block_2, new_block_2))
        print("Patched successfully with fallback")
    else:
        print("Could not find fallback block either. Here is the file contents surrounding raise_for_status:")
        lines = text.split('\n')
        for i, l in enumerate(lines):
            if "r3.raise_for_status()" in l:
                print("\n".join(lines[i-5:i+5]))
