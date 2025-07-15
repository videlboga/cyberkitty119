import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from transkribator_modules.config import logger
from transkribator_modules.db.database import SessionLocal, UserService, ApiKeyService, PromoCodeService
from transkribator_modules.db.models import ApiKey, PlanType
from transkribator_modules.bot.payments import handle_payment_callback

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик callback кнопок"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    data = query.data
    
    try:
        # Обработка платежных callback'ов
        if data == "show_payment_plans" or data.startswith("buy_plan_"):
            await handle_payment_callback(update, context)
            return

        # Обработка кнопок саммари
        elif data.startswith("detailed_summary_") or data.startswith("brief_summary_"):
            from transkribator_modules.bot.handlers import handle_summary_callback
            await handle_summary_callback(update, context)
            return

        # Основные разделы
        elif data == "personal_cabinet":
            from transkribator_modules.bot.commands import personal_cabinet_command
            await personal_cabinet_command(update, context)
        elif data == "show_tutorial":
            from transkribator_modules.bot.commands import show_tutorial
            await show_tutorial(update, context)
        elif data == "show_help":
            from transkribator_modules.bot.commands import start_command
            await start_command(update, context)
        elif data == "show_promo_codes":
            from transkribator_modules.bot.commands import promo_codes_command
            await promo_codes_command(update, context)
        elif data == "show_referral":
            from transkribator_modules.bot.commands import referral_command
            await referral_command(update, context)
        elif data == "add_to_group":
            await add_to_group_callback(query, user)
        elif data == "enter_promo_code":
            await enter_promo_code_callback(query, user)
        elif data == "show_plans":
            await show_plans_callback(query, user)
        elif data == "show_plans_from_cabinet":
            await show_plans_callback(query, user)
        elif data == "show_stats":
            await show_stats_callback(query, user)
        elif data == "show_api_keys":
            await show_api_keys_callback(query, user)
        elif data == "create_api_key":
            await create_api_key_callback(query, user)
        elif data == "list_api_keys":
            await list_api_keys_callback(query, user)
        elif data.startswith("delete_api_key_"):
            key_id = int(data.split("_")[-1])
            await delete_api_key_callback(query, user, key_id)
        elif data == "back_to_start":
            from transkribator_modules.bot.commands import start_command
            await start_command(update, context)
        else:
            # Если это неизвестный callback, логируем для отладки
            logger.warning(f"Неизвестный callback_data: {data}")
            await query.edit_message_text("🙈 Неизвестная команда. *растерянно моргает*")
            
    except Exception as e:
        logger.error(f"Ошибка в callback handler: {e}")
        await query.edit_message_text(
            "😿 Произошла ошибка при обработке запроса. *смущенно прячет мордочку*"
        )

