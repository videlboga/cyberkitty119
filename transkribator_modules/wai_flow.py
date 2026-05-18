"""Lightweight menu flow that delivers the simplified UX screens.

Screens:
- Main menu: подписка, рефералка, запись встреч, настройки, помощь.
- Settings submenu: интерфейс, формат, модель, язык файла.
- Subscription/referral/help text screens with return buttons.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, Update
from telegram.ext import ContextTypes

from transkribator_modules.config import (
    logger,
    TELEGRAM_REFERRAL_URL,
)
from transkribator_modules.db.database import SessionLocal, UserService, ReferralService
from transkribator_modules.manual_mode import manual_vector_chat_command


WAI_STATE_KEY = "wai_flow"


def _build_referral_deeplink(referral_code: str) -> str:
    parsed = urlparse(TELEGRAM_REFERRAL_URL)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params.setdefault("utm_source", "telegram")
    params.setdefault("utm_medium", "bot")
    params.setdefault("utm_campaign", "referral")
    params["start"] = f"ref_{referral_code}"

    path_segments = [segment for segment in parsed.path.split("/") if segment]
    if parsed.scheme in {"http", "https"} and parsed.netloc.lower().endswith("t.me") and path_segments:
        bot_segment = path_segments[0]
        base_path = f"/{bot_segment}"
        params.pop("startapp", None)
        return urlunparse(parsed._replace(path=base_path, query=urlencode(params)))

    return urlunparse(parsed._replace(query=urlencode(params)))


def _ensure_state(user_data: dict[str, Any]) -> dict[str, Any]:
    state = user_data.get(WAI_STATE_KEY)
    if not state:
        state = {
            "settings": {
                "lang": "ru",
                "format": "Google Docs",
                "model": "ChatGPT-4o",
                "input_lang": "auto",
            }
        }
        user_data[WAI_STATE_KEY] = state
    return state


def _main_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("⚡️ Подписка", callback_data="main:subscription")],
        [InlineKeyboardButton("🤝 Реферальная программа", callback_data="main:referral")],
        [InlineKeyboardButton("🔎 Поиск по заметкам", callback_data="main:search")],
        [InlineKeyboardButton("📚 Помощь", callback_data="main:help")],
    ]
    return InlineKeyboardMarkup(rows)


def _reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, **kwargs):
    cb = getattr(update, "callback_query", None)
    if cb and cb.message:
        try:
            return cb.message.edit_text(text, **kwargs)
        except Exception:  # noqa: BLE001
            pass
    if getattr(update, "message", None):
        return update.message.reply_text(text, **kwargs)
    if update.effective_user:
        return context.bot.send_message(chat_id=update.effective_user.id, text=text, **kwargs)
    return None

async def _show_subscription_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await show_payment_plans(update, context)
    except Exception as exc:  # noqa: BLE001
        logger.error("Не удалось открыть тарифы", extra={"error": str(exc)})
        await _reply(
            update,
            context,
            "⚡️ Подписка\n\n"
            "Не удалось загрузить тарифы. Попробуй позже или используй /plans.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ В меню", callback_data="main:menu")]]
            ),
        )


async def _show_referral_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = SessionLocal()
    try:
        user = update.effective_user
        if not user:
            return
        user_service = UserService(db)
        referral_service = ReferralService(db)
        db_user = user_service.get_or_create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
        referral_code = referral_service.create_or_get_referral_code(db_user)
        referral_link = _build_referral_deeplink(referral_code)
        stats = referral_service.get_referral_stats_for_user(db_user)
        message = (
            f"🤝 Реферальная программа\n\n"
            f"Твой код: `{referral_code}`\n"
            f"Ссылка: {referral_link}\n\n"
            f"Статистика:\n"
            f"• Визитов: {stats['visits']}\n"
            f"• Оплачено: {stats['paid_count']}\n"
            f"• Всего сумма: {stats['total_amount']:.0f} ₽\n"
            f"• Баланс: {stats['balance']:.0f} ₽"
        )
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Скопировать ссылку", url=referral_link),
                ],
                [InlineKeyboardButton("⬅️ В меню", callback_data="main:menu")],
            ]
        )
        await _reply(update, context, message, reply_markup=keyboard, parse_mode="Markdown")
    finally:
        db.close()


MAIN_MENU_BUTTON_TEXT = "Главное меню 🐱"
_MAIN_REPLY_KEYBOARD_FLAG = "wai_main_reply_keyboard_sent"
_MAIN_REPLY_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton(MAIN_MENU_BUTTON_TEXT)]],
    resize_keyboard=True,
    one_time_keyboard=False,
    selective=True,
    input_field_placeholder="Нажми кнопку, чтобы открыть главное меню",
)


async def maybe_send_main_reply_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет клавиатуру с кнопкой 'Главное меню 🐱', если её ещё не показывали."""
    if context.chat_data.get(_MAIN_REPLY_KEYBOARD_FLAG):
        return
    chat_id = getattr(update.effective_chat, "id", None)
    if not chat_id:
        return
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Нажмите кнопку «Главное меню 🐱», чтобы быстро вернуться в меню в любой момент.",
            reply_markup=_MAIN_REPLY_KEYBOARD,
            disable_notification=True,
        )
        context.chat_data[_MAIN_REPLY_KEYBOARD_FLAG] = True
    except Exception as exc:  # noqa: BLE001
        logger.debug("Не удалось отправить клавиатуру главного меню", exc_info=True, extra={"error": str(exc)})


