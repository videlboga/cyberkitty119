"""FastAPI webhook server for Max messenger integration.

Endpoints:
  POST /webhook/max  - receive Max events (expects JSON)
  GET  /health       - simple healthcheck

This server calls `max_bot.handlers.handle_media_event` for incoming media events.
"""
from __future__ import annotations

import os
import logging
from typing import Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

from max_bot.api_client import MaxAPI
from max_bot.handlers import handle_media_event
from max_bot.config import logger as max_logger


app = FastAPI(title="Max Bot Webhook")


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.post("/webhook/max")
async def webhook_max(request: Request) -> JSONResponse:
    """Receive webhook from Max and dispatch to handler.

    The exact format depends on Max docs; this endpoint expects a JSON payload
    that includes at least chat_id and file_url for media events. If payload is
    different, adapt parsing accordingly.
    """
    try:
        payload: dict[str, Any] = await request.json()
    except Exception as exc:
        max_logger.exception("[max] invalid json payload")
        raise HTTPException(status_code=400, detail="invalid json") from exc

    # Basic validation — forward the whole payload to handler for flexibility
    api = MaxAPI()

    # Schedule handling asynchronously — webhook returns 200 immediately.
    # Use create_task to avoid blocking the request.
    try:
        app.loop = getattr(app, "loop", None) or None
        # FastAPI/uvicorn will handle event loop; just create a background task.
        import asyncio

        asyncio.create_task(handle_media_event(payload, api=api))
    except Exception:
        # Fallback: try calling directly (synchronous)
        try:
            await handle_media_event(payload, api=api)
        except Exception:
            max_logger.exception("[max] handler failed")
            raise HTTPException(status_code=500, detail="handler failed")

    return JSONResponse({"status": "accepted"}, status_code=202)


if __name__ == "__main__":
    # Allow overriding host/port via env
    host = os.getenv("MAX_BOT_HOST", "0.0.0.0")
    port = int(os.getenv("MAX_BOT_PORT", "8085"))
    uvicorn.run("max_bot.server:app", host=host, port=port, log_level="info")
