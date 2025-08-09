"""
Модуль для работы с платежами в CyberKitty Transkribator
"""

import json
from datetime import datetime, timedelta
from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from transkribator_modules.config import logger
from transkribator_modules.db.database import SessionLocal, UserService, TransactionService
from transkribator_modules.db.models import PlanType

# Цены в Telegram Stars (1 Star ≈ 1.3 рубля)
PLAN_PRICES_STARS = {
    PlanType.BASIC: 760,      # 990 руб ≈ 760 Stars
    PlanType.PRO: 2300,       # 2990 руб ≈ 2300 Stars  
    PlanType.UNLIMITED: 7690  # 9990 руб ≈ 7690 Stars
}

PLAN_DESCRIPTIONS = {
    PlanType.BASIC: {
        "title": "Базовый план",
        "description": "180 минут в месяц, файлы до 200 МБ",
        "features": [
            "180 минут транскрибации в месяц",
            "Файлы до 200 МБ", 
            "Улучшенная транскрибация",
            "Форматирование текста с ИИ"
        ]
    },
    PlanType.PRO: {
        "title": "Профессиональный план", 
        "description": "600 минут в месяц, API доступ, файлы до 500 МБ",
        "features": [
            "600 минут транскрибации в месяц",
            "Файлы до 500 МБ",
            "Приоритетная обработка", 
            "API доступ с ключами",
            "Экспорт в разных форматах"
        ]
    },
    PlanType.UNLIMITED: {
        "title": "Безлимитный план",
        "description": "Безлимитные минуты, файлы до 2 ГБ, расширенный API",
        "features": [
            "Безлимитные минуты транскрибации",
            "Файлы до 2 ГБ",
            "Максимальный приоритет",
            "Расширенный API доступ", 
            "Поддержка 24/7"
        ]
    }
}

async def show_payment_plans(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает доступные тарифные планы."""
    try:
        plans_text = """💎 **Тарифные планы CyberKitty Transkribator**

🆓 **Базовый (Бесплатно)**
• 30 минут транскрипции в месяц
• Файлы до 100 МБ
• Базовая поддержка
• Стандартное качество

⭐ **PRO (299₽/месяц)**
• 10 часов транскрипции в месяц
• Файлы до 2 ГБ
• Приоритетная поддержка
• Высокое качество
• API доступ

🚀 **UNLIMITED (699₽/месяц)**
• Безлимитная транскрипция
• Файлы до 2 ГБ
• VIP поддержка 24/7
• Максимальное качество
• Полный API доступ
• Дополнительные функции ИИ

🎯 **Выберите подходящий план и начните использовать все возможности!**"""

        keyboard = [
            [InlineKeyboardButton("🆓 Остаться на базовом", callback_data="stay_basic")],
            [InlineKeyboardButton("⭐ Купить PRO", callback_data="buy_plan_pro")],
            [InlineKeyboardButton("🚀 Купить UNLIMITED", callback_data="buy_plan_unlimited")],
            [InlineKeyboardButton("🔙 Назад", callback_data="personal_cabinet")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                plans_text, reply_markup=reply_markup, parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                plans_text, reply_markup=reply_markup, parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"Ошибка при показе планов: {e}")
        await update.message.reply_text("❌ Ошибка при загрузке тарифных планов")

async def initiate_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, plan_id: str) -> None:
    """Инициирует процесс оплаты для выбранного плана."""
    try:
        plan_info = {
            "pro": {
                "name": "PRO",
                "price": "299₽",
                "description": "10 часов в месяц + API доступ"
            },
            "unlimited": {
                "name": "UNLIMITED", 
                "price": "699₽",
                "description": "Безлимитно + VIP функции"
            }
        }
        
        if plan_id not in plan_info:
            await update.callback_query.edit_message_text("❌ Неизвестный тарифный план")
            return
        
        plan = plan_info[plan_id]
        
        payment_text = f"""💳 **Оплата тарифного плана {plan['name']}**

📦 **План:** {plan['name']}
💰 **Стоимость:** {plan['price']}
📝 **Описание:** {plan['description']}
⏰ **Период:** 30 дней

🚧 **Интеграция с платежными системами находится в разработке**

**Скоро будет доступно:**
• Оплата банковскими картами
• Оплата через СБП
• Криптовалютные платежи
• Подарочные карты

📧 **По вопросам оплаты:**
Напишите нам @cyberkitty_support

Следите за обновлениями! 🔔"""

        keyboard = [
            [InlineKeyboardButton("📧 Связаться с поддержкой", url="https://t.me/cyberkitty_support")],
            [InlineKeyboardButton("🔙 К тарифам", callback_data="show_payment_plans")],
            [InlineKeyboardButton("🏠 Главная", callback_data="personal_cabinet")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            payment_text, reply_markup=reply_markup, parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Ошибка при инициации платежа: {e}")
        await update.callback_query.edit_message_text("❌ Ошибка при обработке платежа")

async def handle_pre_checkout_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает pre-checkout запросы."""
    try:
        query = update.pre_checkout_query
        
        # Здесь можно добавить дополнительные проверки
        # Например, проверить доступность товара, валидность цены и т.д.
        
        await query.answer(ok=True)
        logger.info(f"Pre-checkout query одобрен для пользователя {query.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка в pre-checkout query: {e}")
        await query.answer(ok=False, error_message="Произошла ошибка при обработке платежа")

async def handle_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает успешные платежи."""
    try:
        payment = update.message.successful_payment
        user_id = update.effective_user.id
        
        logger.info(f"Успешный платеж от пользователя {user_id}: {payment.total_amount/100} {payment.currency}")
        
        # Здесь нужно обновить подписку пользователя в базе данных
        # await update_user_subscription(user_id, payment)
        
        success_text = f"""🎉 **Платеж успешно обработан!**

💳 **Сумма:** {payment.total_amount/100} {payment.currency}
📦 **Товар:** {payment.invoice_payload}
🎯 **ID транзакции:** {payment.telegram_payment_charge_id}

✅ **Ваша подписка активирована!**

**Что теперь доступно:**
• Увеличенные лимиты транскрипции
• Приоритетная обработка файлов
• Расширенная техническая поддержка
• Дополнительные функции ИИ

Спасибо за использование CyberKitty Transkribator! 🐱✨"""

        keyboard = [
            [InlineKeyboardButton("🏠 Личный кабинет", callback_data="personal_cabinet")],
            [InlineKeyboardButton("📊 Статистика", callback_data="show_stats")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            success_text, reply_markup=reply_markup, parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Ошибка при обработке успешного платежа: {e}")
        await update.message.reply_text("❌ Произошла ошибка при активации подписки")

async def handle_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает колбеки связанные с платежами."""
    try:
        query = update.callback_query
        data = query.data
        
        if data == "show_payment_plans":
            await show_payment_plans(update, context)
        elif data.startswith("buy_plan_"):
            plan_id = data.replace("buy_plan_", "")
            await initiate_payment(update, context, plan_id)
        elif data == "stay_basic":
            await query.edit_message_text(
                "👍 Вы остаетесь на базовом тарифе!\n\n"
                "В любой момент можете перейти на PRO или UNLIMITED план "
                "для расширения возможностей. 🚀"
            )
        else:
            await query.edit_message_text("Неизвестная команда платежной системы")
            
    except Exception as e:
        logger.error(f"Ошибка в payment callback: {e}")
        await query.edit_message_text("❌ Ошибка при обработке запроса") 