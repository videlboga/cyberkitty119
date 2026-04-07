import json
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from transkribator_modules.config import logger, MINIAPP_EFFECTIVE_URL
from transkribator_modules.db.database import (
    SessionLocal,
    UserService,
    ApiKeyService,
    TransactionService,
    PromoCodeService,
    ReferralService,
    log_event,
)
from transkribator_modules.db.models import ApiKey, PlanType
from transkribator_modules.utils.event_logging import log_user_action
from transkribator_modules.bot.logging_utils import trace_handler, log_step
from transkribator_modules.wai_flow import wai_menu_command


def _get_target_message(update: Update):
    if update.message:
        return update.message
    if update.callback_query:
        return update.callback_query.message
    return None


async def _reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, **kwargs):
    message = _get_target_message(update)
    if message:
        return await message.reply_text(text, **kwargs)
    if update.callback_query:
        return await context.bot.send_message(chat_id=update.effective_user.id, text=text, **kwargs)
    return None

@log_user_action("bot_command_start")
@trace_handler("command:/start")
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start: показываем нужное главное меню (как по кнопке Назад)."""
    context.chat_data.pop("last_transcription_result", None)
    context.chat_data.pop("qa_session", None)
    usage_reset = False
    was_created = False
    referral_bonus_applied = False
    referral_code: Optional[str] = None
    
    start_payload = None
    if context.args:
        start_payload = context.args[0]
    elif update.message and update.message.text:
        parts = update.message.text.strip().split(maxsplit=1)
        if len(parts) > 1:
            start_payload = parts[1]
    if start_payload:
        start_payload = start_payload.strip()
        if start_payload.lower().startswith("ref="):
            referral_code = start_payload[4:]
        elif start_payload.lower().startswith("ref_"):
            referral_code = start_payload[4:]
    if referral_code:
        referral_code = referral_code.strip()

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "http://host.docker.internal:8002/api/v1/auth/tg/start",
                json={
                    "telegram_id": update.effective_user.id,
                    "username": update.effective_user.username,
                    "first_name": update.effective_user.first_name,
                    "last_name": update.effective_user.last_name,
                    "referral_code": referral_code
                }
            )
            resp.raise_for_status()
            data = resp.json()
            
            was_created = data.get("is_new_user", False)
            usage_reset = data.get("usage_reset", False)
            referral_bonus_applied = data.get("referral_bonus_applied", False)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Start command: failed to init user through Core API",
            extra={"user_id": update.effective_user.id, "error": str(exc)},
        )

    await wai_menu_command(update, context)

    if referral_bonus_applied:
        await _reply(
            update,
            context,
            "🎉 Реферальный бонус активирован: 14 дней плана «Реферал». Загляни в личный кабинет, чтобы увидеть новые лимиты!",
        )
    elif was_created:
        await _reply(
            update,
            context,
            "🎁 В бесплатном тарифе доступны 3 видео в месяц. Используй их, чтобы попробовать все возможности.",
        )
    elif usage_reset:
        await _reply(
            update,
            context,
            "🔄 Лимит бесплатного тарифа обновился — снова доступны 3 бесплатные загрузки на этот месяц.",
        )
    elif referral_code:
        await _reply(
            update,
            context,
            "💌 Ты пришёл по реферальной ссылке — подарок уже активирован: 14 дней плана «Реферал». Наслаждайся расширенными возможностями!",
        )

@trace_handler("command:/help")
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    help_text = """📖 **Справка по CyberKitty Transkribator**

**Основные возможности:**
• Транскрипция видео и аудио файлов
• Поддержка файлов до 2 ГБ
• Автоматическое извлечение аудио из видео
• ИИ-форматирование текста
• Система подписок и бонусов

**Команды:**
/start - Начать работу
/help - Показать эту справку
/status - Проверить статус бота
/backlog - Разобрать заметки из бэклога
/plans - Показать тарифные планы
/stats - Статистика использования
/promo - Промокоды

**Поддерживаемые форматы:**

🎥 **Видео:** MP4, AVI, MOV, MKV, WebM, FLV, WMV, M4V, 3GP
🎵 **Аудио:** MP3, WAV, FLAC, AAC, OGG, M4A, WMA, OPUS

**Ограничения:**
• Максимальный размер файла: 2 ГБ
• Максимальная длительность: 4 часа

