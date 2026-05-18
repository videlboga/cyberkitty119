"""Minimal long-polling echo script for MAX platform.

This script uses the MaxAPI client in this package to poll for updates and
send back a simple "Echo: <text>" reply to the same chat_id found in updates.

Usage:
  export MAX_API_TOKEN=... # or ensure .env is loaded in your environment
  python -m max_bot.echo_longpoll

This is intended for quick local testing. For production use the existing
`max_bot.poller` + `max_bot.handlers` pipeline which integrates with the
project worker system.
"""
from __future__ import annotations
import os
import time
import logging

from .api_client import MaxAPI, MaxAPIError
from .config import logger as max_logger

logger = max_logger or logging.getLogger("max_bot.echo_longpoll")


def run_echo_loop():
    api = MaxAPI()
    logger.info("echo_longpoll: starting long-poll loop")

    marker = None
    backoff = 1
    while True:
        try:
            # Use timeout to enable long polling on server side
            data = api.get_updates(offset=marker, timeout=30)
            if not data:
                # nothing received
                marker = marker
                backoff = 1
                continue

            for upd in data:
                # try to extract chat_id and text
                try:
                    msg = upd.get("message") or upd
                    recipient = (msg or {}).get("recipient") or {}
                    chat_id = recipient.get("chat_id") or recipient.get("id") or upd.get("chat_id") or (msg or {}).get("chat_id")
                    text = (msg or {}).get("body", {}).get("text") or (msg or {}).get("text")
                    if chat_id and text:
                        reply = "Echo: " + text
                        try:
                            api.send_message(chat_id, reply)
                            logger.info("echo_longpoll: replied to %s", chat_id)
                        except MaxAPIError as me:
                            logger.warning("echo_longpoll: failed to send reply: %s", me)
                except Exception:
                    logger.exception("echo_longpoll: failed to process update %s", upd)

                # update marker using 'id' or 'update_id'
                try:
                    uid = upd.get("id") or upd.get("update_id")
                    if uid is not None:
                        marker = int(uid) + 1
                except Exception:
                    pass

            backoff = 1

        except MaxAPIError as exc:
            logger.warning("echo_longpoll: MaxAPIError %s", exc)
            # honor retry-after if provided
            sleep = getattr(exc, "retry_after", None) or backoff
            time.sleep(sleep)
            backoff = min(backoff * 2, 300)
        except Exception as exc:
            logger.exception("echo_longpoll: error in poll loop: %s", exc)
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)


if __name__ == "__main__":
    run_echo_loop()
