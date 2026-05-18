import re

with open("max_bot/api_client.py", "r") as f:
    text = f.read()

pattern = r'def download_url_to_file\(self, url: str, destination_path: str, expected_size_bytes: Optional\[int\] = None\) -> bool:[\s\S]*?return True\n            except requests\.exceptions\.RequestException as e:'

new_code = """def download_url_to_file(self, url: str, destination_path: str, expected_size_bytes: Optional[int] = None, progress_callback=None) -> bool:
        \"\"\"Download a file by URL to destination_path (streaming).\"\"\"
        retries = 3
        for attempt in range(1, retries + 1):
            try:
                r = self.session.get(url, stream=True, timeout=60)
                if not r.ok:
                    logger.error("download failed: %s %s", r.status_code, r.text)
                    return False
                total = 0
                with open(destination_path, "wb") as fh:
                    for chunk in r.iter_content(65536):
                        if not chunk:
                            continue
                        fh.write(chunk)
                        total += len(chunk)
                        if progress_callback:
                            progress_callback(total, expected_size_bytes)
                if expected_size_bytes and total != expected_size_bytes:
                    logger.warning("downloaded size mismatch: got=%s expected=%s", total, expected_size_bytes)
                return True
            except requests.exceptions.RequestException as e:"""

new_text = re.sub(pattern, new_code, text)

if new_text == text:
    print("FAILED")
else:
    with open("max_bot/api_client.py", "w") as f:
        f.write(new_text)
    print("SUCCESS")
