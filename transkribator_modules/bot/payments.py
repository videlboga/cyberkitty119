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
from transkribator_modules.payments.yukassa import YukassaPaymentService

# Цены в Telegram Stars (1 Star ≈ 1.3 рубля)
PLAN_PRICES_STARS = {
    PlanType.PRO: 230,        # 299 руб ≈ 230 Stars
    PlanType.UNLIMITED: 538   # 699 руб ≈ 538 Stars
}

# Цены в рублях для ЮКассы
PLAN_PRICES_RUB = {
    PlanType.BASIC: 0.0,       # Бесплатный план
    PlanType.PRO: 299.0,       # PRO план
    PlanType.UNLIMITED: 699.0  # UNLIMITED план
}

PLAN_DESCRIPTIONS = {
    PlanType.BASIC: {
        "title": "Бесплатный план",
        "description": "3 генерации в месяц, файлы до 50 МБ",
        "features": [
            "3 генерации в месяц",
            "Файлы до 50 МБ",
            "Базовое качество",
            "Без оплаты"
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
        logger.info("Вызвана функция show_payment_plans")
        plans_text = """💎 **Тарифные планы CyberKitty Transkribator**

🆓 **Бесплатный**
• 3 генерации в месяц
• Файлы до 50 МБ
• Базовая поддержка
• Старт для знакомства с сервисом

⭐ **PRO (299₽/месяц)**
• 10 часов (600 минут) в месяц
• Файлы до 500 МБ
• Приоритетная очередь
• Расширенные функции

🚀 **UNLIMITED (699₽/месяц)**
• Безлимитная транскрибация
• Файлы до 2 ГБ
• VIP поддержка 24/7
• Полный набор функций

🎯 **Выберите подходящий план и получите максимум возможностей!**"""

        keyboard = [
            [InlineKeyboardButton("🆓 Остаться на бесплатном", callback_data="stay_basic")],
            [InlineKeyboardButton("⭐ Купить PRO (Stars)", callback_data="buy_plan_pro_stars")],
            [InlineKeyboardButton("⭐ Купить PRO (ЮКасса)", callback_data="buy_plan_pro_yukassa")],
            [InlineKeyboardButton("🚀 Купить UNLIMITED (Stars)", callback_data="buy_plan_unlimited_stars")],
            [InlineKeyboardButton("🚀 Купить UNLIMITED (ЮКасса)", callback_data="buy_plan_unlimited_yukassa")],
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
        logger.info(f"Инициируем оплату для плана: {plan_id}")

        # Получаем цену в Stars для этого плана
        plan_type = getattr(PlanType, plan_id.upper())
        plan_prices = {
            "pro": PLAN_PRICES_STARS.get(PlanType.PRO, 0),
            "unlimited": PLAN_PRICES_STARS.get(PlanType.UNLIMITED, 0)
        }

        plan_info = {
            "pro": {
                "name": "PRO",
                "description": "10 часов в месяц + API доступ"
            },
            "unlimited": {
                "name": "UNLIMITED",
                "description": "Безлимитно + VIP функции"
            }
        }

        if plan_id not in plan_info or plan_id not in plan_prices:
            logger.warning(f"Неизвестный план: {plan_id}")
            await update.callback_query.edit_message_text(f"❌ Неизвестный тарифный план: {plan_id}")
            return

        plan = plan_info[plan_id]
        stars_price = plan_prices[plan_id]

        # Создаем invoice для оплаты через Telegram Stars
        prices = [LabeledPrice(label=f"План {plan['name']}", amount=stars_price)]

        await context.bot.send_invoice(
            chat_id=update.effective_chat.id,
            title=f"Подписка {plan['name']} - CyberKitty Transkribator",
            description=plan['description'],
            payload=f"plan_{plan_id}",
            provider_token="",  # Для Telegram Stars оставляем пустым
            currency="XTR",  # XTR - это код для Telegram Stars
            prices=prices,
            start_parameter="subscription"
        )

        logger.info(f"Invoice для плана {plan_id} отправлен пользователю {update.effective_user.id}")

    except Exception as e:
        logger.error(f"Ошибка при инициации платежа: {e}")
        await update.callback_query.edit_message_text("❌ Ошибка при создании платежа")

async def initiate_yukassa_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, plan_id: str) -> None:
    """Инициирует процесс оплаты через ЮКассу для выбранного плана."""
    try:
        logger.info(f"Инициируем оплату через ЮКассу для плана: {plan_id}")

        # Получаем цену в рублях для этого плана
        plan_type = getattr(PlanType, plan_id.upper())
        rub_price = PLAN_PRICES_RUB.get(plan_type, 0)

        if rub_price <= 0:
            await update.callback_query.edit_message_text("❌ Этот план недоступен для оплаты через ЮКассу")
            return

        plan_prices = {
            "pro": PLAN_PRICES_RUB.get(PlanType.PRO, 0),
            "unlimited": PLAN_PRICES_RUB.get(PlanType.UNLIMITED, 0)
        }

        plan_info = {
            "pro": {
                "name": "PRO",
                "description": "10 часов в месяц + API доступ"
            },
            "unlimited": {
                "name": "UNLIMITED",
                "description": "Безлимитно + VIP функции"
            }
        }

        if plan_id not in plan_info or plan_id not in plan_prices:
            logger.warning(f"Неизвестный план для ЮКассы: {plan_id}")
            await update.callback_query.edit_message_text(f"❌ Неизвестный тарифный план: {plan_id}")
            return

        plan = plan_info[plan_id]
        rub_price = plan_prices[plan_id]

        plan_display_price = f"{rub_price:.0f} ₽"

        # Создаем платеж через ЮКассу
        try:
            yukassa_service = YukassaPaymentService()
            payment_result = yukassa_service.create_payment(
                user_id=update.effective_user.id,
                plan_type=plan_id,
                amount=rub_price,
                description=f"Подписка {plan['name']} - CyberKitty Transkribator"
            )

            # Отправляем ссылку на оплату
            payment_text = f"""💳 **Оплата через ЮКассу**

📦 **План:** {plan['name']}
💰 **Сумма:** {plan_display_price}
📝 **Описание:** {plan['description']}

🔗 **Ссылка для оплаты:**
{payment_result['confirmation_url']}

⚠️ **Важно:** После успешной оплаты ваша подписка будет активирована автоматически.

💡 Если у вас возникли проблемы с оплатой, обратитесь в поддержку."""

            keyboard = [
                [InlineKeyboardButton("💳 Перейти к оплате", url=payment_result['confirmation_url'])],
                [InlineKeyboardButton("🔙 Назад к тарифам", callback_data="show_payment_plans")]
            ]

            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.callback_query.edit_message_text(
                payment_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

            logger.info(f"Платеж ЮКассы для плана {plan_id} создан: {payment_result['payment_id']}")

        except Exception as yukassa_error:
            logger.error(f"Ошибка создания платежа ЮКассы: {yukassa_error}")
            await update.callback_query.edit_message_text(
                "❌ Ошибка при создании платежа через ЮКассу. Попробуйте оплатить через Telegram Stars."
            )

    except Exception as e:
        logger.error(f"Ошибка при инициации платежа ЮКассы: {e}")
        await update.callback_query.edit_message_text("❌ Ошибка при создании платежа")

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

        logger.info(f"Успешный платеж от пользователя {user_id}: {payment.total_amount/100 if payment.currency == 'RUB' else payment.total_amount} {payment.currency}")

        # Обновляем подписку пользователя в базе данных
        db = SessionLocal()
        try:
            user_service = UserService(db)
            transaction_service = TransactionService(db)

            # Получаем пользователя
            db_user = user_service.get_or_create_user(telegram_id=user_id)

            # Определяем план по payload
            plan_name = payment.invoice_payload.replace("plan_", "") if payment.invoice_payload.startswith("plan_") else "pro"
            logger.info(f"Определен план для пользователя {user_id}: {plan_name}")

            # Создаем транзакцию
            amount_rub = payment.total_amount / 100 if payment.currency == "RUB" else None
            amount_stars = payment.total_amount if payment.currency == "XTR" else None

            transaction = transaction_service.create_transaction(
                user=db_user,
                plan_type=plan_name,
                amount_rub=amount_rub or 0.0,
                amount_stars=amount_stars or 0,
                payment_method="telegram_stars" if payment.currency == "XTR" else "telegram_payments"
            )

            # Обновляем план пользователя
            upgrade_success = user_service.upgrade_user_plan(db_user, plan_name)
            if upgrade_success:
                logger.info(f"Подписка пользователя {user_id} успешно обновлена до плана {plan_name}")
            else:
                logger.error(f"Ошибка при обновлении плана пользователя {user_id} до {plan_name}")

        except Exception as e:
            logger.error(f"Ошибка при обновлении подписки: {e}")
        finally:
            db.close()

        success_text = f"""🎉 Платеж успешно обработан!

💳 Сумма: {payment.total_amount/100 if payment.currency == 'RUB' else payment.total_amount} {payment.currency}
📦 Товар: {payment.invoice_payload}
🎯 ID транзакции: {payment.telegram_payment_charge_id}

✅ Ваша подписка активирована!

Что теперь доступно:
• Увеличенные лимиты транскрипции
• Приоритетная обработка файлов
• Расширенная техническая поддержка
• Дополнительные функции ИИ

Спасибо за использование CyberKitty Transkribator! 🐱✨"""

        keyboard = [
            [InlineKeyboardButton("🏠 Личный кабинет", callback_data="personal_cabinet")]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            success_text, reply_markup=reply_markup
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
            if data.endswith("_stars"):
                # Платеж через Telegram Stars
                plan_id = data.replace("buy_plan_", "").replace("_stars", "")
                await initiate_payment(update, context, plan_id)
            elif data.endswith("_yukassa"):
                # Платеж через ЮКассу
                plan_id = data.replace("buy_plan_", "").replace("_yukassa", "")
                await initiate_yukassa_payment(update, context, plan_id)
            else:
                # Старый формат для обратной совместимости
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
