import json
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from transkribator_modules.config import logger, ADMIN_IDS
from transkribator_modules.db.database import (
    SessionLocal, UserService, ApiKeyService, TransactionService, PromoCodeService
)
from transkribator_modules.db.models import ApiKey, PlanType

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    welcome_text = f"""🐱 **Мяу! Добро пожаловать в CyberKitty Transkribator!**

Привет, {user.first_name or 'котик'}! Я умный котик-транскрибатор! 

🎬 Просто отправь мне видео — я сделаю всё сам!

✨ Что я умею:
• 📝 Превращаю речь в текст
• 🤖 Делаю красивое форматирование с ИИ  
• 📋 Создаю краткие и подробные саммари
• 🔄 Работаю с файлами любого размера

🚀 Начинаем?
1️⃣ Отправь мне видео (любой формат)
2️⃣ Выбери тип обработки  
3️⃣ Получи готовую транскрипцию!

*мурчит и готов к работе  🐾*"""
    keyboard = [
        [InlineKeyboardButton("📖 Как пользоваться", callback_data="show_tutorial")],
        [InlineKeyboardButton("🏠 Личный кабинет", callback_data="personal_cabinet")],
        [InlineKeyboardButton("👥 Добавить в группу", callback_data="add_to_group")],
        [InlineKeyboardButton("💸 Реферальная программа", callback_data="show_referral")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

async def plans_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /plans - показать тарифные планы"""
    from transkribator_modules.bot.payments import show_payment_plans
    await show_payment_plans(update, context)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /stats - статистика пользователя"""
    await personal_cabinet_command(update, context)

async def api_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /api - управление API ключами"""
    user = update.effective_user
    
    db = SessionLocal()
    try:
        user_service = UserService(db)
        db_user = user_service.get_or_create_user(telegram_id=user.id)
        
        if db_user.current_plan not in ["pro", "unlimited"]:
            await update.message.reply_text(
                "🔐 API доступ доступен только для планов 💎 Профессиональный и 🚀 Безлимитный\n\n"
                "😿 *грустно мяукает*"
            )
            return
            
        # Показываем API ключи через callback
        from transkribator_modules.bot.callbacks import show_api_keys_callback
        await show_api_keys_callback(None, user)
        
    finally:
        db.close()

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /help - перенаправляет на show_tutorial"""
    await show_tutorial(update, context)

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

        if usage_info['minutes_limit']:
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
            [InlineKeyboardButton("⭐ Купить план", callback_data="show_plans_from_cabinet")],
        ]
        
        # API ключи только для Pro+ планов
        if db_user.current_plan in ["pro", "unlimited"]:
            keyboard.append([InlineKeyboardButton("🔑 API ключи", callback_data="show_api_keys")])
          
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="show_help")])
        
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

async def promo_codes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Управление промокодами"""
    user = update.effective_user
    
    # Если есть аргумент команды (промокод)
    if context.args and len(context.args) > 0:
        promo_code = context.args[0].upper()
        await activate_promo_code(update, context, promo_code)
        return
    
    db = SessionLocal()
    try:
        user_service = UserService(db)
        promo_service = PromoCodeService(db)
        
        db_user = user_service.get_or_create_user(telegram_id=user.id)
        active_promos = promo_service.get_user_active_promos(db_user)
        
        promo_text = f"""🎁 **Промокоды**

Здесь ты можешь активировать промокоды и посмотреть уже активированные!

💡 **Как использовать:**
Введи промокод в поле ниже или используй команду:
`/promo ТВОЙ_ПРОМОКОД`

🎯 **Где взять промокоды?**
• В социальных сетях разработчика
• В специальных акциях и розыгрышах
• За активность в сообществе

