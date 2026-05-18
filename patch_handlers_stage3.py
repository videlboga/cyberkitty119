from pathlib import Path
content = Path('max_bot/native_handlers.py').read_text()

content = content.replace('_ACTIVE_MAX_SEARCH_USERS = set()', '_ACTIVE_MAX_SEARCH_USERS = set()\\n_ACTIVE_MAX_QA_SESSIONS = {}\\n')

old_deliver = '''        file_content = _build_note_file_content(note, raw_transcript, filename, segments)
        try:
            normalized_title = _build_note_filename(note)
            caption = "🐱 CyberKitty119 Транскрибатор\\n[Написать Боту](https://max.ru/id632523990270_bot)"
            from io import BytesIO
            bio = BytesIO(file_content.encode("utf-8"))
            api.send_document(chat_id, bio, f"{normalized_title}.txt", caption=caption.replace("Бот: https://max.ru/id632523990270_bot", "[Бот](https://max.ru/id632523990270_bot)"), parse_mode="Markdown")'''

new_deliver = '''        file_content = _build_note_file_content(note, raw_transcript, filename, segments)
        try:
            normalized_title = _build_note_filename(note)
            caption = "🐱 CyberKitty119 Транскрибатор\\n[Написать Боту](https://max.ru/id632523990270_bot)"
            reply_markup = {"inline_keyboard": [[{"text": "💬 Спросить по заметке", "callback_data": f"noteqa:{note.get('id')}"}]]}
            from io import BytesIO
            bio = BytesIO(file_content.encode("utf-8"))
            api.send_document(chat_id, bio, f"{normalized_title}.txt", caption=caption.replace("Бот: https://max.ru/id632523990270_bot", "[Бот](https://max.ru/id632523990270_bot)"), parse_mode="Markdown", reply_markup=reply_markup)'''

content = content.replace(old_deliver, new_deliver)

# Process QA callback
old_ask = '''        elif event.callback_data.startswith("result:ask:"):
            api.send_message(event.chat_id, "В этой (MAX) версии бота функция QA пока в разработке. Отправьте аудио или видео для новой транскрипции!")
            return'''

new_ask = '''        elif event.callback_data.startswith("result:ask:") or event.callback_data.startswith("noteqa:"):
            api.send_message(event.chat_id, "⏳ Открываю чат с заметкой...")
            try:
                note_id = int(event.callback_data.split(":")[-1])
                db_user = _get_or_create_user_from_event(event)

                from bot.db import get_note_qa_session_for_user
                from bot.handlers import _get_note_session_id

                # Fake context for bot/helpers interface
                class DummyData: pass
                class DummyContext: 
                    user_data = {}
                context = DummyContext()

                session_id = _get_note_session_id(context, note_id, user_id=db_user.id)
                if not session_id:
                    api.send_message(event.chat_id, "⚠️ Не нашёл контекст заметки. Отправь файл заново.", reply_markup=_main_menu_keyboard_inline())
                    return

                _ACTIVE_MAX_QA_SESSIONS[event.user.id] = {
                    "note_id": note_id,
                    "session_id": session_id,
                }
                api.send_message(event.chat_id, "💬 Спросите что угодно по заметке. Я помню контекст всей транскрипции.", reply_markup=_main_menu_keyboard_inline())
            except Exception as e:
                logger.exception("Failed to open QA session")
                api.send_message(event.chat_id, "❌ Не удалось открыть чат.", reply_markup=_main_menu_keyboard_inline())
            return'''

content = content.replace(old_ask, new_ask)

# Process QA Text
qa_text_processing = '''        if event.user.id in _ACTIVE_MAX_QA_SESSIONS and text_lower not in {"/start", "старт", "главное меню", "main:menu", "💎 подписка", "подписка", "🐱 личный кабинет", "личный кабинет", "профиль", "🔎 поиск по заметкам", "поиск по заметкам", "поиск", "⚙️ настройки", "настройки"}:
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
                api.send_message(event.chat_id, "❌ Произошла ошибка. Попробуйте еще раз.", reply_markup=_main_menu_keyboard_inline())
            return

        if text_lower in {"/start", "старт'''

content = content.replace('''        if text_lower in {"/start", "старт''', qa_text_processing)

# In menu callbacks, clear QA session
clear_qa_session = '''        _ACTIVE_MAX_SEARCH_USERS.discard(event.user.id)
        _ACTIVE_MAX_QA_SESSIONS.pop(event.user.id, None)'''

content = content.replace('''        _ACTIVE_MAX_SEARCH_USERS.discard(event.user.id)''', clear_qa_session)


Path('max_bot/native_handlers.py').write_text(content)
