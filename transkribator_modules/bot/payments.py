"""
Модуль для работы с платежами в CyberKitty Transkribator
"""

import json
from datetime import datetime, timedelta
from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from transkribator_modules.config import logger
from transkribator_modules.db.database import SessionLocal, UserService, TransactionService, log_event
from transkribator_modules.bot.logging_utils import log_step
from transkribator_modules.db.models import PlanType, Plan
from transkribator_modules.payments.yukassa import YukassaPaymentService

# Цены в Telegram Stars (1 Star ≈ 1.3 рубля)
PLAN_PRICES_STARS = {
    PlanType.PRO: 230,        # 299 руб ≈ 230 Stars
    PlanType.UNLIMITED: 538,   # 699 руб ≈ 538 Stars
}

# Цены в рублях для ЮКассы
PLAN_PRICES_RUB = {
    PlanType.BASIC: 0.0,       # Бесплатный план
    PlanType.PRO: 299.0,       # PRO план
    PlanType.UNLIMITED: 699.0,  # UNLIMITED план
}

UNLIMITED_YEAR_PLAN = "unlimited_year"

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

PLAN_DESCRIPTIONS_EXTRA = {
    UNLIMITED_YEAR_PLAN: {
        "title": "🚀 Безлимит на год",
        "description": "Одна оплата — год доступа без ограничений",
        "features": [
            "12 месяцев бесконечных минут",
            "Файлы до 2 ГБ и максимум функций",
            "Выгода по сравнению с помесячными платежами",
        ],
    }
}

EXCLUDED_PLAN_TYPES = {PlanType.BETA}


def _resolve_plan_meta(enum_value, plan_name: str) -> dict:
    if enum_value and enum_value in PLAN_DESCRIPTIONS:
        return PLAN_DESCRIPTIONS.get(enum_value, {})
    return PLAN_DESCRIPTIONS_EXTRA.get(plan_name, {})


def _get_rub_price(plan: Plan, enum_value: PlanType | None) -> float | None:
    if getattr(plan, "price_rub", None):
        return float(plan.price_rub)
    if enum_value and enum_value in PLAN_PRICES_RUB:
        return PLAN_PRICES_RUB[enum_value]
    return None


def _get_stars_price(plan: Plan, enum_value: PlanType | None) -> int | None:
    if enum_value and enum_value in PLAN_PRICES_STARS:
        return PLAN_PRICES_STARS[enum_value]
    raw = getattr(plan, "price_stars", None)
    if raw:
        return int(raw)
    return None


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