async def enter_promo_code_callback(query, user):
    """Запрос на ввод промокода"""
    promo_text = """🎁 **Ввод промокода**

Отправь мне промокод одним сообщением!

Например: `КОТИК2024`

🔍 **Где найти промокоды?**
• В социальных сетях @kiryanovpro
• В специальных акциях
• За активность в сообществе

😸 *ожидает с нетерпением*"""

    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="personal_cabinet")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(promo_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_plans_callback(query, user):
    """Показать тарифные планы"""
    from transkribator_modules.db.database import get_plans
    
    plans = get_plans()
    plans_text = "💰 **Тарифные планы:**\n\n"
    
    for plan in plans:
        features = []
        if plan.features:
            try:
                features = json.loads(plan.features)
            except:
                features = [plan.features]
        
        minutes_text = f"{plan.minutes_per_month:.0f} минут" if plan.minutes_per_month else "Безлимитно"
        price_text = f"{plan.price_rub:.0f} ₽" if plan.price_rub > 0 else "Бесплатно"
        
        plans_text += f"**{plan.display_name}** - {price_text}\n"
        plans_text += f"• {minutes_text} в месяц\n"
        plans_text += f"• Файлы любого размера\n"
        
        for feature in features:
            plans_text += f"• {feature}\n"
        
        plans_text += f"_{plan.description}_\n\n"
    
    plans_text += "⭐ **Покупка через Telegram Stars**"

    # Определяем, откуда вызвано меню тарифов
    back_callback = "personal_cabinet" if query.data == "show_plans_from_cabinet" else "show_help"
    keyboard = [
        [InlineKeyboardButton("⭐ Купить план", callback_data="show_payment_plans")],
        [InlineKeyboardButton("🔙 Назад", callback_data=back_callback)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(plans_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_stats_callback(query, user):
    """Показать статистику пользователя"""
    db = SessionLocal()
    try:
        user_service = UserService(db)
        from transkribator_modules.db.database import TranscriptionService
        transcription_service = TranscriptionService(db)
        
        db_user = user_service.get_or_create_user(telegram_id=user.id)
        usage_info = user_service.get_usage_info(db_user)
        
        recent_transcriptions = transcription_service.get_user_transcriptions(db_user, limit=5)
        
        stats_text = f"""📊 **Ваша статистика:**

👤 **Профиль:**
• Telegram ID: `{user.id}`
• План: {usage_info['plan_display_name']}
• Зарегистрирован: {db_user.created_at.strftime('%d.%m.%Y')}

📈 **Использование:**
• В этом месяце: {usage_info['minutes_used_this_month']:.1f} мин"""

        if usage_info['minutes_limit']:
            remaining = usage_info['minutes_remaining']
            percentage = usage_info['usage_percentage']
            stats_text += f"\n• Лимит: {usage_info['minutes_limit']:.0f} мин"
            stats_text += f"\n• Осталось: {remaining:.1f} мин ({100-percentage:.1f}%)"
        else:
            stats_text += f"\n• Лимит: Безлимитно ♾️"
        
        stats_text += f"\n• Всего транскрибировано: {usage_info['total_minutes_transcribed']:.1f} мин"
        
        if recent_transcriptions:
            stats_text += f"\n\n🎬 **Последние транскрибации:**"
            for i, trans in enumerate(recent_transcriptions, 1):
                date_str = trans.created_at.strftime('%d.%m %H:%M')
                stats_text += f"\n{i}. {trans.filename or 'Видео'} ({trans.audio_duration_minutes:.1f} мин) - {date_str}"
        
        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data="personal_cabinet")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    finally:
        db.close()

async def show_api_keys_callback(query, user):
    """Показать API ключи пользователя"""
    db = SessionLocal()
    try:
        user_service = UserService(db)
        db_user = user_service.get_or_create_user(telegram_id=user.id)
        plan = user_service.get_user_plan(db_user)
        
        # Проверяем доступ к API
        if plan.name in [PlanType.FREE, PlanType.BASIC]:
            api_text = f"""🔑 **API доступ**

❌ API доступ недоступен для плана "{plan.display_name}"

API доступен начиная с плана "Профессиональный".

💡 Обновите план для получения доступа к API."""
            
            keyboard = [
                [InlineKeyboardButton("📊 Посмотреть планы", callback_data="show_plans")],
                [InlineKeyboardButton("🔙 Назад", callback_data="personal_cabinet")]
            ]
        else:
            # Получаем API ключи
            api_keys = db.query(ApiKey).filter(
                ApiKey.user_id == db_user.id,
                ApiKey.is_active == True
            ).all()
            
            api_text = f"""🔑 **Управление API ключами**

✅ API доступ активен для плана "{plan.display_name}"

**Ваши API ключи:** ({len(api_keys)}/5)"""
            
            if api_keys:
                for i, key in enumerate(api_keys, 1):
                    last_used = key.last_used_at.strftime('%d.%m.%Y') if key.last_used_at else "Не использовался"
                    limit_text = f"{key.minutes_limit:.0f} мин" if key.minutes_limit else "Безлимитно"
                    api_text += f"\n{i}. {key.name}"
                    api_text += f"\n   • Лимит: {limit_text}"
                    api_text += f"\n   • Использовано: {key.minutes_used:.1f} мин"
                    api_text += f"\n   • Последнее использование: {last_used}"
            else:
                api_text += "\n\nУ вас пока нет API ключей."
            
            api_text += f"\n\n📖 **Документация API:**"
            api_text += f"\nБазовый URL: `http://localhost:8000`"
            api_text += f"\nЗаголовок: `Authorization: Bearer YOUR_API_KEY`"
            api_text += f"\nЭндпоинт: `POST /transcribe`"
            
            keyboard = []
            if len(api_keys) < 5:  # Лимит 5 ключей
                keyboard.append([InlineKeyboardButton("➕ Создать ключ", callback_data="create_api_key")])
            
            if api_keys:
                keyboard.append([InlineKeyboardButton("📋 Управление ключами", callback_data="list_api_keys")])
            
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="personal_cabinet")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(api_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    finally:
        db.close()

async def create_api_key_callback(query, user):
    """Создать новый API ключ"""
    db = SessionLocal()
    try:
        user_service = UserService(db)
        api_key_service = ApiKeyService(db)
        
        db_user = user_service.get_or_create_user(telegram_id=user.id)
        plan = user_service.get_user_plan(db_user)
        
        # Проверяем лимиты
        existing_keys = db.query(ApiKey).filter(
            ApiKey.user_id == db_user.id,
            ApiKey.is_active == True
        ).count()
        
        if existing_keys >= 5:
            await query.edit_message_text(
                "❌ Достигнут лимит API ключей (5 штук). Удалите неиспользуемые ключи.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="show_api_keys")
                ]])
            )
            return
        
        # Создаем ключ
        raw_key, api_key = api_key_service.generate_api_key(
            user=db_user,
            name=f"API Key {existing_keys + 1}"
        )
        
        success_text = f"""✅ **API ключ создан!**

🔑 **Ваш новый API ключ:**
```
{raw_key}
```

⚠️ **ВАЖНО:** Сохраните этот ключ в безопасном месте! Он больше не будет показан.

📖 **Пример использования:**
```bash
curl -X POST "http://localhost:8000/transcribe" \\
  -H "Authorization: Bearer {raw_key}" \\
  -F "file=@video.mp4"
```

🔒 **Безопасность:**
• Не передавайте ключ третьим лицам
• Используйте HTTPS в продакшене
• Регулярно обновляйте ключи"""
        
        keyboard = [
            [InlineKeyboardButton("📋 Мои ключи", callback_data="show_api_keys")],
            [InlineKeyboardButton("🔙 Назад", callback_data="personal_cabinet")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(success_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка при создании API ключа: {e}")
        await query.edit_message_text(
            "Произошла ошибка при создании API ключа. *смущенно прячет мордочку*",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="show_api_keys")
            ]])
        )
    finally:
        db.close()

