"""Adapter layer that exposes a minimal telegram-like Context and Message
objects for reuse of existing transkribator_modules bot handlers.

We don't construct real python-telegram-bot objects; instead we provide
lightweight wrappers implementing only the methods/attributes used by
handlers (message.reply_text, context.bot.send_message, context.chat_data, etc.).
"""
from __future__ import annotations
import asyncio
from typing import Any, Dict, Optional

from .api_client import MaxAPI, MaxAPIError
from .config import logger
import json


class MaxBotAdapter:
    """Async-friendly adapter that proxies calls to MaxAPI."""

    def __init__(self, api: Optional[MaxAPI] = None):
        self.api = api or MaxAPI()

    async def send_message(self, chat_id: Any = None, text: str = "", **kwargs) -> Any:
        # MaxAPI.send_message is sync, call in threadpool
        reply_markup = kwargs.get("reply_markup")
        resp = await asyncio.to_thread(self.api.send_message, chat_id, text, reply_markup=reply_markup)
        
        # We must return a fake message so `status_msg.edit_text()` doesn't throw AttributeError
        # 'resp' is the dictionary returned by the API
        
        message_id = None
        if isinstance(resp, dict):
            # Try to grab the message_id from the JSON response if available
            # MaxAPI might return `{'message': {'body': {'mid': '...'}}}` 
            # or `{'mid': '...'}`
            msg_data = resp.get("message")
            if isinstance(msg_data, dict):
                body_data = msg_data.get("body")
                if isinstance(body_data, dict):
                    message_id = body_data.get("mid") or body_data.get("message_id")
            
            if not message_id:
                message_id = resp.get("mid") or resp.get("message_id")
            
        fake_msg = FakeMessage(chat_id=chat_id, message_id=message_id, text=text, bot=self)
        fake_msg._ctx = getattr(self, "_ctx", None)
        return fake_msg

    async def edit_message_text(self, chat_id: Any, message_id: Any, text: str, **kwargs) -> dict:
        # Our MaxAPI implements edit_message(chat_id, message_id, text)
        reply_markup = kwargs.get("reply_markup")
        return await asyncio.to_thread(self.api.edit_message, chat_id, message_id, text, reply_markup=reply_markup)

    async def send_document(self, chat_id: Any, file_obj, filename: str, caption: Optional[str] = None) -> dict:
        return await asyncio.to_thread(self.api.send_document, chat_id, file_obj, filename, caption)


class FakeMessage:
    def __init__(self, bot: MaxBotAdapter, chat_id: Any, message_id: int = 0, text: Optional[str] = None, caption: Optional[str] = None):
        self._bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self.text = text
        self.caption = caption
        # Will be set by build_update_and_context so reply_text can mark sends
        self._ctx = None
        self._sent = False

        # PTB-like attributes handlers expect (present but default to None/empty)
        # Media attributes: voice, audio, video, document, photo, video_note
        self.voice = None
        self.audio = None
        self.video = None
        self.document = None
        self.photo = None
        self.video_note = None

        # Chat and from_user objects (some handlers access message.chat and message.from_user)
        self.chat = None
        self.from_user = None
        # Provide a convenience alias used in some code paths
        self.message_id = message_id
        self.chat_id = chat_id

    async def reply_text(self, text: str, **kwargs):
        # reply_text usually targets the chat where the message came from
        try:
            return await self._bot.send_message(self.chat_id, text, **kwargs)
        except MaxAPIError as exc:
            logger.warning("reply_text failed: %s", exc)
            raise
        finally:
            try:
                self._sent = True
                if getattr(self, "_ctx", None) is not None:
                    self._ctx._sent_messages = getattr(self._ctx, "_sent_messages", 0) + 1
            except Exception:
                pass

    async def edit_text(self, text: str, **kwargs):
        try:
            return await self._bot.edit_message_text(self.chat_id, getattr(self, "message_id", None), text, **kwargs)
        except MaxAPIError as exc:
            logger.debug("edit_text failed: %s", exc)


class FakeChat:
    def __init__(self, id: Any, type: str = "private"):
        self.id = id
        self.type = type

    async def send_action(self, action: Any):
        # No-op for MAX adapter; handlers call this to show typing indicators.
        return None


class FakeUser:
    def __init__(self, id: Any, first_name: str = "MaxUser", last_name: Optional[str] = None):
        self.id = id
        self.first_name = first_name
        self.last_name = last_name

    # Some handlers reference .username
    @property
    def username(self) -> Optional[str]:
        return None


