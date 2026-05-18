import re

with open('max_bot/native_handlers.py', 'r') as f:
    content = f.read()

# Replace _verify_session usage or QA states. Wait, actually I can rewrite the text handling entirely.
# Let's search inside handle text to use `core_api_client.agent_chat` instead of the local LLM loop and DB direct access.
text_old = """
        if event.user.id in _ACTIVE_MAX_QA_SESSIONS and text_lower not in {"/start", "старт", "главное меню", "main:menu", "💎 подписка", "подписка", " 🐱 личный кабинет", "личный кабинет", "профиль", "🔎 поиск по заметкам", "поиск по заметкам", "поиск", "⚙️ настройки", "настройки"}:
            state = _ACTIVE_MAX_QA_SESSIONS[event.user.id]
            session_id = state.get("session_id")
            
            try:
                from bot.db import fetch_note_qa_session_payload, record_note_qa_message
                from bot.handlers import MAX_QA_HISTORY_MESSAGES, _run_note_agent
                import asyncio
                
                session_payload = fetch_note_qa_session_payload(session_id, history_limit=MAX_QA_HISTORY_MESSAGES)
                if not session_payload:
                    api.send_message(event.chat_id, "⚠️ Контекст заметки недоступен. Попробуй отправить файл заново.", reply_markup=_main_menu_keyboard_inline())
                    _ACTIVE_MAX_QA_SESSIONS.pop(event.user.id, None)
                    return
                
                record_note_qa_message(session_id, "user", event.text.strip())
                session_payload["messages"].append({"role": "user", "content": event.text.strip()})
                
                api.send_message(event.chat_id, "⏳ Думаю...")
                answer = asyncio.run(_run_note_agent(session_payload))
                
                record_note_qa_message(session_id, "assistant", answer)
                api.send_message(event.chat_id, answer, reply_markup={"inline_keyboard": [[{"text": "💬 Спросите что угодно дальше", "callback_data": "ignored"}], * _main_menu_keyboard_inline()["inline_keyboard"]]})
                
            except Exception as e:
                logger.exception("Failed QA max")
                api.send_message(event.chat_id, "❌ Произошла ошибка (QA)", reply_markup=_main_menu_keyboard_inline())
            return
"""

text_new = """
        if text_lower not in {"/start", "старт", "главное меню", "main:menu", "💎 подписка", "подписка", " 🐱 личный кабинет", "личный кабинет", "профиль", "🔎 поиск по заметкам", "поиск по заметкам", "поиск", "⚙️ настройки", "настройки", "💎💎 подписка"}:
            from .core_api_client import agent_chat
            try:
                api.send_message(event.chat_id, "⏳ Думаю...")
                tid = _get_telegram_id_from_event(event)

                from .core_api_client import agent_chat
                answer = asyncio.run(agent_chat(
                    telegram_id=tid,
                    text=event.text.strip(),
                    name=event.user.first_name or "MaxUser"
                ))
                if answer:
                     api.send_message(event.chat_id, answer, reply_markup=_main_menu_keyboard_inline())
                     return
            except Exception as e:
                logger.error(f"Agent chat error: {e}")
                # Fallthrough if agent returns nothing/error
"""

content = content.replace(text_old, text_new)
with open('max_bot/native_handlers.py', 'w') as f:
    f.write(content)
