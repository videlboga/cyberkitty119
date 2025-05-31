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
    """Показать планы с возможностью покупки через Telegram Stars"""
    user = update.effective_user
    
    db = SessionLocal()
    try:
        user_service = UserService(db)
        db_user = user_service.get_or_create_user(telegram_id=user.id)
        current_plan = user_service.get_user_plan(db_user)
        
        plans_text = f"""⭐ **Покупка планов через Telegram Stars**

👤 **Ваш текущий план:** {current_plan.display_name}

💫 **Доступные планы для покупки:**

"""
        
        keyboard = []
        
        for plan_type, price_stars in PLAN_PRICES_STARS.items():
            if plan_type.value == current_plan.name:
                continue  # Не показываем текущий план
                
            plan_info = PLAN_DESCRIPTIONS[plan_type]
            price_rub = price_stars * 1.3  # Примерный курс
            
            plans_text += f"**{plan_info['title']}** - ⭐ {price_stars} Stars (~{price_rub:.0f} ₽)\n"
            plans_text += f"_{plan_info['description']}_\n\n"
            
            # Добавляем кнопку покупки
            keyboard.append([InlineKeyboardButton(
                f"⭐ Купить {plan_info['title']} - {price_stars} Stars",
                callback_data=f"buy_plan_{plan_type.value}"
            )])
        
        if not keyboard:
            plans_text += "✅ У вас уже максимальный план!"
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")])
        else:
            plans_text += "💡 **Что такое Telegram Stars?**\n"
            plans_text += "Telegram Stars - внутренняя валюта Telegram для покупок в ботах.\n"
            plans_text += "Купить Stars можно в настройках Telegram.\n\n"
            plans_text += "🔒 **Безопасность:** Все платежи обрабатываются Telegram"
            
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")])
        
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
        logger.error(f"Ошибка при показе планов оплаты: {e}")
        error_text = "Произошла ошибка при загрузке планов. *смущенно прячет мордочку*"
        
        if update.callback_query:
            await update.callback_query.edit_message_text(error_text)
        else:
            await update.message.reply_text(error_text)
    finally:
        db.close()

async def create_payment_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE, plan_type: str) -> None:
    """Создать инвойс для оплаты плана через Telegram Stars"""
    user = update.effective_user
    query = update.callback_query
    
    if plan_type not in PLAN_PRICES_STARS:
        await query.edit_message_text("❌ Неизвестный план")
        return
    
    plan_enum = PlanType(plan_type)
    price_stars = PLAN_PRICES_STARS[plan_enum]
    plan_info = PLAN_DESCRIPTIONS[plan_enum]
    
    try:
        # Создаем инвойс для Telegram Stars
        prices = [LabeledPrice(label=plan_info["title"], amount=price_stars)]
        
        # Payload для идентификации платежа
        payload = json.dumps({
            "user_id": user.id,
            "plan": plan_type,
            "timestamp": datetime.now().isoformat()
        })
        
        await context.bot.send_invoice(
            chat_id=user.id,
            title=f"⭐ {plan_info['title']}",
            description=plan_info['description'],
            payload=payload,
            provider_token="",  # Пустой для Telegram Stars
            currency="XTR",     # Валюта Telegram Stars
            prices=prices,
            start_parameter=f"buy_plan_{plan_type}",
            photo_url="https://i.imgur.com/placeholder.jpg",  # Опционально
            photo_size=512,
            photo_width=512,
            photo_height=512,
            need_name=False,
            need_phone_number=False,
            need_email=False,
            need_shipping_address=False,
            send_phone_number_to_provider=False,
            send_email_to_provider=False,
            is_flexible=False
        )
        
        # Обновляем сообщение
        success_text = f"""✅ **Инвойс создан!**

💫 **План:** {plan_info['title']}
⭐ **Цена:** {price_stars} Telegram Stars
📋 **Включает:**"""

        for feature in plan_info['features']:
            success_text += f"\n• {feature}"
        
        success_text += f"\n\n💡 Нажмите на инвойс выше для оплаты"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад к планам", callback_data="show_payment_plans")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(success_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка при создании инвойса: {e}")
        await query.edit_message_text(
            f"❌ Ошибка при создании инвойса: {str(e)}\n\n"
            "Возможно, у бота нет прав на создание платежей.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="show_payment_plans")
            ]])
        )