😸 *Следи за новостями, чтобы не пропустить!*"""

        if active_promos:
            promo_text += f"\n\n🎉 **Твои активные промокоды:**"
            for promo in active_promos:
                expires_text = ""
                if promo.expires_at:
                    if promo.expires_at > datetime.utcnow():
                        days_left = (promo.expires_at - datetime.utcnow()).days
                        expires_text = f" (ещё {days_left} дн.)"
                    else:
                        expires_text = " (истек)"
                else:
                    expires_text = " (бессрочно 🎉)"
                
                promo_text += f"\n• {promo.promo_code.description}{expires_text}"
        
        promo_text += f"\n\n😸 *предвкушающе мурчит*"

        keyboard = [
            [InlineKeyboardButton("✏️ Ввести промокод", callback_data="enter_promo_code")],
            [InlineKeyboardButton("🔙 Назад", callback_data="personal_cabinet")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                promo_text, reply_markup=reply_markup, parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                promo_text, reply_markup=reply_markup, parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"Ошибка в промокодах: {e}")
        error_text = "😿 Ошибка при загрузке промокодов. *расстроенно мяукает*"
        
        if update.callback_query:
            await update.callback_query.edit_message_text(error_text)
        else:
            await update.message.reply_text(error_text)
    finally:
        db.close()

async def activate_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE, promo_code: str) -> None:
    """Активация промокода"""
    user = update.effective_user
    
    db = SessionLocal()
    try:
        user_service = UserService(db)
        promo_service = PromoCodeService(db)
        
        db_user = user_service.get_or_create_user(telegram_id=user.id)
        
        # Валидируем промокод
        is_valid, message, promo = promo_service.validate_promo_code(promo_code, db_user)
        
        if not is_valid:
            await update.message.reply_text(message)
            return
        
        # Активируем промокод
        activation = promo_service.activate_promo_code(promo, db_user)
        
        # Формируем сообщение об успехе
        duration_text = ""
        if promo.duration_days:
            duration_text = f" на {promo.duration_days} дней"
        else:
            duration_text = " навсегда"
        
        success_text = f"""🎉 **Промокод активирован!**

{promo.description}

✨ **Твой новый план:** 🚀 Безлимитный{duration_text}

🎁 **Что теперь доступно:**
• Безлимитные минуты транскрибации
• Файлы любого размера  
• VIP поддержка
• Все функции сервиса

😻 *счастливо мурчит и делает кульбит*"""

        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data="personal_cabinet")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(success_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка при активации промокода: {e}")
        await update.message.reply_text("😿 Ошибка при активации промокода. *грустно мяукает*")
    finally:
        db.close()

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда для проверки статуса сервисов"""
    status_text = """🔧 **Статус сервисов Cyberkitty19 Transkribator**

🤖 **Бот:** ✅ Работает
🌐 **API сервер:** ✅ Активен
🔧 **Система транскрибации:** ✅ Готов
💾 **База данных:** ✅ Подключена

😸 *все системы мурчат исправно*"""
    
    await update.message.reply_text(status_text, parse_mode='Markdown')

# ----------------------------------------------------------------------------
# 📢 Рассылка сообщений администраторами
# ----------------------------------------------------------------------------

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/broadcast <текст> – рассылает сообщение всем активным пользователям (30 дн.)."""

    # Проверяем права
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("🚫 У вас нет прав для этой команды.")
        return

    # Определяем текст рассылки
    text = " ".join(context.args) if context.args else None

    # Если текста нет, но команда была как ответ на сообщение – берём его
    if not text and update.message.reply_to_message and update.message.reply_to_message.text:
        text = update.message.reply_to_message.text

    if not text:
        await update.message.reply_text("Использование: /broadcast <текст> или ответьте на сообщение командой.")
        return

    await update.message.reply_text("🔄 Начинаю рассылку…")

    # Собираем пользователей
    from datetime import timedelta, datetime
    db = SessionLocal()
    sent = 0
    try:
        user_service = UserService(db)
        users = user_service.get_active_users(days=30)

        for user in users:
            try:
                await context.bot.send_message(chat_id=user.telegram_id, text=text, parse_mode='Markdown')
                sent += 1
                await asyncio.sleep(0.05)  # мелкая пауза
            except Exception as e:
                logger.warning(f"Не удалось отправить сообщение пользователю {user.telegram_id}: {e}")

        await update.message.reply_text(f"✅ Рассылка завершена. Отправлено {sent} пользователям.")

    finally:
        db.close()

async def raw_transcript_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда для получения сырой транскрибации"""
    await update.message.reply_text(
        "🎬 Отправь мне видео с этой командой, и я верну только сырую транскрибацию без форматирования!\n\n"
        "😺 *готовится к быстрой работе*"
    )

async def show_tutorial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Подробная инструкция по использованию бота"""
    tutorial_text = """🎬 **Как пользоваться CyberKitty**

🎬 Отправь мне видео, аудио, файл, ссылку, я всё прочитаю и верну обработанный текст. Потом могу из него сделать краткое/подробное саммори или вернуть необработанную транскрипцию (если так больше нравится, но они обычно хуже)

Если есть вопросы, предложения, или какой-нибудь тип файла/ссылки не прочитался - пиши @like\\_a\\_duck, он поможет."""

    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="show_help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(tutorial_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(tutorial_text, reply_markup=reply_markup, parse_mode='Markdown') 

async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = "💸 *Реферальная программа скоро появится!*\n\nТы сможешь приглашать друзей и получать бонусы за их регистрацию и покупки. Следи за новостями!"
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="show_help")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown') 