class FakeContext:
    def __init__(self, bot_adapter: MaxBotAdapter, chat_data: Optional[Dict] = None):
        self.bot = bot_adapter
        self.chat_data: Dict[str, Any] = chat_data or {}
        self.user_data: Dict[str, Any] = {}
        self.args: list[str] = []
        # Provide a minimal Application-like object used by handlers to
        # schedule background tasks (context.application.create_task).
        class _App:
            def create_task(self, coro):
                """Schedule coro reliably.

                Prefer scheduling on the running event loop. If none is
                available, run the coroutine in a background thread via
                asyncio.run so the work still executes (returned value will be
                a Thread object in that fallback case).
                """
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    return loop.create_task(coro)

                # Fallback: run in a background thread to avoid losing the
                # coroutine. This returns the Thread object (not an asyncio
                # Task) but handlers generally don't rely on the return value.
                import threading

                def _runner():
                    try:
                        asyncio.run(coro)
                    except Exception:
                        logger.exception("background task failed")

                t = threading.Thread(target=_runner, daemon=True)
                t.start()
                return t

        self.application = _App()


class FakeCallbackQuery:
    def __init__(self, data: str, message: FakeMessage):
        self.data = data
        self.message = message

    async def answer(self, text: Optional[str] = None, show_alert: bool = False, **kwargs):
        # In MAX, we typically don't have to ack callback queries explicitly like Telegram.
        # But if needed, we stub it here to avoid crashes in handlers.
        pass


