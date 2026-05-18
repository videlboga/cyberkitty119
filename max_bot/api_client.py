
"""Thin client for Max messenger API.

This is a small wrapper around HTTP API methods used by the handlers. Adjust
implementation per real Max API docs.
"""
from __future__ import annotations
import time
import requests

from typing import Optional, BinaryIO
import json
from .config import MAX_API_URL, MAX_API_TOKEN, logger


class MaxAPIError(RuntimeError):
    def __init__(self, message: str = "", status_code: Optional[int] = None, headers: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.headers = dict(headers or {})
        self.retry_after = None
        # Try to parse Retry-After header if present
        ra = self.headers.get("Retry-After") or self.headers.get("retry-after")
        if ra is not None:
            try:
                self.retry_after = int(ra)
            except Exception:
                try:
                    self.retry_after = int(float(ra))
                except Exception:
                    self.retry_after = None

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"MaxAPIError(status={self.status_code}, retry_after={self.retry_after}) {super().__str__()}"


class MaxAPI:
    def __init__(self, token: Optional[str] = None, base_url: Optional[str] = None):
        self.token = token or MAX_API_TOKEN
        self.base_url = base_url or MAX_API_URL
        self.session = requests.Session()
        if self.token:
            # Per MAX docs the Authorization header should contain the token directly
            # ("Authorization: {access_token}"). Do not include the Bearer prefix.
            self.session.headers.update({"Authorization": f"{self.token}"})
        # Try to validate token quickly and log identity (non-fatal)
        try:
            me = None
            try:
                me = self.get_me()
            except Exception as _:
                me = None
            if me:
                logger.info("MaxAPI: authenticated as: %s", me)
            else:
                logger.info("MaxAPI: get_me did not return identity (token may be invalid or /me unsupported)")
        except Exception:
            # Keep client construction non-fatal; we'll surface errors on use.
            logger.debug("MaxAPI: silent get_me check failed", exc_info=True)

    def send_message(self, chat_id: str, text: str, reply_markup: Optional[Any] = None, parse_mode: Optional[str] = None) -> dict:
        """Send a text message.

        Prefer the documented form: POST /messages?chat_id=... with JSON body {"text":...}.
        If that fails, fall back to older recipient variants we tried previously.
        """
        url = f"{self.base_url}/messages"

        # format reply markup roughly per standard standard inline keyboards 
        # (transkribator mostly passes telegram InlineKeyboardMarkup or a serializable dict)
        formatted_markup = None
        if reply_markup is not None:
            try:
                # If it's a PTB object
                if hasattr(reply_markup, 'to_dict'):
                    formatted_markup = reply_markup.to_dict()
                else:
                    formatted_markup = reply_markup
            except Exception:
                pass

        # Helper to perform a single POST and handle rate limit/errors
        def _post(params: dict, json_body: dict):
            if formatted_markup is not None:
                if isinstance(formatted_markup, dict) and "inline_keyboard" in formatted_markup:
                    buttons = []
                    for row in formatted_markup.get("inline_keyboard", []):
                        new_row = []
                        for btn in row:
                            new_row.append({
                                "text": btn.get("text", ""),
                                "type": "callback",
                                "payload": btn.get("callback_data") or btn.get("payload") or btn.get("callbackData") or "btn"
                            })
                        buttons.append(new_row)
                    json_body["attachments"] = [
                        {
                            "type": "inline_keyboard",
                            "payload": {
                                "buttons": buttons
                            }
                        }
                    ]
                else:
                    json_body["reply_markup"] = formatted_markup
            if parse_mode and parse_mode.lower() == "markdown":
                json_body["format"] = "markdown"
            
            try:
                import requests.exceptions
                logger.info("send_message POST url=%s params=%s json=%s", url, params, json_body)
                r = self.session.post(url, params=params, json=json_body, timeout=10)
            except requests.exceptions.ReadTimeout as exc:
                logger.warning("send_message read timeout, retrying: %s", exc)
                try:
                    r = self.session.post(url, params=params, json=json_body, timeout=20)
                except Exception as exc2:
                    logger.warning("send_message second attempt failed: %s", exc2)
                    return None
            except Exception as exc:
                logger.warning("send_message request error params=%s json=%s: %s", params, json_body, exc)
                return None

            if r.status_code == 429:
                logger.error("send_message 429: %s", r.text)
                raise MaxAPIError(r.text, status_code=429, headers=r.headers)

            if r.ok:
                try:
                    logger.debug("send_message response OK status=%s body=%s request=%s", r.status_code, r.text, getattr(r, 'request', None))
                    return r.json()
                except Exception:
                    return {}
            # Log non-ok response with request details to help diagnose payload/recipient issues
            try:
                req = getattr(r, 'request', None)
                req_info = None
                if req is not None:
                    req_info = {
                        'method': getattr(req, 'method', None),
                        'url': getattr(req, 'url', None),
                        'body': getattr(req, 'body', None),
                        'headers': dict(getattr(req, 'headers', {}) or {}),
                    }
                logger.info("send_message non-ok response: status=%s text=%s params=%s request=%s response_headers=%s", r.status_code, r.text, params, req_info, dict(r.headers or {}))
            except Exception:
                logger.info("send_message non-ok response: %s %s %s", r.status_code, r.text, params)
            return r

        # If caller passed a recipient-like dict, try to extract the correct id.
        # Important: for replies use the sender.user_id (the human who sent the message)
        # when available. Fallback order:
        # 1) sender.user_id
        # 2) message.recipient.chat_id (dialog id)
        # 3) message.recipient.user_id
        # 4) top-level chat_id/id/user_id on the provided dict
        resolved_id = None
        resolved_kind = None
        if isinstance(chat_id, dict):
            rec = chat_id
            raw = rec.get("_raw_update") or rec
            msg = raw.get("message") if isinstance(raw, dict) else None
            if isinstance(msg, dict):
                s = msg.get("sender") or msg.get("from") or {}
                if isinstance(s, dict):
                    sid = s.get("user_id") or s.get("id")
                    if sid:
                        resolved_id = sid
                        resolved_kind = "user_id(sender)"
                if not resolved_id:
                    r = msg.get("recipient") or msg.get("to") or {}
                    if isinstance(r, dict):
                        cid = r.get("chat_id") or r.get("id")
                        if cid:
                            resolved_id = cid
                            resolved_kind = "chat_id(recipient)"
                        else:
                            uid = r.get("user_id")
                            if uid:
                                resolved_id = uid
                                resolved_kind = "user_id(recipient)"
            # top-level fallback
            if not resolved_id:
                for key in ("chat_id", "id", "user_id"):
                    if key in rec:
                        resolved_id = rec.get(key)
                        resolved_kind = f"top.{key}"
                        break
        else:
            resolved_id = chat_id
            resolved_kind = "direct"

        # First, try the most likely query param form depending on resolved_kind.
        # If we resolved a sender.user_id, try user_id param first (works for direct messages).
        if resolved_id is not None:
            try_order = []
            try:
                if resolved_kind == "user_id(sender)":
                    try_order = [("user_id", resolved_id), ("chat_id", resolved_id)]
                elif resolved_kind == "chat_id(recipient)":
                    try_order = [("chat_id", resolved_id), ("user_id", resolved_id)]
                else:
                    try_order = [("chat_id", resolved_id), ("user_id", resolved_id)]

                for key, val in try_order:
                    params = {key: val}
                    resp = _post(params, {"text": text})
                    if resp and not isinstance(resp, requests.Response):
                        logger.info("send_message succeeded using param %s=%s (resolved_kind=%s)", key, val, resolved_kind)
                        return resp
            except MaxAPIError:
                raise
            except Exception:
                # fall through to payload fallbacks
                pass

        # Fallback: try older/alternative payload shapes in body (legacy support)
        attempts = []
        # If we resolved a recipient dict earlier, try some variants
        if isinstance(chat_id, dict):
            rec = chat_id
            raw = rec.get("_raw_update") or rec
            msg = raw.get("message") if isinstance(raw, dict) else None
            candidate_recs = []
            if isinstance(msg, dict):
                r = msg.get("recipient") or msg.get("to") or {}
                if isinstance(r, dict) and r:
                    candidate_recs.append(r)
                s = msg.get("sender") or msg.get("from") or {}
                if isinstance(s, dict) and s:
                    candidate_recs.append(s)
            if isinstance(rec, dict) and rec:
                candidate_recs.append(rec)

            for crec in candidate_recs:
                attempts.append({"recipient": crec, "text": text})
                attempts.append({"recipient": json.dumps(crec), "text": text})
                attempts.append({"to": crec, "text": text})
                attempts.append({"to": json.dumps(crec), "text": text})
                cid = crec.get("chat_id") or crec.get("id") or crec.get("user_id")
                if cid is not None:
                    attempts.append({"chat_id": cid, "text": text})
                    try:
                        attempts.append({"recipient": {"chat": {"id": int(cid)}} , "text": text})
                    except Exception:
                        pass
                    try:
                        cid_s = str(cid)
                        attempts.append({"recipient": {"id": cid_s}, "text": text})
                        attempts.append({"recipient": {"id": cid_s, "type": "dialog"}, "text": text})
                        attempts.append({"recipient": {"id": f"user:{cid_s}"}, "text": text})
                        attempts.append({"recipient": {"id": f"chat:{cid_s}"}, "text": text})
                        attempts.append({"to": f"user:{cid_s}", "text": text})
                        attempts.append({"to": f"chat:{cid_s}", "text": text})
                    except Exception:
                        pass
        else:
            attempts.append({"chat_id": resolved_id, "text": text})
            try:
                cid_int = int(resolved_id)
            except Exception:
                cid_int = None
            if cid_int is not None:
                attempts.append({"recipient": {"chat_id": cid_int}, "text": text})
                attempts.append({"recipient": {"chat_id": cid_int, "chat_type": "dialog"}, "text": text})
                attempts.append({"recipient": {"type": "user", "id": cid_int}, "text": text})
            attempts.append({"to": f"chat:{resolved_id}", "text": text})

        last_resp = None
        for payload in attempts:
            if parse_mode and parse_mode.lower() == "markdown":
                payload["format"] = "markdown"
            if formatted_markup is not None:
                payload["reply_markup"] = formatted_markup
                if isinstance(formatted_markup, dict) and "inline_keyboard" in formatted_markup:
                    payload["inline_keyboard"] = formatted_markup["inline_keyboard"]
                    
            try:
                logger.info("send_message trying payload: %s", payload)
                r = self.session.post(url, json=payload, timeout=30)
            except Exception as exc:
                logger.warning("send_message request error for payload %s: %s", payload, exc)
                last_resp = None
                continue

            if r.status_code == 429:
                logger.error("send_message 429: %s", r.text)
                raise MaxAPIError(r.text, status_code=429, headers=r.headers)

            if r.ok:
                try:
                    logger.debug("send_message response OK status=%s body=%s request=%s", r.status_code, r.text, getattr(r, 'request', None))
                    return r.json()
                except Exception:
                    return {}
            # Log more details about why payload was rejected
            try:
                req = getattr(r, 'request', None)
                req_info = None
                if req is not None:
                    req_info = {
                        'method': getattr(req, 'method', None),
                        'url': getattr(req, 'url', None),
                        'body': getattr(req, 'body', None),
                        'headers': dict(getattr(req, 'headers', {}) or {}),
                    }
                logger.info("send_message failed for payload %s: status=%s text=%s request=%s response_headers=%s", payload, r.status_code, r.text, req_info, dict(r.headers or {}))
            except Exception:
                logger.info("send_message failed for payload %s: %s %s", payload, r.status_code, r.text)
            last_resp = r

        if last_resp is not None:
            logger.error("send_message failed (all payloads): %s %s", getattr(last_resp, 'status_code', None), getattr(last_resp, 'text', None))
            raise MaxAPIError(getattr(last_resp, 'text', '') or 'send_message failed', status_code=getattr(last_resp, 'status_code', None), headers=getattr(last_resp, 'headers', None))
        raise MaxAPIError('send_message failed: no response')

    def get_me(self) -> dict:
        """Return bot identity (/me) useful for token validation."""
        url = f"{self.base_url}/me"
        r = self.session.get(url, timeout=10)
        if not r.ok:
            logger.error("get_me failed: %s %s", r.status_code, r.text)
            raise MaxAPIError(r.text, status_code=r.status_code, headers=r.headers)
        try:
            return r.json()
        except Exception:
            return {}

    def edit_message(self, chat_id: str, message_id: str, text: str, reply_markup: Optional[Any] = None, parse_mode: Optional[str] = None) -> dict:
        url = f"{self.base_url}/messages"
        payload = {"text": text}
        params = {"message_id": message_id}
        if parse_mode and parse_mode.lower() == "markdown":
            payload["format"] = "markdown"
        if reply_markup is not None:
            try:
                fm = reply_markup.to_dict() if hasattr(reply_markup, 'to_dict') else reply_markup
                if isinstance(fm, dict) and "inline_keyboard" in fm:
                    buttons = []
                    for row in fm.get("inline_keyboard", []):
                        new_row = []
                        for btn in row:
                            new_row.append({
                                "text": btn.get("text", ""),
                                "type": "callback",
                                "payload": btn.get("callback_data") or btn.get("payload") or btn.get("callbackData") or "btn"
                            })
                        buttons.append(new_row)
                    payload["attachments"] = [
                        {
                            "type": "inline_keyboard",
                            "payload": {
                                "buttons": buttons
                            }
                        }
                    ]
                else:
                    payload["reply_markup"] = fm
            except Exception:
                pass
                
        r = self.session.put(url, params=params, json=payload, timeout=30)
        
        # Max API may not support PUT /messages/<id>. Fallback to send_message
        if r.status_code == 404 and r.json().get('code') in ['method.not.found', 'route.not.found']:
            logger.warning(f"Max API does not support PUT /messages. Falling back to send_message for chat {chat_id}")
            return self.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)

        if not r.ok:
            # Fallback to send_message for method.not.found even if it's PATCH or somehow 400
            try:
                err_data = r.json()
                if err_data.get('code') == 'method.not.found':
                    logger.warning(f"Max API does not support message editing. Falling back to send_message for chat {chat_id}")
                    return self.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
            except Exception:
                pass

            logger.error("edit_message failed: %s %s", r.status_code, r.text)
            raise MaxAPIError(r.text)
        return r.json()

    def send_document(self, chat_id: str, file_obj: BinaryIO, filename: str, caption: Optional[str] = None, parse_mode: Optional[str] = None, reply_markup: Optional[dict] = None) -> dict:
        """Send a document to a chat using MAX API's /uploads and /messages endpoints."""
        url_upload = f"{self.base_url}/uploads"
        
        # 1. Get upload URL (with retries)
        upload_url = None
        import requests.exceptions
        for attempt in range(3):
            try:
                r1 = self.session.post(url_upload, params={"type": "file"}, timeout=30)
                r1.raise_for_status()
                upload_url = r1.json().get("url")
                if not upload_url:
                    raise MaxAPIError("Failed to get upload URL: no url in response")
                break
            except requests.exceptions.ReadTimeout as exc:
                logger.warning("send_document step 1 read timeout (attempt %d/3): %s", attempt + 1, exc)
                if attempt == 2:
                    logger.error("send_document step 1 (get url) final attempt failed: %s", exc)
                    raise MaxAPIError(f"Upload init fail timeout: {exc}")
                time.sleep(1 + attempt)
            except requests.exceptions.RequestException as exc:
                # Non-timeout request errors (connection etc.)
                logger.error("send_document step 1 (get url) request error: %s", exc)
                if attempt == 2:
                    raise MaxAPIError(f"Upload init fail: {exc}")
                time.sleep(1 + attempt)
            except Exception as exc:
                logger.error("send_document step 1 (get url) failed: %s", exc)
                raise MaxAPIError(f"Upload init fail: {exc}")

        # 2. Upload file to provided URL (with retries, reset file pointer)
        upload_resp = None
        mime = "application/octet-stream"
        if filename.endswith(".txt"):
            mime = "text/plain"
        elif filename.endswith(".jpeg") or filename.endswith(".jpg"):
            mime = "image/jpeg"
        elif filename.endswith(".png"):
            mime = "image/png"
        elif filename.endswith(".mp3"):
            mime = "audio/mpeg"

        for attempt in range(3):
            try:
                # Ensure we send the full file on retries
                if hasattr(file_obj, 'seek'):
                    try:
                        file_obj.seek(0)
                    except Exception:
                        # If seek fails, just continue; upload may still work for stream objects
                        logger.debug("file_obj.seek(0) failed; proceeding without seek")

                files = {"file": (filename, file_obj, mime)}
                # Use a moderate timeout; very long timeouts hide problems and block the poller.
                r2 = self.session.post(upload_url, files=files, timeout=300)
                r2.raise_for_status()

                upload_resp = r2.json()
                break
            except requests.exceptions.ReadTimeout as exc:
                logger.warning("send_document step 2 read timeout (attempt %d/3): %s", attempt + 1, exc)
                if attempt == 2:
                    logger.error("send_document step 2 (upload file) final attempt failed: %s", exc)
                    raise MaxAPIError(f"Upload file fail timeout: {exc}")
                time.sleep(1 + attempt)
            except requests.exceptions.RequestException as exc:
                logger.error("send_document step 2 (upload file) request error (attempt %d/3): %s", attempt + 1, exc)
                if attempt == 2:
                    raise MaxAPIError(f"Upload file fail: {exc}")
                time.sleep(1 + attempt)
            except Exception as exc:
                logger.error("send_document step 2 (upload file) failed: %s", exc)
                raise MaxAPIError(f"Upload file fail: {exc}")

        if not upload_resp:
            raise MaxAPIError("Upload file fail: no response after retries")
        # Depending on platform, token might be under token or returned directly
        token_payload = upload_resp.get("token") or upload_resp
        file_id = upload_resp.get("fileId") or upload_resp.get("id")

        # 3. Send message with the token
        try:
            msg_url = f"{self.base_url}/messages"
            text = caption if caption else "📄 Файл"
            
            # Construct the payload dict properly for MAX API
            payload_dict = {}
            if "token" in upload_resp:
                payload_dict["token"] = upload_resp["token"]
            if "fileId" in upload_resp:
                payload_dict["id"] = upload_resp["fileId"]
            elif "id" in upload_resp:
                payload_dict["id"] = upload_resp["id"]
            if not payload_dict:
                payload_dict = upload_resp
                
            json_body = {
                "text": text,
                "attachments": [
                    {
                        "type": "file",
                        "payload": payload_dict
                    }
                ]
            }
            if reply_markup is not None:
                try:
                    fm = reply_markup.to_dict() if hasattr(reply_markup, 'to_dict') else reply_markup
                    if isinstance(fm, dict) and "inline_keyboard" in fm:
                        buttons = []
                        for row in fm.get("inline_keyboard", []):
                            new_row = []
                            for btn in row:
                                new_row.append({
                                    "text": btn.get("text", ""),
                                    "type": "callback",
                                    "payload": btn.get("callback_data") or btn.get("payload") or btn.get("callbackData") or "btn"
                                })
                            buttons.append(new_row)
                        json_body["attachments"].append({
                            "type": "inline_keyboard",
                            "payload": {
                                "buttons": buttons
                            }
                        })
                    else:
                        json_body["attachments"].append({
                            "type": "inline_keyboard",
                            "payload": fm.get("inline_keyboard") or fm
                        })
                except Exception:
                    pass
            
            if parse_mode and parse_mode.lower() == "markdown":
                json_body["format"] = "markdown"
            
            # Since MAX API can take a moment to process the file, we add retries
            
            for attempt in range(5):
                try:
                    logger.info(f"Sending MSG document payload: {json_body}"); r3 = self.session.post(msg_url, params={"chat_id": str(chat_id).strip()}, json=json_body, timeout=60)
                    if r3.status_code == 400 and "attachment.not.ready" in r3.text:
                        logger.info("Attachment not ready, waiting 1s (attempt %d/5)", attempt + 1)
                        time.sleep(1)
                        continue
                    if r3.status_code == 400:
                        logger.error(f"HTTP 400 payload {json_body} resp {r3.text}")
                    r3.raise_for_status()
                    return r3.json()
                except requests.exceptions.ReadTimeout as e:
                    logger.warning("send_document step 3 read timeout (attempt %d/5): %s", attempt + 1, e)
                    if attempt == 4:
                        raise MaxAPIError(f"Send message with attachment fail timeout: {e}")
                    time.sleep(1 + attempt)
                
            raise MaxAPIError("Attachment not ready after 5 retries")
            
        except Exception as exc:
            logger.error("send_document step 3 (send msg) failed: %s", exc)
            raise MaxAPIError(f"Send message with attachment fail: {exc}")

    def download_url_to_file(self, url: str, destination_path: str, expected_size_bytes: Optional[int] = None, progress_callback=None) -> bool:
        """Download a file by URL to destination_path (streaming)."""
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
            except requests.exceptions.RequestException as e:
                logger.warning("download failed on attempt %s: %s", attempt, e)
                if attempt == retries:
                    logger.error("download failed after %s attempts: %s", retries, e)
                    return False
                time.sleep(2)
        return False

    def get_updates(self, offset: Optional[int] = None, limit: int = 100, timeout: int = 30) -> list:
        """Poll provider for new updates.

        This is a generic implementation that expects the provider to expose an
        endpoint like GET /updates?marker=...&limit=...&timeout=... which returns
        a JSON array of update objects. Adapt to real Max API if the path/shape
        differs.
        """
        url = f"{self.base_url}/updates"
        params = {"limit": limit, "timeout": timeout}
        if offset is not None:
            # API uses 'marker' as pointer to next update; keep method param
            # name 'offset' for backward compatibility with the poller.
            params["marker"] = offset
        try:
            r = self.session.get(url, params=params, timeout=timeout + 10)
        except Exception as exc:
            logger.debug("get_updates request failed: %s", exc)
            raise MaxAPIError(str(exc))

        # Handle rate limiting explicitly
        if r.status_code == 429:
            # Try to include any server message in the exception
            body = r.text
            logger.error("get_updates failed: 429 %s", body)
            raise MaxAPIError(body, status_code=429, headers=r.headers)

        if not r.ok:
            logger.error("get_updates failed: %s %s", r.status_code, r.text)
            raise MaxAPIError(r.text, status_code=r.status_code, headers=r.headers)

        try:
            data = r.json()
        except Exception:
            logger.error("get_updates: failed to decode json: %s", r.text)
            raise MaxAPIError("invalid json", status_code=r.status_code, headers=r.headers)

        # Allow both {"updates": [...]} and raw list responses
        if isinstance(data, dict) and "updates" in data:
            return data["updates"] or []
        if isinstance(data, list):
            return data
        return []