async def show_payment_plans(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает доступные тарифные планы."""
    try:
        logger.info("Вызвана функция show_payment_plans")
        log_step(update, "payments:show_plans")

        session = SessionLocal()
        try:
            plans = (
                session.query(Plan)
                .filter(Plan.is_active == True)
                .all()
            )
            excluded_names = {plan_type.value for plan_type in EXCLUDED_PLAN_TYPES}
            plans = [plan for plan in plans if plan.name not in excluded_names]
        finally:
            session.close()

        order = {
            PlanType.FREE.value: 0,
            PlanType.BASIC.value: 1,
            PlanType.PRO.value: 2,
            PlanType.UNLIMITED.value: 3,
            UNLIMITED_YEAR_PLAN: 4,
        }

        plans.sort(key=lambda p: order.get(p.name, 100))

        plans_text = (
            "💎 Тарифы CyberKitty Transkribator\n"
            "🆓 Бесплатный\n"
            "• Безлимитные минуты\n"
            "• 3 генерации в месяц\n"
            "• Базовое качество\n\n"
            "💎 Профессиональный — 299₽/мес\n"
            "• 10 часов транскрибации\n"
            "• Приоритетная обработка\n\n"
            "🚀 Безлимитный — 699₽/мес\n"
            "• Полный безлимит\n"
            "• Максимальный приоритет\n\n"
            "🚀 Безлимит на год — 4900₽/год <s>8400₽</s>\n"
            "• Безлимит на 12 месяцев\n"
            "• Все функции включены"
        )

        keyboard = []

        for plan in plans:
            name = plan.name
            display_name = plan.display_name
            if name == PlanType.FREE.value or name == PlanType.BASIC.value:
                continue

            enum_value = None
            try:
                enum_value = PlanType(name)
            except ValueError:
                pass

            if enum_value and enum_value in EXCLUDED_PLAN_TYPES:
                continue

            stars_price = _get_stars_price(plan, enum_value)
            if stars_price:
                keyboard.append([
                    InlineKeyboardButton(
                        f"{display_name} (Stars)",
                        callback_data=f"buy_plan_{name}_stars"
                    )
                ])
            rub_price_value = _get_rub_price(plan, enum_value)
            if rub_price_value and rub_price_value > 0:
                keyboard.append([
                    InlineKeyboardButton(
                        f"{display_name} (ЮКасса)",
                        callback_data=f"buy_plan_{name}_yukassa"
                    )
                ])

        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="personal_cabinet")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.callback_query:
            await update.callback_query.edit_message_text(
                plans_text, reply_markup=reply_markup, parse_mode='HTML'
            )
        else:
            await _reply(update, context, plans_text, reply_markup=reply_markup, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Ошибка при показе планов: {e}")
        await _reply(update, context, "❌ Ошибка при загрузке тарифных планов")

async def initiate_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, plan_id: str) -> None:
    """Инициирует процесс оплаты для выбранного плана."""
    try:
        logger.info(f"Инициируем оплату для плана: {plan_id}")
        log_step(update, "payments:initiate", {"plan": plan_id})

        enum_value = None
        try:
            enum_value = getattr(PlanType, plan_id.upper())
        except AttributeError:
            enum_value = None

        session = SessionLocal()
        try:
            plan_obj = session.query(Plan).filter(Plan.name == (enum_value.value if enum_value else plan_id)).first()
        finally:
            session.close()

        if not plan_obj:
            logger.warning(f"План не найден: {plan_id}")
            await update.callback_query.edit_message_text("❌ Тариф временно недоступен")
            return

        stars_price = _get_stars_price(plan_obj, enum_value)
        if not stars_price:
            logger.warning(f"План {plan_id} недоступен для оплаты Stars")
            await update.callback_query.edit_message_text("❌ Этот план недоступен для оплаты через Telegram Stars")
            return

        meta = _resolve_plan_meta(enum_value, plan_obj.name)
        display_name = plan_obj.display_name or meta.get("title", plan_obj.name.upper())
        description = meta.get("description", "")
        if plan_obj.description:
            description = plan_obj.description

        # Создаем invoice для оплаты через Telegram Stars
        prices = [LabeledPrice(label=f"План {display_name}", amount=stars_price)]

        log_step(update, "payments:invoice_sent", {"plan": plan_obj.name, "stars": stars_price})
        await context.bot.send_invoice(
            chat_id=update.effective_chat.id,
            title=f"Подписка {display_name} - CyberKitty Transkribator",
            description=description or f"Тариф {display_name} в CyberKitty Transkribator",
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
        log_step(update, "payments:yukassa_init", {"plan": plan_id})

        # Разрешаем планы, отсутствующие в enum, используя БД как источник истины
        enum_value = None
        plan_type = None
        try:
            plan_type = getattr(PlanType, plan_id.upper())
            enum_value = plan_type
        except AttributeError:
            plan_type = None  # DB-only plan (e.g., unlimited_year)

        session = SessionLocal()
        try:
            plan_obj = session.query(Plan).filter(Plan.name == (plan_type.value if plan_type else plan_id)).first()
        finally:
            session.close()

        if not plan_obj:
            logger.warning(f"План не найден в БД: {plan_id}")
            await update.callback_query.edit_message_text(f"❌ Неизвестный тарифный план: {plan_id}")
            return

        rub_price = float(plan_obj.price_rub or 0.0) if plan_obj else float(PLAN_PRICES_RUB.get(enum_value, 0.0))
        if rub_price <= 0:
            logger.warning(f"План {plan_id} недоступен для ЮКассы (price_rub <= 0)")
            await update.callback_query.edit_message_text("❌ Этот план недоступен для оплаты через ЮКассу")
            return

        meta = PLAN_DESCRIPTIONS.get(enum_value, {}) if enum_value else {}
        display_name = plan_obj.display_name if plan_obj else meta.get("title", (plan_type.value if plan_type else plan_id).upper())
        description = (plan_obj.description or meta.get("description", "")) if plan_obj else meta.get("description", "")

        plan_display_price = f"{rub_price:.0f} ₽"

        # Создаем платеж через ЮКассу
        try:
            yukassa_service = YukassaPaymentService()
            payment_result = yukassa_service.create_payment(
                user_id=update.effective_user.id,
                plan_type=(plan_type.value if plan_type else plan_id),
                amount=rub_price,
                description=f"Подписка {display_name} - CyberKitty Transkribator"
            )

            # Отправляем ссылку на оплату
            payment_text = f"""💳 **Оплата через ЮКассу**

📦 **План:** {display_name}
💰 **Сумма:** {plan_display_price}
📝 **Описание:** {description or 'Подписка CyberKitty Transkribator'}

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
            log_step(update, "payments:yukassa_link_sent", {
                "plan": plan_id,
                "payment_id": payment_result['payment_id'],
            })

        except Exception as yukassa_error:
            logger.error(f"Ошибка создания платежа ЮКассы: {yukassa_error}")
            log_step(update, "payments:yukassa_error", {"plan": plan_id, "error": str(yukassa_error)})
            await update.callback_query.edit_message_text(
                "❌ Ошибка при создании платежа через ЮКассу. Попробуйте оплатить через Telegram Stars."
            )

    except Exception as e:
        logger.error(f"Ошибка при инициации платежа ЮКассы: {e}")
        log_step(update, "payments:yukassa_error", {"plan": plan_id, "error": str(e)})
        await update.callback_query.edit_message_text("❌ Ошибка при создании платежа")

async def handle_pre_checkout_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает pre-checkout запросы."""
    try:
        query = update.pre_checkout_query
        
        log_step(update, "payments:pre_checkout", {
            "invoice_payload": query.invoice_payload,
            "total_amount": query.total_amount,
            "currency": query.currency,
        })

        # Здесь можно добавить дополнительные проверки
        # Например, проверить доступность товара, валидность цены и т.д.

        await query.answer(ok=True)
        logger.info(f"Pre-checkout query одобрен для пользователя {query.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка в pre-checkout query: {e}")
        log_step(update, "payments:pre_checkout_error", {"error": str(e)})
        await query.answer(ok=False, error_message="Произошла ошибка при обработке платежа")


async def handle_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает успешные платежи."""
    try:
        payment = update.message.successful_payment
        user_id = update.effective_user.id

        logger.info(f"Успешный платеж от пользователя {user_id}: {payment.total_amount/100 if payment.currency == 'RUB' else payment.total_amount} {payment.currency}")
        
        # Определяем план по payload
        plan_name = payment.invoice_payload.replace("plan_", "") if payment.invoice_payload.startswith("plan_") else "pro"
        
        log_step(update, "payments:success", {
            "plan": plan_name,
            "amount": payment.total_amount,
            "currency": payment.currency,
            "provider": payment.provider_payment_charge_id,
            "telegram_charge_id": payment.telegram_payment_charge_id,
        })

        # Обновляем подписку пользователя в базе данных
        db = SessionLocal()
        try:
            user_service = UserService(db)
            transaction_service = TransactionService(db)

            # Получаем пользователя
            db_user = user_service.get_or_create_user(telegram_id=user_id)

            logger.info(f"Определен план для пользователя {user_id}: {plan_name}")

            # Создаем транзакцию
            amount_rub = payment.total_amount / 100 if payment.currency == "RUB" else None
            amount_stars = payment.total_amount if payment.currency == "XTR" else None

            transaction = transaction_service.create_transaction(
                user=db_user,
                plan_type=plan_name,
                amount_rub=amount_rub or 0.0,
                amount_stars=amount_stars or 0,
                payment_method="telegram_stars" if payment.currency == "XTR" else "telegram_payments",
                currency=payment.currency,
                provider_payment_charge_id=payment.provider_payment_charge_id,
                telegram_payment_charge_id=payment.telegram_payment_charge_id,
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

        await _reply(update, context, success_text, reply_markup=reply_markup)
        log_step(update, "payments:success_delivered", {"plan": plan_name})

    except Exception as e:
        logger.error(f"Ошибка при обработке успешного платежа: {e}")
        log_step(update, "payments:success_error", {"error": str(e)})
        await _reply(update, context, "❌ Произошла ошибка при активации подписки")

async def handle_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает колбеки связанные с платежами."""
    try:
        query = update.callback_query
        data = query.data
        
        # Логируем payment callback
        log_step(update, "payments:callback", {"data": data})

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
            log_step(update, "payments:stay_basic")
            await query.edit_message_text(
                "👍 Вы остаетесь на базовом тарифе!\n\n"
                "В любой момент можете перейти на PRO или UNLIMITED план "
                "для расширения возможностей. 🚀"
            )
        else:
            await query.edit_message_text("Неизвестная команда платежной системы")

    except Exception as e:
        logger.error(f"Ошибка в payment callback: {e}")
        log_step(update, "payments:callback_error", {"error": str(e)})
        await query.edit_message_text("❌ Ошибка при обработке запроса")
