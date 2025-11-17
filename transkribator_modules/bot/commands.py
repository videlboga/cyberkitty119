import json
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from transkribator_modules.config import logger, FEATURE_BETA_MODE
from transkribator_modules.db.database import (
    SessionLocal,
    UserService,
    ApiKeyService,
    TransactionService,
    PromoCodeService,
    NoteService,
    ReferralService,
    log_event,
)
from transkribator_modules.beta.reminders import REMINDER_KEYBOARD
from transkribator_modules.db.models import ApiKey, PlanType
from transkribator_modules.utils.event_logging import log_user_action


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
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start: показываем нужное главное меню (как по кнопке Назад)."""
    db = SessionLocal()
    usage_reset = False
    was_created = False
    referral_bonus_applied = False
    referral_code: Optional[str] = None
    try:
        user_service = UserService(db)
        db_user = user_service.get_or_create_user(
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
            last_name=update.effective_user.last_name,
        )
        usage_info = user_service.get_usage_info(db_user)
        usage_reset = bool(getattr(db_user, "_usage_reset", False))
        was_created = bool(getattr(db_user, "_was_created", False))
        setattr(db_user, "_usage_reset", False)
        setattr(db_user, "_was_created", False)

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
        if referral_code:
            referral_service = ReferralService(db)
            try:
                referral_service.record_referral_visit(referral_code, update.effective_user.id)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to record referral visit",
                    extra={"telegram_id": update.effective_user.id, "code": referral_code, "error": str(exc)},
                )
            try:
                referral_service.attribute_user_referral(update.effective_user.id, referral_code)
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "Failed to attribute referral user",
                    extra={"telegram_id": update.effective_user.id, "code": referral_code, "error": str(exc)},
                )
            if was_created:
                try:
                    referral_bonus_applied = referral_service.apply_referral_welcome_bonus(db_user)
                    if referral_bonus_applied:
                        usage_info = user_service.get_usage_info(db_user)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to apply referral bonus on /start",
                        extra={
                            "user_id": db_user.id,
                            "telegram_id": update.effective_user.id,
                            "code": referral_code,
                            "error": str(exc),
                        },
                    )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Start command: failed to init user",
            extra={"user_id": update.effective_user.id, "error": str(exc)},
        )
        usage_info = None
    finally:
        db.close()

    # Если пользователь впервые создан — залогируем отдельное событие регистрации
    if was_created:
        try:
            log_event(update.effective_user.id, "user_registered", {
                "telegram_id": update.effective_user.id,
                "username": update.effective_user.username,
            })
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to log user_registered", extra={"error": str(exc)})

    first_name = update.effective_user.first_name or 'котик'
    welcome_text = f"""🐱 **Мяу! Добро пожаловать в Cyberkitty19 Transkribator!**

Привет, {first_name}! Я котик, который помогает превращать видео в заметки и держать всё под лапкой.

🎬 **Что я умею:**
• Расшифровываю видео и аудио в текст  
• Форматирую заметки и делаю краткие и длинные саммори  
• Веду задачи и записи вместе с миниаппом **«Журнал»**  
• Нахожу и обновляю заметки через встроенного ИИ‑агента

🚀 **Как работать:**
1. Отправь мне видео или аудио — я создам заметку автоматически.  
2. Спроси агента — он найдёт нужную запись или подготовит новую.  
3. Открой миниапп **«Журнал»**, чтобы просматривать и редактировать заметки в Telegram.

💡 **Готов начать?**  
Нажми кнопку ниже, чтобы открыть личный кабинет и «Журнал», или просто пришли мне видео.

*мурчит и готов к новым заметкам* 🐾"""

    keyboard = [
        [InlineKeyboardButton("🏠 Личный кабинет", callback_data="personal_cabinet")],
        [InlineKeyboardButton("⭐ Купить подписку", callback_data="show_payment_plans")],
        [InlineKeyboardButton("💡 Помощь", callback_data="show_help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await _reply(update, context, welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

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


async def backlog_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать пользователю заметки из бэклога и предложить разобрать их."""
    try:
        log_event(update.effective_user.id, "bot_command_backlog", {
            "chat_id": update.effective_chat.id if update.effective_chat else None
        })
    except Exception:
        logger.debug("Failed to log /backlog event", exc_info=True)

    if not FEATURE_BETA_MODE:
        await _reply(update, context, "Бэклог доступен в новом бета-режиме. Ожидайте обновлений!")
        return

    db = SessionLocal()
    try:
        user_service = UserService(db)
        note_service = NoteService(db)

        user = user_service.get_or_create_user(
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
            last_name=update.effective_user.last_name,
        )

        if not user_service.is_beta_enabled(user):
            await _reply(update, context, "Включи бета-режим в личном кабинете, чтобы работать с бэклогом.")
            return

        backlog_notes = note_service.list_backlog(user, limit=5)
        if not backlog_notes:
            await _reply(update, context, "Бэклог пуст — можно отдыхать! 💤")
            return

        lines = []
        for note in backlog_notes:
            snippet = note.summary or (note.text or '')
            snippet = (snippet or '').strip().replace('\n', ' ')
            if len(snippet) > 80:
                snippet = snippet[:77] + '…'
            lines.append(f"• {snippet or 'без текста'}")

        text = "У тебя есть заметки в бэклоге. Разберём 5 сейчас?\n\n" + "\n".join(lines)
        await _reply(update, context, text, reply_markup=REMINDER_KEYBOARD, disable_web_page_preview=True)
    finally:
        db.close()

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