async def list_api_keys_callback(query, user):
    """Показать список API ключей для управления"""
    db = SessionLocal()
    try:
        user_service = UserService(db)
        db_user = user_service.get_or_create_user(telegram_id=user.id)
        
        api_keys = db.query(ApiKey).filter(
            ApiKey.user_id == db_user.id,
            ApiKey.is_active == True
        ).all()
        
        if not api_keys:
            await query.edit_message_text(
                "У вас нет активных API ключей.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="show_api_keys")
                ]])
            )
            return
        
        keys_text = "🔑 **Управление API ключами:**\n\n"
        keyboard = []
        
        for i, key in enumerate(api_keys, 1):
            created = key.created_at.strftime('%d.%m.%Y')
            last_used = key.last_used_at.strftime('%d.%m.%Y') if key.last_used_at else "Не использовался"
            limit_text = f"{key.minutes_limit:.0f} мин" if key.minutes_limit else "Безлимитно"
            
            keys_text += f"**{i}. {key.name}**\n"
            keys_text += f"• Создан: {created}\n"
            keys_text += f"• Лимит: {limit_text}\n"
            keys_text += f"• Использовано: {key.minutes_used:.1f} мин\n"
            keys_text += f"• Последнее использование: {last_used}\n\n"
            
            # Добавляем кнопку удаления
            keyboard.append([InlineKeyboardButton(
                f"🗑 Удалить '{key.name}'", 
                callback_data=f"delete_api_key_{key.id}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="show_api_keys")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(keys_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    finally:
        db.close()

async def delete_api_key_callback(query, user, key_id):
    """Удалить API ключ"""
    db = SessionLocal()
    try:
        user_service = UserService(db)
        db_user = user_service.get_or_create_user(telegram_id=user.id)
        
        # Находим ключ
        api_key = db.query(ApiKey).filter(
            ApiKey.id == key_id,
            ApiKey.user_id == db_user.id,
            ApiKey.is_active == True
        ).first()
        
        if not api_key:
            await query.edit_message_text(
                "API ключ не найден или уже удален.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="list_api_keys")
                ]])
            )
            return
        
        # Деактивируем ключ
        api_key.is_active = False
        db.commit()
        
        await query.edit_message_text(
            f"✅ API ключ '{api_key.name}' успешно удален.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Мои ключи", callback_data="show_api_keys"),
                InlineKeyboardButton("🔙 Назад", callback_data="personal_cabinet")
            ]])
        )
        
    except Exception as e:
        logger.error(f"Ошибка при удалении API ключа: {e}")
        await query.edit_message_text(
            "Произошла ошибка при удалении ключа.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="list_api_keys")
            ]])
        )
    finally:
        db.close()

async def add_to_group_callback(query, user):
    """Информация о добавлении бота в группу"""
    group_text = """👥 **Добавить бота в группу**

🐱 **CyberKitty** может работать в группах и каналах!

✨ **Что умеет в группах:**
• Автоматически транскрибирует аудио и видео
• Отвечает только на медиа-файлы
• Не спамит лишними сообщениями
• Сразу отправляет готовую транскрипцию

📋 **Как добавить:**
1. Добавьте @CyberKitty19_bot в группу
2. Сделайте бота администратором (для загрузки файлов)
3. Отправьте видео или аудио в группу
4. Бот автоматически обработает и ответит

🔧 **Требования:**
• Бот должен быть администратором группы
• Права на чтение сообщений
• Права на отправку сообщений

💡 **Особенности работы в группах:**
• Бот отвечает только на аудио/видео
• Без промежуточных статусных сообщений
• Сразу отправляет готовую транскрипцию
• Не добавляет кнопки и дополнительные сообщения

😸 готов помочь в любой группе"""

    keyboard = [
        [InlineKeyboardButton("🔗 Ссылка на бота", url="https://t.me/CyberKitty19_bot")],
        [InlineKeyboardButton("🔙 Назад", callback_data="show_help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(group_text, reply_markup=reply_markup, parse_mode='Markdown') 