async def handle_pre_checkout_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка pre-checkout запроса"""
    query = update.pre_checkout_query
    
    try:
        # Парсим payload
        payload_data = json.loads(query.invoice_payload)
        user_id = payload_data.get("user_id")
        plan_type = payload_data.get("plan")
        
        # Проверяем валидность
        if user_id != query.from_user.id:
            await query.answer(ok=False, error_message="Ошибка авторизации")
            return
            
        if plan_type not in PLAN_PRICES_STARS:
            await query.answer(ok=False, error_message="Неизвестный план")
            return
        
        # Проверяем цену
        expected_price = PLAN_PRICES_STARS[PlanType(plan_type)]
        if query.total_amount != expected_price:
            await query.answer(ok=False, error_message="Неверная цена")
            return
        
        # Все проверки пройдены
        await query.answer(ok=True)
        
    except Exception as e:
        logger.error(f"Ошибка в pre_checkout: {e}")
        await query.answer(ok=False, error_message="Ошибка обработки платежа")

async def handle_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка успешного платежа"""
    payment = update.message.successful_payment
    user = update.effective_user
    
    db = SessionLocal()
    try:
        # Парсим payload
        payload_data = json.loads(payment.invoice_payload)
        plan_type = payload_data.get("plan")
        
        user_service = UserService(db)
        transaction_service = TransactionService(db)
        
        # Получаем пользователя
        db_user = user_service.get_or_create_user(telegram_id=user.id)
        
        # Записываем транзакцию
        transaction = transaction_service.create_transaction(
            user=db_user,
            amount_stars=payment.total_amount,
            amount_rub=payment.total_amount * 1.3,  # Примерный курс
            currency="XTR",
            payment_provider="telegram_stars",
            provider_payment_charge_id=payment.provider_payment_charge_id,
            telegram_payment_charge_id=payment.telegram_payment_charge_id,
            plan_purchased=plan_type,
            metadata=json.dumps({
                "invoice_payload": payment.invoice_payload,
                "order_info": payment.order_info.__dict__ if payment.order_info else None
            })
        )
        
        # Обновляем план пользователя
        user_service.upgrade_user_plan(db_user, plan_type)
        
        # Получаем информацию о новом плане
        plan_info = PLAN_DESCRIPTIONS[PlanType(plan_type)]
        
        success_message = f"""🎉 **Платеж успешно обработан!**

✅ **Ваш новый план:** {plan_info['title']}
⭐ **Оплачено:** {payment.total_amount} Telegram Stars
🆔 **ID транзакции:** {transaction.id}

📋 **Теперь вам доступно:**"""

        for feature in plan_info['features']:
            success_message += f"\n• {feature}"
        
        success_message += f"\n\n💡 Используйте /stats для просмотра обновленной информации"
        
        keyboard = [
            [InlineKeyboardButton("📊 Моя статистика", callback_data="show_stats")],
            [InlineKeyboardButton("🔑 API ключи", callback_data="show_api_keys")] if plan_type in ["pro", "unlimited"] else [],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_start")]
        ]
        # Убираем пустые списки
        keyboard = [row for row in keyboard if row]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            success_message, 
            reply_markup=reply_markup, 
            parse_mode='Markdown'
        )
        
        logger.info(f"Успешная покупка плана {plan_type} пользователем {user.id} за {payment.total_amount} Stars")
        
    except Exception as e:
        logger.error(f"Ошибка при обработке успешного платежа: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при активации плана. "
            "Платеж прошел успешно, но план не активирован. "
            "Обратитесь в поддержку @kiryanovpro"
        )
    finally:
        db.close()

async def handle_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик callback кнопок для платежей"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "show_payment_plans":
        await show_payment_plans(update, context)
    elif data.startswith("buy_plan_"):
        plan_type = data.replace("buy_plan_", "")
        await create_payment_invoice(update, context, plan_type)
    else:
        await query.edit_message_text("Неизвестная команда платежей") 