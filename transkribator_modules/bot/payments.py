import json
from datetime import datetime, timedelta
from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters

from transkribator_modules.config import logger, YUKASSA_SHOP_ID, YUKASSA_SECRET_KEY
from transkribator_modules.db.database import SessionLocal, UserService, TransactionService
from transkribator_modules.db.models import PlanType

# Импортируем ЮKassa сервис
try:
    from transkribator_modules.payments.yukassa import YukassaPaymentService
    YUKASSA_AVAILABLE = bool(YUKASSA_SHOP_ID and YUKASSA_SECRET_KEY)
except ImportError:
    YUKASSA_AVAILABLE = False
    logger.warning("ЮKassa SDK не установлен")

# Цены в Telegram Stars (1 Star ≈ 1.3 рубля)
PLAN_PRICES_STARS = {
    PlanType.BASIC: 460,      # 599 руб ≈ 460 Stars
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
        "description": "Безлимитные минуты, файлы любого размера, расширенный API",
        "features": [
            "Безлимитные минуты транскрибации",
            "Файлы любого размера",
            "Максимальный приоритет",
            "Расширенный API доступ", 
            "Поддержка 24/7"
        ]
    }
}

# --- Состояния для ConversationHandler ---
ASK_CONTACT, ASK_EMAIL = range(2)

