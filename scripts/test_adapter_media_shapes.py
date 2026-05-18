from max_bot.adapter import build_update_and_context

cases = []

# 1: text message
cases.append(("text", {"id": "u1", "message": {"body": {"text": "hello"}, "recipient": {"chat_id": "123"}, "sender": {"user_id": "uuser"}}}))

# 2: body.file
cases.append(("body.file", {"id": "u2", "message": {"body": {"file": {"id": "f123", "size": 1024, "mime_type": "audio/ogg", "name": "voice.ogg", "url": "https://example.com/f123"}}, "recipient": {"chat_id": "123"}, "sender": {"user_id": "uuser"}}}))

# 3: msg.document
cases.append(("msg.document", {"id": "u3", "message": {"document": {"file_id": "d-1", "size": 2048, "mime_type": "application/pdf", "name": "doc.pdf", "url": "https://example.com/d-1"}, "recipient": {"chat_id": "123"}, "sender": {"user_id": "uuser"}}}))

# 4: attachments with payload
cases.append(("attachments.payload", {"id": "u4", "message": {"attachments": [{"type": "file", "payload": {"id": "a-1", "file_url": "https://example.com/a-1", "mime_type": "image/png"}}], "recipient": {"chat_id": "123"}, "sender": {"user_id": "uuser"}}}))

# 5: top-level attachments
cases.append(("top.attachments", {"id": "u5", "attachments": [{"payload": {"file_id": "t-1", "file_url": "https://example.com/t-1", "mime_type": "audio/mpeg"}}], "message": {"recipient": {"chat_id": "123"}, "sender": {"user_id": "uuser"}}}))

# 6: voice field
cases.append(("msg.voice", {"id": "u6", "message": {"voice": {"id": "v-1", "file_url": "https://example.com/v-1", "mime_type": "audio/ogg"}, "recipient": {"chat_id": "123"}, "sender": {"user_id": "uuser"}}}))

from textwrap import indent

for name, upd in cases:
    fake_update, ctx = build_update_and_context(upd)
    msg = fake_update.message
    f = None
    for attr in ("document", "video", "audio", "voice", "video_note"):
        v = getattr(msg, attr, None)
        if v:
            f = v
            which = attr
            break
    print("---", name)
    print(" text=", getattr(msg, 'text', None))
    if f:
        print(" found file on", which, "file_id=", getattr(f, 'file_id', None), "file_url=", getattr(f, 'file_url', None), "mime=", getattr(f, 'mime_type', None))
    else:
        print(" no file attached")

print('\nctx._sent_messages after build (should be 0):', getattr(ctx, '_sent_messages', None))
