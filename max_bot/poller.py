"""Poller for Max messenger updates.

This module implements a configurable poller that repeatedly calls
`MaxAPI.get_updates` with an offset, schedules `handle_media_event` for each
update and persists `last_update_id` to a local state file (data/max_poll_state.json)
to avoid schema changes in the DB for a first iteration.

The poller supports long polling (timeout parameter) and basic backoff on
errors/rate limits.
"""
from __future__ import annotations

import time
import json
import os
import asyncio
from typing import Optional

from .api_client import MaxAPI
from .handlers import handle_media_event
from .config import logger, MAX_POLL_INTERVAL, MAX_POLL_LONGPOLL, MAX_POLL_TIMEOUT, MAX_POLL_STATE_FILE
from .config import MAX_POLL_TIMEOUT as _TMP

# Simple in-memory dedupe cache to avoid processing the same provider message
# more than once in a short window. This helps when the provider may deliver
# duplicates or when polling state drifts. Keyed by message.mid (provider
# message identifier) or by update id when mid is unavailable.
_PROCESSED_CACHE: dict = {}
# dedupe window seconds (keep recent ids for this long)
_DEDUPE_WINDOW = 300


def _has_file_like_in_update(upd: dict) -> bool:
    """Quick heuristic: return True if update contains any attachment-like
    object that *probably* has a url or file_id. This is intentionally cheap
    and used only for lookahead inside a single get_updates batch.
    """
    try:
        msg = upd.get("message") if "message" in upd else None
        # check top-level
        for key in ("url", "file_url", "download_url", "content_url"):
            if upd.get(key):
                return True

        # check top attachments
        top_att = upd.get("attachments") or upd.get("files") or upd.get("documents")
        if isinstance(top_att, list) and top_att:
            # if any candidate has url or id, consider it a file-like
            for c in top_att:
                if isinstance(c, dict):
                    if any((c.get(k) for k in ("url", "file_url", "download_url", "content_url", "id", "file_id"))):
                        return True
                else:
                    return True

        if isinstance(msg, dict):
            # attachments arrays
            body = msg.get("body") if isinstance(msg.get("body"), dict) else {}
            att = (
                (msg.get("link") or {}).get("message", {}).get("attachments") if isinstance((msg.get("link") or {}).get("message", {}), dict) else None
            )
            if not att:
                att = body.get("attachments") or body.get("files") or body.get("documents") or msg.get("attachments") or msg.get("files")
            if isinstance(att, list) and att:
                for a in att:
                    if isinstance(a, dict):
                        if any((a.get(k) or (a.get("payload") or {}).get(k) for k in ("url", "file_url", "download_url", "content_url", "id", "file_id"))):
                            return True
                    else:
                        return True

            # single-file keys
            for k in ("document", "file", "photo", "voice", "audio"):
                v = msg.get(k)
                if v:
                    if isinstance(v, dict):
                        if any((v.get(x) for x in ("url", "file_url", "id", "file_id"))):
                            return True
                    else:
                        return True
    except Exception:
        return False
    return False


