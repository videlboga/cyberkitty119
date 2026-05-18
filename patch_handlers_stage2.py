import re
from pathlib import Path

content = Path('max_bot/native_handlers.py').read_text()

# Introduce search state
if '_ACTIVE_MAX_SEARCH_USERS' not in content:
    content = content.replace("def _show_profile_max", "_ACTIVE_MAX_SEARCH_USERS = set()\\n\\ndef _show_profile_max")

# Update show_search_max to actually enable search mode
search_repl_old = '''def _show_search_max(event: Event, api: MaxAPI) -> None:
    msg = "🔎 Функция поиска пока находится в разработке для MAX версии. Вы можете искать заметки в Telegram боте."
    api.send_message(event.chat_id, msg, reply_markup=_main_menu_keyboard_inline())'''

search_repl_new = '''def _show_search_max(event: Event, api: MaxAPI) -> None:
    _ACTIVE_MAX_SEARCH_USERS.add(event.user.id)
    msg = "�� Напиши, что найти в заметках. Я поищу по содержимому и тегам. (Для отмены выберите любое действие в меню)"
    api.send_message(event.chat_id, msg, reply_markup=_main_menu_keyboard_inline())'''

content = content.replace(search_repl_old, search_repl_new)

# Update Settings and Help
settings_old = '''def _show_settings_max(event: Event, api: MaxAPI) -> None:
    msg = "⚙️ Настройки бота будут доступны позже."
    api.send_message(event.chat_id, msg, reply_markup=_main_menu_keyboard_inline())'''

settings_new = '''def _show_settings_max(event: Event, api: MaxAPI) -> None:
    msg = "⚙️ Настройки в разработке. Если нужно что-то сменить (например формат) — напиши и помогу вручную."
    api.send_message(event.chat_id, msg, reply_markup=_main_menu_keyboard_inline())'''

content = content.replace(settings_old, settings_new)


# Update Subscription
subscription_old = '''def _show_subscription_max(event: Event, api: MaxAPI) -> None:
    msg = "💎 Управление подпиской пока недоступно в MAX версии. Вы можете управлять ей в Telegram боте."
    api.send_message(event.chat_id, msg, reply_markup=_main_menu_keyboard_inline())'''

subscription_new = '''def _show_subscription_max(event: Event, api: MaxAPI) -> None:
    from transkribator_modules.db.database import SessionLocal, Plan
    from transkribator_modules.bot.payments import EXCLUDED_PLAN_TYPES, PlanType, UNLIMITED_YEAR_PLAN
    
    db = SessionLocal()
    try:
        plans = db.query(Plan).filter(Plan.is_active == True).all()
        excluded_names = {pt.value for pt in EXCLUDED_PLAN_TYPES}
        plans = [p for p in plans if p.name not in excluded_names]
        
        order = {
            PlanType.FREE.value: 0,
            PlanType.BASIC.value: 1,
            PlanType.PRO.value: 2,
            PlanType.UNLIMITED.value: 3,
            UNLIMITED_YEAR_PLAN: 4,
        }
        plans.sort(key=lambda p: order.get(p.name, 100))

        plans_text = (
            "💎 Тарифы CyberKitty Transkribator\\n"
            "🆓 Бесплатный\\n"
            "• Безлимитные минуты\\n"
            "• 3 генерации в месяц\\n"
            "• Базовое качество\\n\\n"
            "💎 Профессиональный — 299₽/мес\\n"
            "• 10 часов транскрибации\\n"
            "• Приоритетная обработка\\n\\n"
            "🚀 Безлимитный — 699₽/мес\\n"
            "• Полный безлимит\\n"
            "• Максимальный приоритет\\n\\n"
            "🚀 Безлимит на год — 4900₽/год\\n"
            "• Безлимит на 12 месяцев\\n"
            "• Все функции включены\\n\\n"
            "⚠️ Покупка тарифов пока доступна только в нашем Telegram боте @cyberkitty119_bot или по ссылке."
        )
        api.send_message(event.chat_id, plans_text, reply_markup=_main_menu_keyboard_inline())
    except Exception as e:
        api.send_message(event.chat_id, "Ошибка загрузки тарифов.", reply_markup=_main_menu_keyboard_inline())
    finally:
        db.close()'''

content = content.replace(subscription_old, subscription_new)


# Insert handling logic in _process_event_async for Search
# We find "if text_lower in {"/start", "старт", "/help", "помощь", "❓ помощь", "main:menu", "главное меню"}:"
# Just before it, we check for search state. Also, if they use the menu, we cancel search state.

cancel_search = '''        # Cancel search if any menu button pressed as text or event
        if event.callback_data:
            _ACTIVE_MAX_SEARCH_USERS.discard(event.user.id)
'''

# Wait, callback_data handling happens earlier. We should put discard near the top of callback_data handling.
# Let's insert right after: "if event.callback_data:"
content = content.replace('        logger.info("native_handlers: received callback_data=%s user=%s"', '        _ACTIVE_MAX_SEARCH_USERS.discard(event.user.id)\\n        logger.info("native_handlers: received callback_data=%s user=%s"')

# For text commands, when _process_event_async checks if it's text
text_search_logic = '''        text_lower = event.text.lower().strip()
        
        if event.user.id in _ACTIVE_MAX_SEARCH_USERS and text_lower not in {"/start", "старт", "главное меню", "main:menu", "�� подписка", "подписка", "🐱 личный кабинет", "личный кабинет", "профиль", "🔎 поиск по заметкам", "поиск по заметкам", "поиск", "⚙️ настройки", "настройки"}:
            api.send_message(event.chat_id, "⏳ Ищу в заметках...")
            try:
                db_user = _get_or_create_user_from_event(event)
                from transkribator_modules.search.service import run_note_search, NoteSearchError
                import asyncio
                
                try:
                    result = asyncio.run(run_note_search(user_id=db_user.id, query=event.text.strip()))
                    resp = result.get("response", "Ничего не найдено.")
                    api.send_message(event.chat_id, resp, reply_markup=_main_menu_keyboard_inline())
                except NoteSearchError as exc:
                    api.send_message(event.chat_id, f"⚠️ Не удалось выполнить поиск: {exc}", reply_markup=_main_menu_keyboard_inline())
                finally:
                    pass
            except Exception as e:
                logger.exception("Search error in MAX")
                api.send_message(event.chat_id, "❌ Произошла ошибка при поиске.", reply_markup=_main_menu_keyboard_inline())
            finally:
                _ACTIVE_MAX_SEARCH_USERS.discard(event.user.id)
            return

        if text_lower in {"/start", "старт'''

content = content.replace('''        text_lower = event.text.lower().strip()
        if text_lower in {"/start", "старт''', text_search_logic)

# Cancel search if menu text received
menu_text_cancel = '''        _ACTIVE_MAX_SEARCH_USERS.discard(event.user.id)
        if text_lower in {"/start", "старт'''
content = content.replace('''        if text_lower in {"/start", "старт''', menu_text_cancel)

Path('max_bot/native_handlers.py').write_text(content)
