"""Контентный поток для бета-режима (заглушка)."""

from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from transkribator_modules.config import logger
from ..router import RouterResult

TYPE_LABELS = {
    "meeting": "встреча",
    "idea": "идея",
    "task": "задача",
    "media": "медиа",
    "recipe": "рецепт",
    "journal": "дневник",
    "other": "прочее",
}


def _build_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⚡ Обработать сейчас", callback_data="beta:act:now")],
            [InlineKeyboardButton("🕓 Обработать позже", callback_data="beta:act:later")],
            [InlineKeyboardButton("📝 Только транскрипт", callback_data="beta:act:raw")],
            [InlineKeyboardButton("🗂 Выбрать тип", callback_data="beta:act:type_menu")],
        ]
    )

def compose_header(type_hint: str, type_conf: float, manual_type: Optional[str]) -> str:
    chosen = manual_type or type_hint or "other"
    type_label = TYPE_LABELS.get(chosen, TYPE_LABELS["other"])

    if manual_type:
        return f"Готово. Выбрали: _{type_label}_. Что делаем?"

    confidence = max(0.0, min(type_conf * 100, 100.0))
    if type_conf >= 0.55:
        return f"Готово. Похоже: _{type_label}_ ({confidence:.0f}%). Что делаем?"

    return "Готово. Что делаем с записью?"


async def show_processing_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    router_result: RouterResult,
) -> None:
    """Показывает первый экран обработки в бета-режиме."""

    user_id = update.effective_user.id if update.effective_user else None
    logger.info(
        "Показываем экран обработки",
        extra={
            "user_id": user_id,
            "mode": router_result.mode,
            "confidence": router_result.confidence,
            "type_hint": router_result.content.type_hint,
            "error": router_result.error,
        },
    )

    beta_state = context.user_data.setdefault("beta", {})
    beta_state["router_payload"] = router_result.payload.model_dump()

    manual_type = beta_state.get("manual_type")
    type_hint = router_result.content.type_hint or "other"
    type_conf = router_result.content.type_confidence or 0.0
    header = compose_header(type_hint, type_conf, manual_type)

    await update.message.reply_text(
        header,
        reply_markup=_build_main_keyboard(),
        parse_mode="Markdown",
    )