def _load_state(path: str) -> dict:
    try:
        with open(path, "r") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_state(path: str, state: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        json.dump(state, fh)


def map_update_to_event(upd: dict) -> dict:
    """Map provider-specific update envelope into a normalized event dict.

    This is the same heuristic logic previously embedded in the async
    processor but exposed so we can test it against saved examples and
    add extra debug output without running the live poller.
    """
    # Heuristics for common shapes. Try multiple possible paths.
    chat = None
    file_url = None
    file_id = None
    message_id = None

    # direct fields
    chat = upd.get("chat_id") or upd.get("chat") or chat
    if isinstance(chat, dict):
        chat = chat.get("id") or chat.get("chat_id") or chat.get("user_id")

    # common wrappers
    # Always read the message object if present; chat may be already set
    msg = upd.get("message") if "message" in upd else None
    if isinstance(msg, dict):
        # prefer explicit chat identifiers from the message if we don't have one
        chat = chat or msg.get("chat_id") or (msg.get("chat") or {}).get("id") or msg.get("from") or chat
        message_id = msg.get("id") or msg.get("message_id")

    # attachments / files
    candidates = []
    if msg and isinstance(msg, dict):
        # Quick direct extraction for forwarded link.message.attachments
        try:
            _lm = (msg.get("link") or {}).get("message") if isinstance(msg.get("link"), dict) else None
            if isinstance(_lm, dict):
                # DEBUG: log link.message attachments shape (truncated)
                try:
                    import json as _json

                    lm_dump = _json.dumps(_lm.get("attachments") or _lm.get("files") or _lm.get("documents") or {}, ensure_ascii=False)
                    if len(lm_dump) > 1000:
                        lm_dump = lm_dump[:1000] + "..."
                except Exception:
                    lm_dump = str((_lm.get("attachments") or _lm.get("files") or _lm.get("documents")) or {})
                logger.info("poller: link.message attachments dump=%s", lm_dump)

                _atts = _lm.get("attachments") or _lm.get("files") or _lm.get("documents")
                if isinstance(_atts, list) and _atts:
                    for a in _atts:
                        if isinstance(a, dict):
                            p = a.get("payload") if isinstance(a.get("payload"), dict) else a
                            try:
                                kdump = ",".join(sorted(list(p.keys()))) if isinstance(p, dict) else str(type(p))
                            except Exception:
                                kdump = str(type(p))
                            logger.info("poller: inspecting forwarded attachment payload keys=%s", kdump)
                            for k in ("url", "file_url", "download_url", "content_url"):
                                if isinstance(p, dict) and p.get(k):
                                    file_url = p.get(k)
                                    file_id = p.get("id") or p.get("file_id") or file_id
                                    logger.info("poller: extracted file_url from link.message payload key=%s", k)
                                    break
                        if file_url:
                            break
        except Exception:
            # be fault tolerant; fall back to general heuristics below
            pass
        # attachments array
        body_dict = msg.get("body") if isinstance(msg.get("body"), dict) else {}
        # Prefer forwarded (link.message) attachments when present because
        # many forwards include the actual file metadata there.
        att = None
        try:
            link_msg = msg.get("link") if isinstance(msg.get("link"), dict) else None
            link_att = (link_msg.get("message") or {}).get("attachments") if link_msg else None
            if isinstance(link_att, list) and link_att:
                att = link_att
        except Exception:
            att = None

        # If no link attachments, fall back to body/msg attachments
        if att is None:
            att = (
                body_dict.get("attachments") or body_dict.get("files") or body_dict.get("documents") or
                msg.get("attachments") or msg.get("files") or msg.get("documents")
            )

        if isinstance(att, list) and att:
            for a in att:
                # normalize shapes: {type:..., payload: {...}} and raw payloads
                if isinstance(a, dict) and isinstance(a.get("payload"), dict):
                    candidates.append(a.get("payload"))
                else:
                    candidates.append(a)
        # single document
        for k in ("document", "file", "photo", "voice", "audio"):
            v = msg.get(k)
            if v:
                candidates.append(v)
        # also check forwarded link -> message attachments (some updates nest attachments under link.message)
        try:
            link_msg = msg.get("link") and isinstance(msg.get("link"), dict) and msg.get("link").get("message")
            # if we already handled link_msg above by preferring link attachments,
            # don't duplicate them here. This block remains for safety for
            # updates where link.message is present but wasn't used earlier.
            if isinstance(link_msg, dict):
                link_att = link_msg.get("message", {}).get("attachments") or link_msg.get("message", {}).get("files") or link_msg.get("message", {}).get("documents")
                if isinstance(link_att, list):
                    for a in link_att:
                        if isinstance(a, dict) and isinstance(a.get("payload"), dict):
                            candidates.append(a.get("payload"))
                        else:
                            candidates.append(a)
        except Exception:
            pass

    # recipient object (Max uses recipient.chat_id)
    rec = None
    if msg and isinstance(msg, dict):
        rec = msg.get("recipient") or msg.get("to")
        if isinstance(rec, dict):
            cid = rec.get("chat_id") or rec.get("id") or rec.get("user_id")
            if cid:
                chat = cid

    # top-level attachments
    top_att = upd.get("attachments") or upd.get("files") or upd.get("documents")
    if isinstance(top_att, list):
        candidates.extend(top_att)
    elif isinstance(top_att, dict):
        candidates.append(top_att)

    # search candidates for URL or file_id
    if candidates:
        try:
            # dump candidates as JSON-ish repr but cap length to avoid huge logs
            import json as _json

            dump = _json.dumps(candidates, ensure_ascii=False)
            if len(dump) > 2000:
                dump = dump[:2000] + "..."
        except Exception:
            dump = str(candidates[:4])
        logger.info("poller: attachment candidates count=%d dump=%s", len(candidates), dump)
    for c in candidates:
        if not isinstance(c, dict):
            continue
        # common url fields
        for key in ("url", "file_url", "download_url", "content_url"):
            if key in c and c.get(key):
                file_url = c.get(key)
                break
        # Some payloads nest the actual url under 'payload' or 'payload.url'
        if not file_url and isinstance(c.get("payload"), dict):
            for key in ("url", "file_url", "download_url", "content_url"):
                if key in c.get("payload") and c.get("payload").get(key):
                    file_url = c.get("payload").get(key)
                    break
        if file_url:
            file_id = c.get("id") or c.get("file_id") or (c.get("payload") or {}).get("id") or file_id
            break

    # fallback: some providers include 'data' or 'payload'
    if not file_url:
        data = upd.get("data") or upd.get("payload")
        if isinstance(data, dict):
            for key in ("url", "file_url", "download_url", "content_url"):
                if key in data and data.get(key):
                    file_url = data.get(key)
                    break

    # also capture message text when present
    text = None
    try:
        text = (upd.get("message") or {}).get("body", {}).get("text")
    except Exception:
        text = None

    # last-resort: fields directly on update
    if not file_url:
        for key in ("file_url", "url", "download_url"):
            if key in upd and upd.get(key):
                file_url = upd.get(key)
                break

    # final deep search: recursively look for any http(s) URL string in
    # the update payload. This helps with odd vendor shapes where the
    # URL is nested under unexpected keys or encoded within strings.
    def _find_url_in_obj(obj):
        if isinstance(obj, str):
            if obj.startswith("http://") or obj.startswith("https://"):
                return obj
            return None
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str) and (v.startswith("http://") or v.startswith("https://")):
                    return v
                try:
                    res = _find_url_in_obj(v)
                except Exception:
                    res = None
                if res:
                    return res
        if isinstance(obj, list):
            for it in obj:
                try:
                    res = _find_url_in_obj(it)
                except Exception:
                    res = None
                if res:
                    return res
        return None

    if not file_url:
        try:
            found = _find_url_in_obj(upd)
            if found:
                file_url = found
                logger.info("poller: deep-found url=%s", file_url)
        except Exception:
            logger.debug("poller: deep url search failed", exc_info=True)

    # If we found attachment candidates but couldn't resolve a usable URL,
    # log a warning with a truncated dump so we can extend parsing if needed.
    if (candidates and not file_url):
        try:
            import json as _json

            dump = _json.dumps(candidates, ensure_ascii=False)
            if len(dump) > 1000:
                dump = dump[:1000] + "..."
        except Exception:
            dump = str(candidates[:4])
        logger.warning("poller: attachments present but no file_url resolved; candidates=%s", dump)

    # normalize chat to string if numeric
    if chat is not None:
        try:
            chat = str(chat)
        except Exception:
            pass

    return {
        "chat_id": chat,
        "file_url": file_url,
        "file_id": file_id,
        "message_id": message_id,
        # include message text if present
        "text": text,
        # keep raw update for debugging
        "_raw_update": upd,
    }


