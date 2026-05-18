from pathlib import Path
content = Path('max_bot/native_handlers.py').read_text()

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
                import logging
                logger.exception("Failed to open QA session")
                api.send_message(event.chat_id, "❌ Не удалось открыть чат.", reply_markup=_main_menu_keyboard_inline())
            return'''

if old_ask in content:
    content = content.replace(old_ask, new_ask)
    Path('max_bot/native_handlers.py').write_text(content)
else:
    print("WARNING: old_ask not found!")
