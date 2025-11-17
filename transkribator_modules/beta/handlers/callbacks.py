"""Callback handlers for the updated beta agent (legacy buttons fallback)."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from transkribator_modules.config import logger


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    logger.info(
        "Beta callback received after refactor",
        extra={"data": query.data, "user_id": update.effective_user.id if update.effective_user else None},
    )
    await query.answer("Новый бета-режим работает через диалог. Напишите запрос текстом.", show_alert=False)

