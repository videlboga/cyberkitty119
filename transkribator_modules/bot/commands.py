import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from transkribator_modules.config import logger
from transkribator_modules.db.database import (
    SessionLocal, UserService, ApiKeyService, TransactionService, PromoCodeService
)
from transkribator_modules.db.models import ApiKey, PlanType

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start: показываем нужное главное меню (как по кнопке Назад)."""
    welcome_text = f"""🐱 **Мяу! Добро пожаловать в Cyberkitty19 Transkribator!**

Привет, {update.effective_user.first_name or 'котик'}! Я умный котик-транскрибатор, который превращает твои видео в текст!

🎬 **Что я умею:**
• Транскрибирую видео любого формата в текст
• Форматирую текст с помощью ИИ
• Создаю краткие и подробные саммари
• Работаю с большими файлами через API

🚀 **Как это работает:**
Просто отправь мне видео, и я создам красивую текстовую расшифровку! Можешь выбрать обычную транскрибацию или с ИИ-форматированием.

💡 **Готов начать?**
Нажми кнопку ниже, чтобы войти в личный кабинет, или просто отправь мне видео!

*мурчит и виляет хвостиком* 🐾"""

    keyboard = [
        [InlineKeyboardButton("🏠 Личный кабинет", callback_data="personal_cabinet")],
        [InlineKeyboardButton("⭐ Купить подписку", callback_data="show_payment_plans")],
        [InlineKeyboardButton("💡 Помощь", callback_data="show_help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

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
/plans - Показать тарифные планы
/stats - Статистика использования
/api - API ключи
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

    await update.message.reply_text(help_text, parse_mode='Markdown')

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

    await update.message.reply_text(status_text, parse_mode='Markdown')

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

    await update.message.reply_text(help_text, parse_mode='Markdown')

async def plans_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /plans"""
    from transkribator_modules.bot.payments import show_payment_plans
    await show_payment_plans(update, context)

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /buy — быстрый переход к покупке."""
    from transkribator_modules.bot.payments import show_payment_plans
    await show_payment_plans(update, context)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /stats"""
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

        await update.message.reply_text(stats_text, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        await update.message.reply_text(
            "❌ Не удалось получить статистику. Попробуйте позже."
        )

async def api_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /api"""
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

    await update.message.reply_text(api_text, parse_mode='Markdown')

async def promo_codes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /promo"""
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

        cabinet_text += f"""

📈 **Всего транскрибировано:** {usage_info['total_minutes_transcribed']:.1f} мин"""

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