async def _process_update(update: dict, api: MaxAPI) -> None:
    # Map provider-specific update envelope into the simple event dict
    # expected by `handle_media_event` (chat_id, file_url, file_id, filename).
    # Use the module-level mapper for testability and clearer logging
    try:
        from textwrap import shorten

        logger.info("poller: raw update: %s", shorten(repr(update), width=1000))
    except Exception:
        logger.info("poller: raw update: %s", update)

    try:
        event = map_update_to_event(update)
    except Exception as e:
        logger.error("poller: failed mapping update: %s", e)
        event = {}

    # Extra explicit extraction fallback for forwarded attachments: some
    # updates include the usable URL under message.link.message.attachments[*].payload.url
    # — if our general mapper didn't pick it up, try this targeted path before
    # falling back to the generic handlers. This addresses cases where the
    # provider nests attachments unexpectedly.
    if not event.get("file_url"):
        try:
            msg = (update.get("message") or {}) if isinstance(update.get("message"), dict) else {}
            link_msg = (msg.get("link") or {}).get("message") if isinstance(msg.get("link"), dict) else None
            if isinstance(link_msg, dict):
                atts = link_msg.get("attachments") or link_msg.get("files") or link_msg.get("documents")
                if isinstance(atts, list) and atts:
                    for a in atts:
                        if isinstance(a, dict):
                            p = a.get("payload") if isinstance(a.get("payload"), dict) else a
                            for k in ("url", "file_url", "download_url", "content_url"):
                                if isinstance(p, dict) and p.get(k):
                                    event["file_url"] = p.get(k)
                                    event["file_id"] = p.get("id") or p.get("file_id") or event.get("file_id")
                                    logger.info("poller: explicit-extracted forwarded file_url=%s", event["file_url"])
                                    break
                        if event.get("file_url"):
                            break
        except Exception:
            pass

    try:
        # log raw update briefly
        try:
            from textwrap import shorten

            logger.info("poller: raw update: %s", shorten(repr(update), width=1000))
        except Exception:
            logger.info("poller: raw update: %s", update)

        event = map_update_to_event(update)
        # Deduplicate by provider message id (mid) or update id.
        try:
            mid = None
            try:
                # prefer message.body.mid, fall back to message.mid, and check forwarded link.message.mid
                msg_body = (update.get("message") or {}).get("body") if isinstance((update.get("message") or {}).get("body"), dict) else None
                if msg_body and msg_body.get("mid"):
                    mid = msg_body.get("mid")
                else:
                    mid = (update.get("message") or {}).get("mid") or None
                # forwarded message mid
                try:
                    link_mid = (update.get("message") or {}).get("link", {}).get("message", {}).get("mid")
                    if link_mid and not mid:
                        mid = link_mid
                except Exception:
                    pass
            except Exception:
                mid = None
            uid = update.get("id") or update.get("update_id") or None
            dedupe_key = mid or uid
            if dedupe_key:
                now = time.time()
                # cleanup old entries
                stale = [k for k, v in _PROCESSED_CACHE.items() if now - v > _DEDUPE_WINDOW]
                for k in stale:
                    _PROCESSED_CACHE.pop(k, None)
                if dedupe_key in _PROCESSED_CACHE:
                    logger.info("poller: skipping duplicate update (key=%s) within %s seconds", dedupe_key, _DEDUPE_WINDOW)
                    return
                _PROCESSED_CACHE[dedupe_key] = now
        except Exception:
            # If dedupe check fails, continue processing normally
            logger.debug("poller: dedupe check error", exc_info=True)
        logger.info("poller: mapped event chat=%s file=%s text=%s", event.get("chat_id"), event.get("file_url"), event.get("text"))

        # Try to reuse the main Telegram handlers from transkribator_modules.
        # Build a minimal Update/Context pair and call handle_message so all
        # business logic (jobs, transcribe pipeline, QA, etc.) is reused.
        try:
            from transkribator_modules.bot.handlers import handle_message as tg_handle_message
            from .adapter import build_update_and_context

            fake_update, fake_ctx = build_update_and_context(update, api=api)
            # Call the telegram handler; it is async
            await tg_handle_message(fake_update, fake_ctx)
            # Note: we do not short-circuit to avoid missing other processing
        except Exception as exc:
            # If the telegram handler already sent a reply (some handlers
            # reply early and then later access attributes that may be
            # missing in our FakeMessage), avoid sending a duplicate
            # fallback reply. We track sends via fake_ctx._sent_messages.
            try:
                sent = getattr(fake_ctx, "_sent_messages", 0)
            except Exception:
                sent = 0

            logger.exception("poller: failed to invoke transkribator handler (sent=%s), falling back to max_bot handler: %s", sent, exc)
            if sent:
                logger.info("poller: telegram handler already sent %s messages; skipping fallback reply", sent)
            else:
                await handle_media_event(event, api=api)
    except Exception:
        # include the update body in the log for easier debugging
        try:
            uid = update.get("id") or update.get("update_id") or "?"
        except Exception:
            uid = "?"
        logger.exception("poller: failed to handle update %s; payload=%s", uid, update)


