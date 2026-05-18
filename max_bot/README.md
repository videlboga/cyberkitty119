Max bot scaffold

This package contains a minimal production-oriented integration for the "Max"
messenger. It uses provider-aware user identifiers and enqueues media jobs into
existing transkribator workers.

Quick start (local):
- Set env: MAX_API_TOKEN, MAX_API_URL (if needed), MEDIA_INCOMING_DIR
- Run a small HTTP server that accepts Max webhooks and calls
  `max_bot.handlers.handle_media_event(event)` for incoming media events.

Notes:
- The implementation assumes the Max API supports send_message, edit_message,
  send_document and file downloads via URL. Adjust `max_bot/api_client.py` to fit
  the real API.