def build_update_and_context(raw_update: dict, api: Optional[MaxAPI] = None):
    """Construct minimal update-like and context-like objects from provider update.

    raw_update expected to follow MAX update shape used elsewhere in this repo
    (message -> recipient.chat_id, body.text, etc.).
    """
    bot_adapter = MaxBotAdapter(api=api)
    # create context first so FakeMessage can reference it
    msg = raw_update.get("message") or {}
    recipient = msg.get("recipient") or {}
    chat_id = recipient.get("chat_id") or recipient.get("id") or raw_update.get("chat_id") or msg.get("chat_id")
    user = msg.get("sender") or msg.get("from") or {}
    user_id = user.get("user_id") or user.get("id") or raw_update.get("user_id")

    text = (msg.get("body") or {}).get("text") or msg.get("text") or msg.get("caption")

    ctx = FakeContext(bot_adapter)
    # track sends performed by the fake message/context
    ctx._sent_messages = 0

    fake_message = FakeMessage(bot_adapter, chat_id=chat_id, message_id=msg.get("id") or msg.get("message_id") or 0, text=text, caption=msg.get("caption"))
    # populate chat/from_user and media stubs so handlers can inspect safely
    fake_message.chat = FakeChat(chat_id)
    fake_message.from_user = FakeUser(
        user_id or chat_id,
        first_name=user.get("first_name") or user.get("name") or "MaxUser",
        last_name=user.get("last_name")
    )
    # give message a back-reference to context so reply_text can update counters
    fake_message._ctx = ctx

    # If the provider included file metadata in the body or attachments, expose
    # a minimal file-like object with attributes handlers use
    body = msg.get("body") or {}
    file_meta = None
    source = None

    # Helper to normalize an attachment dict into file_meta
    def _meta_from_dict(d: dict) -> Optional[dict]:
        if not isinstance(d, dict):
            return None
        # common url/id fields
        fid = d.get("file_id") or d.get("id") or d.get("fileId")
        size = d.get("file_size") or d.get("size") or d.get("fileSize")
        mtype = d.get("mime_type") or d.get("mimeType") or d.get("content_type")
        name = d.get("file_name") or d.get("name") or d.get("filename")
        url = d.get("url") or d.get("file_url") or d.get("download_url") or d.get("content_url")
        if fid or url:
            return {"file_id": fid, "file_size": size, "mime_type": mtype, "file_name": name, "file_url": url}
        return None

    # 1) body.file or body.file_id
    if isinstance(body, dict):
        if body.get("file_id"):
            file_meta = {"file_id": body.get("file_id"), "file_size": body.get("file_size"), "mime_type": body.get("mime_type"), "file_name": body.get("file_name"), "file_url": body.get("file_url")}
            source = "body.file_id"
        elif isinstance(body.get("file"), dict):
            f = body.get("file")
            file_meta = {"file_id": f.get("id") or f.get("file_id"), "file_size": f.get("size"), "mime_type": f.get("mime_type"), "file_name": f.get("name"), "file_url": f.get("url")}
            source = "body.file"

    # 2) message-level keys like document/file/photo/audio/voice
    if not file_meta and isinstance(msg, dict):
        for k in ("document", "file", "photo", "voice", "audio", "video"):
            v = msg.get(k)
            if v:
                # photo might be a list
                if isinstance(v, list) and v:
                    # pick the last (largest) photo
                    cand = v[-1]
                    meta = _meta_from_dict(cand)
                    if meta:
                        file_meta = meta
                        source = f"msg.{k}[list]"
                        break
                else:
                    meta = _meta_from_dict(v)
                    if meta:
                        file_meta = meta
                        source = f"msg.{k}"
                        break

    # 3) message.body.attachments or message.attachments arrays (including forwarded messages)
    if not file_meta and isinstance(msg, dict):
        body_dict = msg.get("body") if isinstance(msg.get("body"), dict) else {}
        att = (
            body_dict.get("attachments") or body_dict.get("files") or body_dict.get("documents") or
            msg.get("attachments") or msg.get("files") or msg.get("documents")
        )
        # also check forwarded link -> message attachments (some updates nest attachments under link.message)
        try:
            link_msg = msg.get("link") and isinstance(msg.get("link"), dict) and msg.get("link").get("message")
            if isinstance(link_msg, dict):
                link_att = link_msg.get("attachments") or link_msg.get("files") or link_msg.get("documents")
                if isinstance(link_att, list) and link_att:
                    # prefer link attachments over msg.attachments
                    att = link_att
        except Exception:
            pass

        if isinstance(att, list) and att:
            for item in att:
                # sometimes attachment is {type:..., payload: {...}}
                if isinstance(item, dict) and item.get("payload") and isinstance(item.get("payload"), dict):
                    cand = item.get("payload")
                else:
                    cand = item
                meta = _meta_from_dict(cand)
                if meta:
                    file_meta = meta
                    source = "msg.attachments"
                    break

    # 4) top-level attachments/files
    if not file_meta:
        top_att = raw_update.get("attachments") or raw_update.get("files") or raw_update.get("documents")
        if isinstance(top_att, list) and top_att:
            for item in top_att:
                cand = item.get("payload") if isinstance(item, dict) and item.get("payload") else item
                meta = _meta_from_dict(cand if isinstance(cand, dict) else {})
                if meta:
                    file_meta = meta
                    source = "top.attachments"
                    break
        elif isinstance(top_att, dict):
            meta = _meta_from_dict(top_att)
            if meta:
                file_meta = meta
                source = "top.attachments.dict"

    # 5) payload / data
    if not file_meta:
        data = raw_update.get("data") or raw_update.get("payload")
        if isinstance(data, dict):
            meta = _meta_from_dict(data)
            if meta:
                file_meta = meta
                source = "raw.payload"

    if file_meta:
        class _F:
            def __init__(self, meta: dict):
                self.file_id = str(meta.get("file_id") or "")
                self.file_size = meta.get("file_size")
                self.mime_type = meta.get("mime_type")
                self.file_name = meta.get("file_name")
                self.file_url = meta.get("file_url")

        fake_file = _F(file_meta)
        # attach to common media attributes so handlers can find it
        fake_message.document = fake_file
        fake_message.video = fake_file
        fake_message.audio = fake_file
        fake_message.voice = fake_file
        fake_message.video_note = fake_file
        # Log which source provided the metadata (guard against None)
        try:
            if file_meta and isinstance(file_meta, dict):
                # log a trimmed JSON of the file_meta for easier debugging in container logs
                fm = dict(file_meta)
                try:
                    fm_dump = json.dumps(fm, ensure_ascii=False)
                    if len(fm_dump) > 1000:
                        fm_dump = fm_dump[:1000] + "..."
                except Exception:
                    fm_dump = str(fm)
                logger.info("[adapter] attached fake file from %s: %s", source, fm_dump)
            else:
                logger.info("[adapter] attempted to attach fake file from %s but file_meta empty", source)
        except Exception:
            logger.debug("[adapter] failed to log file_meta", exc_info=True)

    fake_update = type("UpdateLike", (), {})()
    setattr(fake_update, "message", fake_message)
    setattr(fake_update, "effective_chat", FakeChat(chat_id))
    setattr(fake_update, "effective_user", FakeUser(
        user_id or chat_id,
        first_name=user.get("first_name") or user.get("name") or "MaxUser",
        last_name=user.get("last_name")
    ))
    # Some handler background tasks access update.effective_message; provide it
    # so code can read message_id and other attributes safely.
    setattr(fake_update, "effective_message", fake_message)
    setattr(fake_update, "update_id", raw_update.get("id") or raw_update.get("update_id"))
    setattr(fake_update, "provider_platform", "max")

    # If this is a callback query or inline button press, fake a callback_query.
    # We check for a payload/data assuming it's a string, or explicitly a 'callback_query' object.
    cb = raw_update.get("callback_query")
    callback_data = None
    if isinstance(cb, dict):
        callback_data = cb.get("data")
    elif raw_update.get("type") == "callback_query" or getattr(fake_update, "type", None) == "callback_query":
        callback_data = raw_update.get("data")
    else:
        # Sometimes postbacks come in the body or payload as a string
        pd = raw_update.get("payload") or raw_update.get("data")
        if isinstance(pd, str):
            callback_data = pd
        else:
            bd = msg.get("body") or {}
            bd_pd = bd.get("payload") or bd.get("data")
            if isinstance(bd_pd, str):
                callback_data = bd_pd

    if callback_data:
        fake_cb = FakeCallbackQuery(callback_data, getattr(fake_update, "message"))
        setattr(fake_update, "callback_query", fake_cb)

    # Debugging: log presence of common media attributes to help diagnose
    try:
        logger.debug("[adapter] built FakeMessage for chat=%s user=%s attrs: video=%s document=%s text=%s callback=%s", chat_id, user_id, hasattr(fake_message, "video"), hasattr(fake_message, "document"), getattr(fake_message, "text", None), bool(callback_data))
    except Exception:
        pass

    return fake_update, ctx