async def wai_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ensure_state(context.user_data)
    first_name = (getattr(update.effective_user, "first_name", None) or "котик").strip()
    welcome = (
        "🐱 **Мяу! Добро пожаловать в Cyberkitty19 Transkribator!**\n\n"
        f"Привет, {first_name}! Я котик, который помогает превращать видео в заметки и держать всё под лапкой.\n\n"
        "🎬 **Что я умею:**\n"
        "• Расшифровываю видео и аудио в текст  \n"
        "• Форматирую заметки и делаю краткие и длинные саммори  \n"
        "• Нахожу и обновляю заметки через встроенного ИИ‑агента\n"
        "• Через поиск по заметкам отвечаю осмысленно из всего контекста\n\n"
        "Совет: «Чтобы продолжить работу, отправьте в чат новый файл или ссылку!»"
    )
    await _reply(
        update,
        context,
        welcome,
        parse_mode="Markdown",
        reply_markup=_main_menu(),
    )
    await maybe_send_main_reply_keyboard(update, context)


async def wai_handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query:
        await query.answer()
    data = (query.data if query else "") if hasattr(query, "data") else ""
    state = _ensure_state(context.user_data)

    if data == "main:menu":
        await _reply(update, context, "Главное меню", reply_markup=_main_menu())
        return

    if data == "main:subscription":
        await _show_subscription_menu(update, context)
        return

    if data == "main:referral":
        await _show_referral_info(update, context)
        return

    if data == "main:search":
        await manual_vector_chat_command(update, context)
        return

    if data == "main:help":
        await _reply(
            update,
            context,
            "📚 Помощь и FAQ\n\n"
            "Как начать: отправьте файл или ссылку и дождитесь результата.\n"
            "Как задавать вопросы: нажмите кнопку «🔎 Задать вопросы» после транскрипции.\n"
            "Команды: /start, /questions, /help.\n"
            "Если нужна помощь, напишите текстово — бот отвечает как обычный чат-ИИ.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ В меню", callback_data="main:menu")]]),
        )
        return

    if data == "subscription:cancel":
        await _reply(
            update,
            context,
            "Автоплатёж отменён. Текущий период сохранён до конца.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ В меню", callback_data="main:menu")]]),
        )
        return

    # Fallback
    await _reply(update, context, "Выбери пункт меню.", reply_markup=_main_menu())


async def wai_start_hint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветствие + меню (для /start хука)."""
    await wai_menu_command(update, context)


async def wai_progress_placeholder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сообщение при приёме файла/ссылки."""
    return await _reply(
        update,
        context,
        "Файл принят! Ожидайте обработки...\n[██████--------------] 30%",
    )


def _shorten(text: str | None, limit: int = 280) -> str | None:
    if not text:
        return None
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


async def send_result_card(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    summary: str | None = None,
    source_url: str | None = None,
    extra_lines: list[str] | None = None,
) -> None:
    """Отправляет финальную карточку после обработки файла."""

    summary_line = _shorten(summary, 320)
    message_parts: list[str] = ["✅ Обработка завершена!"]
    if summary_line:
        message_parts.append(f"📝 {summary_line}")
    if source_url:
        message_parts.append(f"🔗 Источник: {source_url}")
    if extra_lines:
        cleaned = [line.strip() for line in extra_lines if line and line.strip()]
        if cleaned:
            message_parts.append("\n".join(cleaned))
    message_parts.append("Можно задать вопросы по материалу или вернуться в меню.")

    buttons: list[list[InlineKeyboardButton]] = []
    if source_url:
        buttons.append([InlineKeyboardButton("🌐 Открыть источник", url=source_url)])
    buttons.append([InlineKeyboardButton("💬 Задать вопросы", callback_data="manual:menu")])
    buttons.append([InlineKeyboardButton("🏠 Главное меню", callback_data="wai:menu")])

    await _reply(
        update,
        context,
        "\n\n".join(message_parts),
        reply_markup=InlineKeyboardMarkup(buttons),
        disable_web_page_preview=True,
    )