**Как это работает:**
1. Вы отправляете файл
2. Если это видео - я извлекаю аудио
3. Аудио отправляется в AI API для транскрипции
4. Текст форматируется с помощью LLM
5. Вы получаете готовую транскрипцию

Просто отправьте файл и я начну обработку! 🚀"""

    await _reply(update, context, help_text, parse_mode='Markdown')

@trace_handler("command:/status")
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /status"""
    status_text = """✅ **Статус CyberKitty Transkribator**

🤖 Бот: Активен
🌐 Telegram Bot API Server: Активен
🎵 Обработка аудио: Доступна
🎥 Обработка видео: Доступна
🧠 ИИ транскрипция: Подключена
📝 ИИ форматирование: Активно
💎 Система платежей: Активна

**Настройки:**
• Макс. размер файла: 2 ГБ
• Макс. длительность: 4 часа
• Форматы видео: 9 поддерживаемых
• Форматы аудио: 8 поддерживаемых

Готов к работе! 🚀"""

    await _reply(update, context, status_text, parse_mode='Markdown')

@trace_handler("command:/raw_transcript")
async def raw_transcript_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /rawtranscript"""
    help_text = """📝 **Получение сырой транскрипции**

После обработки файла вы можете получить необработанную транскрипцию,
нажав кнопку "Сырая транскрипция" в сообщении с результатом.

**Что это дает:**
• Исходный текст без ИИ-обработки
• Полная версия без сокращений
• Возможность самостоятельной обработки

**Как использовать:**
1. Отправьте файл для транскрипции
2. Получите обработанный результат
3. Нажмите кнопку "Сырая транскрипция"
4. Получите исходный текст

Удобно для дальнейшей обработки! 🔧"""

    await _reply(update, context, help_text, parse_mode='Markdown')

@trace_handler("command:/plans")
async def plans_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /plans"""
    try:
        log_event(update.effective_user.id, "bot_command_plans", {
            "chat_id": update.effective_chat.id if update.effective_chat else None
        })
    except Exception:
        logger.debug("Failed to log /plans event", exc_info=True)
    
    from transkribator_modules.bot.payments import show_payment_plans
    await show_payment_plans(update, context)