async def show_payment_plans(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать планы с выбором способа оплаты"""
    user = update.effective_user
    
    db = SessionLocal()
    try:
        user_service = UserService(db)
        db_user = user_service.get_or_create_user(telegram_id=user.id)
        current_plan = user_service.get_user_plan(db_user)
        
        plans_text = f"""💳 **Покупка тарифных планов**

👤 **Ваш текущий план:** {current_plan.display_name}

💫 **Доступные планы для покупки:**

"""
        
        keyboard = []
        
        for plan_type, price_stars in PLAN_PRICES_STARS.items():
            if plan_type.value == current_plan.name:
                continue  # Не показываем текущий план
                
            plan_info = PLAN_DESCRIPTIONS[plan_type]
            price_rub = price_stars * 1.3  # Примерный курс
            
            plans_text += f"**{plan_info['title']}** - {price_rub:.0f} ₽\n"
            plans_text += f"_{plan_info['description']}_\n\n"
            
            # Добавляем кнопку выбора способа оплаты
            keyboard.append([InlineKeyboardButton(
                f"💳 Купить {plan_info['title']}",
                callback_data=f"choose_payment_{plan_type.value}"
            )])
        
        if not keyboard:
            plans_text += "✅ У вас уже максимальный план!"
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="show_help")])
        else:
            plans_text += "💡 **Способы оплаты:**\n"
            plans_text += "• 💳 Банковская карта (ЮKassa)\n"
            plans_text += "• ⭐ Telegram Stars\n\n"
            plans_text += "🔒 **Безопасность:** Все платежи защищены"
            
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="show_help")])
        
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

async def choose_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE, plan_type: str) -> None:
    """Показать выбор способа оплаты для плана"""
    user = update.effective_user
    query = update.callback_query
    
    if plan_type not in PLAN_PRICES_STARS:
        await query.edit_message_text("❌ Неизвестный план")
        return
    
    plan_enum = PlanType(plan_type)
    plan_info = PLAN_DESCRIPTIONS[plan_enum]
    price_rub = PLAN_PRICES_STARS[plan_enum] * 1.3
    
    payment_text = f"""💳 **Выбор способа оплаты**

📋 **План:** {plan_info['title']}
💰 **Цена:** {price_rub:.0f} ₽
📝 **Описание:** {plan_info['description']}

Выберите способ оплаты:"""

    keyboard = []
    
    # Кнопка для ЮKassa (если доступен)
    if YUKASSA_AVAILABLE:
        keyboard.append([InlineKeyboardButton(
            f"💳 Банковская карта ({price_rub:.0f} ₽)",
            callback_data=f"pay_yukassa_{plan_type}"
        )])
    
    # Кнопка для Telegram Stars
    price_stars = PLAN_PRICES_STARS[plan_enum]
    keyboard.append([InlineKeyboardButton(
        f"⭐ Telegram Stars ({price_stars} Stars)",
        callback_data=f"pay_stars_{plan_type}"
    )])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад к планам", callback_data="show_payment_plans")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(payment_text, reply_markup=reply_markup, parse_mode='Markdown')

async def create_yukassa_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, plan_type: str) -> None:
    """Создать платеж через ЮKassa"""
    user = update.effective_user
    query = update.callback_query
    
    if not YUKASSA_AVAILABLE:
        await query.edit_message_text("❌ ЮKassa недоступен. Попробуйте Telegram Stars.")
        return
    
    try:
        # Создаем сервис ЮKassa
        yukassa_service = YukassaPaymentService()
        
        # Получаем цену плана
        amount = yukassa_service.get_plan_price(plan_type)
        description = yukassa_service.get_plan_description(plan_type)
        
        # Создаем платеж
        payment_data = yukassa_service.create_payment(
            user_id=user.id,
            plan_type=plan_type,
            amount=amount,
            description=description
        )
        
        # Отправляем ссылку на оплату
        payment_text = f"""💳 **Платеж создан!**

📋 **План:** {description}
💰 **Сумма:** {amount:.0f} ₽
🔗 **Ссылка:** [Оплатить через ЮKassa]({payment_data['confirmation_url']})

💡 Нажмите на ссылку выше для оплаты
🔄 После оплаты нажмите "Проверить статус" """

        keyboard = [
            [InlineKeyboardButton("🔗 Оплатить", url=payment_data['confirmation_url'])],
            [InlineKeyboardButton("🔄 Проверить статус", callback_data=f"check_yukassa_{payment_data['payment_id']}")],
            [InlineKeyboardButton("🔙 Назад", callback_data="show_payment_plans")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(payment_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка создания платежа ЮKassa: {e}")
        await query.edit_message_text(
            f"❌ Ошибка создания платежа: {str(e)}\n\n"
            "Попробуйте позже или используйте Telegram Stars.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="show_payment_plans")
            ]])
        )

async def check_yukassa_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, payment_id: str) -> None:
    """Проверить статус платежа ЮKassa"""
    user = update.effective_user
    query = update.callback_query
    
    if not YUKASSA_AVAILABLE:
        await query.edit_message_text("❌ ЮKassa недоступен")
        return
    
    try:
        # Создаем сервис ЮKassa
        yukassa_service = YukassaPaymentService()
        
        # Проверяем платеж
        payment_info = yukassa_service.verify_payment(payment_id)
        
        if not payment_info:
            await query.edit_message_text(
                "❌ Платеж не найден или произошла ошибка",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="show_payment_plans")
                ]])
            )
            return
        
        if payment_info['status'] == 'succeeded':
            # Платеж успешен - активируем план
            await activate_plan_after_payment(user.id, payment_info)
            
            success_text = f"""✅ **Платеж успешен!**

💰 **Сумма:** {payment_info['amount']:.0f} ₽
📋 **План:** {payment_info['metadata'].get('plan_type', 'Неизвестно')}
⏰ **Время:** {payment_info['paid_at']}

🎉 Ваш план активирован!"""

            keyboard = [[InlineKeyboardButton("🏠 В главное меню", callback_data="show_help")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(success_text, reply_markup=reply_markup, parse_mode='Markdown')
            
        elif payment_info['status'] == 'pending':
            # Платеж в обработке
            await query.edit_message_text(
                "⏳ Платеж в обработке. Попробуйте проверить статус через несколько минут.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Проверить снова", callback_data=f"check_yukassa_{payment_id}")],
                    [InlineKeyboardButton("🔙 Назад", callback_data="show_payment_plans")]
                ])
            )
        else:
            # Платеж не прошел
            await query.edit_message_text(
                f"❌ Платеж не прошел. Статус: {payment_info['status']}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="show_payment_plans")
                ]])
            )
            
    except Exception as e:
        logger.error(f"Ошибка проверки платежа ЮKassa: {e}")
        await query.edit_message_text(
            f"❌ Ошибка проверки платежа: {str(e)}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="show_payment_plans")
            ]])
        )

async def activate_plan_after_payment(user_id: int, payment_info: dict) -> None:
    """Активировать план пользователя после успешного платежа"""
    db = SessionLocal()
    try:
        user_service = UserService(db)
        transaction_service = TransactionService(db)
        
        # Получаем пользователя
        user = user_service.get_or_create_user(telegram_id=user_id)
        
        # Получаем тип плана из метаданных
        plan_type = payment_info['metadata'].get('plan_type')
        if not plan_type:
            logger.error(f"Не найден тип плана в метаданных платежа {payment_info['payment_id']}")
            return
        
        # Обновляем план пользователя
        success = user_service.upgrade_user_plan(user, plan_type)
        
        if success:
            # Создаем запись о транзакции
            transaction_service.create_transaction(
                user=user,
                plan_purchased=plan_type,
                amount_rub=payment_info['amount'],
                currency="RUB",
                payment_provider="yukassa",
                provider_payment_charge_id=payment_info['payment_id'],
                metadata=json.dumps(payment_info)
            )
            
            logger.info(f"План {plan_type} активирован для пользователя {user_id}")
        else:
            logger.error(f"Не удалось активировать план {plan_type} для пользователя {user_id}")
            
    except Exception as e:
        logger.error(f"Ошибка активации плана: {e}")
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
            [InlineKeyboardButton("🏠 Личный кабинет", callback_data="personal_cabinet")]
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
    elif data.startswith("choose_payment_"):
        plan_type = data.replace("choose_payment_", "")
        await choose_payment_method(update, context, plan_type)
    elif data.startswith("pay_yukassa_"):
        # Обрабатывается через ConversationHandler
        await query.edit_message_text("Обрабатывается...")
    elif data.startswith("pay_stars_"):
        plan_type = data.replace("pay_stars_", "")
        await create_payment_invoice(update, context, plan_type)
    elif data.startswith("check_yukassa_"):
        payment_id = data.replace("check_yukassa_", "")
        await check_yukassa_payment(update, context, payment_id)
    elif data.startswith("buy_plan_"):
        plan_type = data.replace("buy_plan_", "")
        await create_payment_invoice(update, context, plan_type)
    else:
        await query.edit_message_text("Неизвестная команда платежей") 

# --- Новый шаг: запрос контакта или e-mail ---
async def ask_contact_or_email_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обёртка для извлечения plan_type из callback_data"""
    query = update.callback_query
    data = query.data
    if data.startswith("pay_yukassa_"):
        plan_type = data.replace("pay_yukassa_", "")
        return await ask_contact_or_email(update, context, plan_type)
    else:
        await query.edit_message_text("Ошибка: неизвестный план")
        return ConversationHandler.END

async def ask_contact_or_email(update: Update, context: ContextTypes.DEFAULT_TYPE, plan_type: str):
    """Показать экран выбора способа передачи контакта для чека ЮKassa"""
    query = update.callback_query
    context.user_data['pending_plan_type'] = plan_type
    text = (
        "Для оплаты по 54-ФЗ требуется чек.\n"
        "Пожалуйста, выберите, как вы хотите отправить контактные данные для чека ЮKassa:\n\n"
        "• Отправьте e-mail (будет использован только для чека)\n"
        "• Или отправьте свой телефон через Telegram"
    )
    keyboard = [
        [KeyboardButton("📧 Ввести e-mail")],
        [KeyboardButton("📱 Отправить телефон", request_contact=True)]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await query.message.reply_text(text, reply_markup=reply_markup)
    return ASK_CONTACT

# --- Обработка контакта ---
async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if contact and contact.phone_number:
        context.user_data['yukassa_contact'] = {'phone': contact.phone_number}
        await update.message.reply_text("Спасибо! Теперь создаём платёж...", reply_markup=ReplyKeyboardRemove())
        return await proceed_yukassa_payment(update, context)
    else:
        await update.message.reply_text("Не удалось получить номер. Попробуйте ещё раз или выберите e-mail.")
        return ASK_CONTACT

# --- Обработка e-mail ---
async def handle_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()
    if "@" in email and "." in email:
        context.user_data['yukassa_contact'] = {'email': email}
        await update.message.reply_text("Спасибо! Теперь создаём платёж...", reply_markup=ReplyKeyboardRemove())
        return await proceed_yukassa_payment(update, context)
    else:
        await update.message.reply_text("Похоже, это не e-mail. Пожалуйста, введите корректный e-mail.")
        return ASK_CONTACT

# --- Продолжение: создание платежа с receipt ---
async def proceed_yukassa_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    plan_type = context.user_data.get('pending_plan_type')
    contact = context.user_data.get('yukassa_contact', {})
    if not plan_type:
        await update.message.reply_text("Ошибка: не выбран тарифный план.")
        return ConversationHandler.END
    try:
        yukassa_service = YukassaPaymentService()
        amount = yukassa_service.get_plan_price(plan_type)
        description = yukassa_service.get_plan_description(plan_type)
        # Формируем receipt
        receipt = {
            'customer': {},
            'items': [{
                'description': description,
                'quantity': '1.00',
                'amount': {'value': str(amount), 'currency': 'RUB'},
                'vat_code': 1,
                'payment_mode': 'full_prepayment',
                'payment_subject': 'service'
            }]
        }
        if 'email' in contact:
            receipt['customer']['email'] = contact['email']
        elif 'phone' in contact:
            receipt['customer']['phone'] = contact['phone']
        else:
            await update.message.reply_text("Ошибка: не удалось получить контактные данные.")
            return ConversationHandler.END
        payment_data = yukassa_service.create_payment(
            user_id=user.id,
            plan_type=plan_type,
            amount=amount,
            description=description,
            receipt=receipt
        )
        payment_text = f"""💳 **Платеж создан!**\n\n📋 **План:** {description}\n💰 **Сумма:** {amount:.0f} ₽\n🔗 **Ссылка:** [Оплатить через ЮKassa]({payment_data['confirmation_url']})\n\n💡 Нажмите на ссылку выше для оплаты\n🔄 После оплаты нажмите 'Проверить статус' """
        keyboard = [
            [InlineKeyboardButton("🔗 Оплатить", url=payment_data['confirmation_url'])],
            [InlineKeyboardButton("🔄 Проверить статус", callback_data=f"check_yukassa_{payment_data['payment_id']}")],
            [InlineKeyboardButton("🔙 Назад", callback_data="show_payment_plans")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(payment_text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Ошибка создания платежа ЮKassa: {e}")
        await update.message.reply_text(
            f"❌ Ошибка создания платежа: {str(e)}\n\nПопробуйте позже или используйте Telegram Stars.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="show_payment_plans")]])
        )
    return ConversationHandler.END 