async def run_poll_loop():
    """Async loop entrypoint (suitable for container CMD)."""
    api = MaxAPI()
    state_path = MAX_POLL_STATE_FILE

    logger.info("max poller starting; longpoll=%s interval=%s timeout=%s", MAX_POLL_LONGPOLL, MAX_POLL_INTERVAL, MAX_POLL_TIMEOUT)
    
    state = _load_state(state_path)
    last_id = state.get("last_update_id")

    # Main loop
    backoff = 1
    while True:
        try:
            timeout = MAX_POLL_TIMEOUT if MAX_POLL_LONGPOLL else 0
            updates = await asyncio.to_thread(api.get_updates, offset=(last_id + 1 if last_id is not None else None), timeout=timeout)
            if updates:
                logger.info("poller: received %d updates", len(updates))
                # process updates in order
                for idx, upd in enumerate(updates):
                    # allow both 'id' and 'update_id'
                    uid = upd.get("id") or upd.get("update_id")
                    try:
                        # If this update appears to have no file/text but a later
                        # update in the same batch contains the file (common when
                        # provider emits a minimal update followed by forwarded
                        # payload), skip processing this minimal update — the
                        # later update will be processed and contains the real
                        # attachment. This reduces false fallbacks.
                        try:
                            # cheap heuristic: if this update has no file-like
                            # content but some later update in the batch with the
                            # same mid or forwarded mid does, prefer the later one.
                            if not _has_file_like_in_update(upd):
                                # extract mids for matching
                                msg = (upd.get("message") or {}) if isinstance(upd.get("message"), dict) else {}
                                body = msg.get("body") if isinstance(msg.get("body"), dict) else {}
                                mid = body.get("mid") or msg.get("mid") or None
                                link_mid = (msg.get("link") or {}).get("message", {}).get("mid") if isinstance((msg.get("link") or {}).get("message", {}), dict) else None
                                # look ahead in remaining updates
                                found_later = False
                                for later in updates[idx + 1:]:
                                    # cheap check: does later update contain file-like?
                                    if _has_file_like_in_update(later):
                                        # if mids match (or either missing), assume related
                                        l_msg = (later.get("message") or {}) if isinstance(later.get("message"), dict) else {}
                                        l_body = l_msg.get("body") if isinstance(l_msg.get("body"), dict) else {}
                                        l_mid = l_body.get("mid") or l_msg.get("mid") or None
                                        l_link_mid = (l_msg.get("link") or {}).get("message", {}).get("mid") if isinstance((l_msg.get("link") or {}).get("message", {}), dict) else None
                                        if (mid and l_mid and mid == l_mid) or (link_mid and l_link_mid and link_mid == l_link_mid) or (not mid and not link_mid):
                                            found_later = True
                                            break
                                if found_later:
                                    logger.info("poller: skipping minimal update in-batch in favor of later update (uid=%s)", uid)
                                    # advance last_id as usual; do not process this one
                                    if uid is not None:
                                        try:
                                            last_id = int(uid) if last_id is None or int(uid) > int(last_id) else last_id
                                        except Exception:
                                            pass
                                    continue
                        except Exception:
                            # on any heuristic failure, fall back to normal processing
                            pass

                        await _process_update(upd, api)
                    except Exception:
                        logger.exception("poller: processing update failed")

                    if uid is not None:
                        try:
                            last_id = int(uid) if last_id is None or int(uid) > int(last_id) else last_id
                        except Exception:
                            pass

                # persist state
                _save_state(state_path, {"last_update_id": last_id})

            # reset backoff on success
            backoff = 1

        except Exception as exc:
            # If we raised MaxAPIError with status/headers, try to honor Retry-After
            retry_sleep = None
            try:
                from .api_client import MaxAPIError

                if isinstance(exc, MaxAPIError) and exc.status_code == 429:
                    retry_sleep = getattr(exc, "retry_after", None) or None
                    if retry_sleep is None:
                        # if no Retry-After header, escalate backoff more aggressively
                        backoff = min(backoff * 2, 300)
                        retry_sleep = backoff
                    logger.warning("poller: rate limited (429). Sleeping for %s seconds", retry_sleep)
                else:
                    logger.warning("poller: error fetching updates: %s", exc)
            except Exception:
                logger.warning("poller: error fetching updates: %s", exc)

            # Sleep appropriate time
            try:
                await asyncio.sleep(retry_sleep or backoff)
            except Exception:
                await asyncio.sleep(backoff)

            # increase backoff after failure
            backoff = min(backoff * 2, 300)

        # Sleep between polls if not using longpoll
        if not MAX_POLL_LONGPOLL:
            await asyncio.sleep(MAX_POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(run_poll_loop())