@trace_handler("command:/buy")
async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /buy — быстрый переход к покупке."""
    try:
        log_event(update.effective_user.id, "bot_command_buy", {
            "chat_id": update.effective_chat.id if update.effective_chat else None
        })
    except Exception:
        logger.debug("Failed to log /buy event", exc_info=True)
    
    from transkribator_modules.bot.payments import show_payment_plans
    await show_payment_plans(update, context)

@trace_handler("command:/stats")
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /stats"""
    try:
        log_event(update.effective_user.id, "bot_command_stats", {
            "chat_id": update.effective_chat.id if update.effective_chat else None
        })
    except Exception:
        logger.debug("Failed to log /stats event", exc_info=True)
    
    try:
        from transkribator_modules.db.database import get_user_stats
        user_id = update.effective_user.id
        stats = get_user_stats(user_id)

        stats_text = f"""📊 **Ваша статистика**

🎯 **Основные показатели:**
• Обработано файлов: {stats.get('files_processed', 0)}
• Минут транскрибировано: {stats.get('minutes_transcribed', 0)}
• Последний раз: {stats.get('last_activity', 'Никогда')}

💎 **Подписка:**
• Статус: {stats.get('subscription_status', 'Бесплатный')}
• Остаток файлов: {stats.get('files_remaining', 'Безлимит')}
• Действует до: {stats.get('subscription_until', 'Не ограничено')}

📈 **Достижения:**
• Всего символов: {stats.get('total_characters', 0)}
• Средняя длительность: {stats.get('avg_duration', 0)} мин

Спасибо за использование CyberKitty Transkribator! 🐱"""

        await _reply(update, context, stats_text, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        await _reply(update, context, "❌ Не удалось получить статистику. Попробуйте позже.")


@trace_handler("command:/timezone")
async def timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        log_event(update.effective_user.id, "bot_command_timezone", {
            "chat_id": update.effective_chat.id if update.effective_chat else None,
            "has_args": bool(context.args)
        })
    except Exception:
        logger.debug("Failed to log /timezone event", exc_info=True)
    
    args = context.args
    if not args:
        await _reply(
            update,
            context,
            "Укажи часовой пояс. Пример: /timezone Europe/Moscow\n"
            "Полный список: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones",
        )
        return

    tz_name = args[0]
    try:
        ZoneInfo(tz_name)
    except Exception:
        await _reply(
            update,
            context,
            "Не понял часовой пояс. Используй формат вроде Europe/Moscow или America/New_York.",
        )
        return

    db = SessionLocal()
    try:
        user_service = UserService(db)
        user = user_service.get_or_create_user(
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
            last_name=update.effective_user.last_name,
        )
        user_service.set_timezone(user, tz_name)
    except Exception as exc:  # noqa: BLE001
        logger.error("Timezone update failed", extra={"user_id": update.effective_user.id, "error": str(exc)})
        await _reply(update, context, "Не удалось сохранить часовой пояс. Попробуй позже.")
    else:
        await _reply(update, context, f"Часовой пояс сохранён: {tz_name}")
    finally:
        db.close()


@trace_handler("command:/backlog")
async def backlog_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Историческая команда — сейчас просто рассказываем, что функция недоступна."""
    await _reply(
        update,
        context,
        "Бэклог временно недоступен. В новой версии бота весь фокус на стандартной обработке файлов.",
    )

@trace_handler("command:/api")
async def api_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /api"""
    try:
        log_event(update.effective_user.id, "bot_command_api", {
            "chat_id": update.effective_chat.id if update.effective_chat else None
        })
    except Exception:
        logger.debug("Failed to log /api event", exc_info=True)
    
    api_text = """🔌 **API интеграция**

**Скоро будет доступно:**
• REST API для транскрипции
• Webhook уведомления
• Интеграция с внешними сервисами
• Массовая обработка файлов

**Планируемые возможности:**
• Загрузка по URL
• Пакетная обработка
• Приоритетная очередь
• Детальная аналитика

Следите за обновлениями! 🚀

*API будет доступен для пользователей с PRO подпиской*"""

    await _reply(update, context, api_text, parse_mode='Markdown')

@trace_handler("command:/promo")
async def promo_codes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /promo"""
    try:
        log_event(update.effective_user.id, "bot_command_promo", {
            "chat_id": update.effective_chat.id if update.effective_chat else None,
            "has_args": bool(context.args)
        })
    except Exception:
        logger.debug("Failed to log /promo event", exc_info=True)
    
    if not context.args:
        promo_text = """🎁 **Промокоды**

**Как использовать:**
Отправьте `/promo [код]` для активации промокода

**Примеры:**
• `/promo WELCOME10` - скидка 10%
• `/promo PREMIUM30` - 30 дней PRO бесплатно

**Где найти промокоды:**
• Наш Telegram канал
• Рассылка новостей
• Специальные акции

Следите за обновлениями для получения новых промокодов! 🔥"""

        await update.message.reply_text(promo_text, parse_mode='Markdown')
        return

    promo_code = context.args[0].upper()

    try:
        from transkribator_modules.db.database import activate_promo_code
        user_id = update.effective_user.id
        result = activate_promo_code(user_id, promo_code)

        if result['success']:
            await update.message.reply_text(
                f"🎉 **Промокод активирован!**\n\n"
                f"**Бонус:** {result['bonus']}\n"
                f"**Действует до:** {result['expires']}\n\n"
                f"Спасибо за использование CyberKitty Transkribator! 🐱",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"❌ **Ошибка активации промокода**\n\n"
                f"Причина: {result['error']}\n\n"
                f"Проверьте правильность ввода кода.",
                parse_mode='Markdown'
            )

    except Exception as e:
        logger.error(f"Ошибка при активации промокода: {e}")
        await update.message.reply_text(
            "❌ Не удалось активировать промокод. Попробуйте позже."
        )

@trace_handler("command:/personal_cabinet")
async def personal_cabinet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Личный кабинет пользователя"""
    try:
        log_event(update.effective_user.id, "bot_command_cabinet", {
            "chat_id": update.effective_chat.id if update.effective_chat else None
        })
    except Exception:
        logger.debug("Failed to log /cabinet event", exc_info=True)
    
    user = update.effective_user

    import httpx
    try:
        # STRANGLER PATTERN: Call the new Core API for user profile
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"http://host.docker.internal:8002/api/v1/system/profile/tg/{user.id}",
                params={"first_name": user.first_name or "", "last_name": user.last_name or ""}
            )
            resp.raise_for_status()
            data = resp.json()

        cabinet_text = f"""🐱 **Личный кабинет**\n\n👤 **Профиль:**\n• Имя: {data["first_name"] or "Котик"} {data["last_name"] or ""}\n• План: {data["plan_display_name"]} {data["plan_status_text"]}\n\n📊 **Использование в этом месяце:**"""

        if data["current_plan"] == "free":
            remaining = data["generations_remaining"]
            percentage = data["usage_percentage"]
            progress_bar = "🟩" * int(percentage // 10) + "⬜" * (10 - int(percentage // 10))
            cabinet_text += f"""\n• Использовано: {data["generations_used_this_month"]} из {data["generations_limit"]} генераций\n• Осталось: {remaining} генераций\n{progress_bar} {percentage:.1f}%"""
        elif data["minutes_limit"]:
            remaining = data["minutes_remaining"]
            percentage = data["usage_percentage"]
            progress_bar = "🟩" * int(percentage // 10) + "⬜" * (10 - int(percentage // 10))
            cabinet_text += f"""\n• Использовано: {data["minutes_used_this_month"]:.1f} из {data["minutes_limit"]:.0f} мин\n• Осталось: {remaining:.1f} мин\n{progress_bar} {percentage:.1f}%"""
        else:
            cabinet_text += f"""\n• Использовано: {data["minutes_used_this_month"]:.1f} мин\n• Лимит: Безлимитно ♾️"""

        cabinet_text += f"\n\n📈 **Всего транскрибировано:** {data["total_minutes_transcribed"]:.1f} мин\n"

        active_promos = data.get("active_promos", [])
        if active_promos:
            cabinet_text += f"\n\n🎁 **Активные промокоды:**"
            from datetime import datetime
            for p in active_promos[:3]:
                expires_text = ""
                if p.get("expires_at"):
                    try:
                        exp = datetime.fromisoformat(p["expires_at"].replace("Z", "+00:00")).replace(tzinfo=None)
                        days_left = (exp - datetime.utcnow()).days
                        expires_text = f" (ещё {days_left} дн.)"
                    except Exception:
                        pass
                cabinet_text += f"\n• [{p["code"]}] -{p["discount_percent"]}%{expires_text}"

        cabinet_text += "\n\n🐾 *мурчит довольно*"

    except Exception as e:
        import logging
        logging.error(f"Core API request failed for profile: {e}")
        cabinet_text = "❌ Не удалось загрузить профиль. (API Runtime Error)"


        # Кнопки меню
        keyboard = [
            [InlineKeyboardButton("📊 Статистика", callback_data="show_stats")],
            [InlineKeyboardButton("🎁 Промокоды", callback_data="show_promo_codes")],
            [InlineKeyboardButton("⭐ Купить план", callback_data="show_payment_plans")],
        ]

        # API ключи только для Pro+ планов
        if db_user.current_plan in ["pro", "unlimited"]:
            keyboard.append([InlineKeyboardButton("🔑 API ключи", callback_data="show_api_keys")])

        keyboard.append([InlineKeyboardButton("💡 Помощь", callback_data="show_help")])

        # MiniApp доступен всегда (даём прямую ссылку)
        try:
            if MINIAPP_EFFECTIVE_URL:
                keyboard.append([InlineKeyboardButton("🗂 Открыть MiniApp", url=MINIAPP_EFFECTIVE_URL)])
        except Exception:
            logger.debug("Не удалось добавить кнопку MiniApp в личный кабинет", exc_info=True)

        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.callback_query:
            await update.callback_query.edit_message_text(
                cabinet_text, reply_markup=reply_markup, parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                cabinet_text, reply_markup=reply_markup, parse_mode='Markdown'
            )

    except Exception as e:
        logger.error(f"Ошибка в личном кабинете: {e}")
        error_text = "😿 Произошла ошибка при загрузке кабинета. *грустно мяукает*"

        if update.callback_query:
            await update.callback_query.edit_message_text(error_text)
        else:
            await update.message.reply_text(error_text)
    finally:
        db.close()