async def personal_cabinet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Личный кабинет пользователя"""
    try:
        log_event(update.effective_user.id, "bot_command_cabinet", {
            "chat_id": update.effective_chat.id if update.effective_chat else None
        })
    except Exception:
        logger.debug("Failed to log /cabinet event", exc_info=True)
    
    user = update.effective_user

    db = SessionLocal()
    try:
        user_service = UserService(db)
        promo_service = PromoCodeService(db)

        db_user = user_service.get_or_create_user(telegram_id=user.id)
        usage_info = user_service.get_usage_info(db_user)
        active_promos = promo_service.get_user_active_promos(db_user)

        # Определяем статус тарифа
        plan_status = ""
        if db_user.plan_expires_at:
            if db_user.plan_expires_at > datetime.utcnow():
                days_left = (db_user.plan_expires_at - datetime.utcnow()).days
                plan_status = f"(истекает через {days_left} дн.)"
            else:
                plan_status = "(истек)"
        elif db_user.current_plan != "free":
            plan_status = "(бессрочно 🎉)"

        cabinet_text = f"""🐱 **Личный кабинет**

👤 **Профиль:**
• Имя: {user.first_name or 'Котик'} {user.last_name or ''}
• План: {usage_info['plan_display_name']} {plan_status}

📊 **Использование в этом месяце:**"""

        # Для бесплатного тарифа показываем генерации
        if usage_info['current_plan'] == 'free':
            remaining = usage_info['generations_remaining']
            percentage = usage_info['usage_percentage']
            progress_bar = "🟩" * int(percentage // 10) + "⬜" * (10 - int(percentage // 10))

            cabinet_text += f"""
• Использовано: {usage_info['generations_used_this_month']} из {usage_info['generations_limit']} генераций
• Осталось: {remaining} генераций
{progress_bar} {percentage:.1f}%"""
        elif usage_info['minutes_limit']:
            remaining = usage_info['minutes_remaining']
            percentage = usage_info['usage_percentage']
            progress_bar = "🟩" * int(percentage // 10) + "⬜" * (10 - int(percentage // 10))

            cabinet_text += f"""
• Использовано: {usage_info['minutes_used_this_month']:.1f} из {usage_info['minutes_limit']:.0f} мин
• Осталось: {remaining:.1f} мин
{progress_bar} {percentage:.1f}%"""
        else:
            cabinet_text += f"""
• Использовано: {usage_info['minutes_used_this_month']:.1f} мин
• Лимит: Безлимитно ♾️"""

        beta_status = "Включен 🟢" if user_service.is_beta_enabled(db_user) else "Выключен ⚪"

        cabinet_text += f"""

📈 **Всего транскрибировано:** {usage_info['total_minutes_transcribed']:.1f} мин

🧪 **Бета-режим:** {beta_status}"""

        # Активные промокоды
        if active_promos:
            cabinet_text += f"\n\n🎁 **Активные промокоды:**"
            for promo in active_promos[:3]:  # Показываем только первые 3
                expires_text = ""
                if promo.expires_at:
                    days_left = (promo.expires_at - datetime.utcnow()).days
                    expires_text = f" (ещё {days_left} дн.)"
                cabinet_text += f"\n• {promo.promo_code.description}{expires_text}"

        cabinet_text += f"\n\n🐾 *мурчит довольно*"

        # Кнопки меню
        keyboard = [
            [InlineKeyboardButton("🐾 БЕТА_СУПЕР_КОТ", callback_data="toggle_beta")],
            [InlineKeyboardButton("📊 Статистика", callback_data="show_stats")],
            [InlineKeyboardButton("🎁 Промокоды", callback_data="show_promo_codes")],
            [InlineKeyboardButton("⭐ Купить план", callback_data="show_payment_plans")],
        ]

        # API ключи только для Pro+ планов
        if db_user.current_plan in ["pro", "unlimited"]:
            keyboard.append([InlineKeyboardButton("🔑 API ключи", callback_data="show_api_keys")])

        keyboard.append([InlineKeyboardButton("💡 Помощь", callback_data="show_help")])

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
