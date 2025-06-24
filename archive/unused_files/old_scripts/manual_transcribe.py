import asyncio
from pathlib import Path
import sys

# Добавляем корневую директорию проекта в sys.path
# чтобы можно было импортировать transkribator_modules
current_dir = Path(__file__).parent.resolve()
sys.path.append(str(current_dir))

try:
    from transkribator_modules.utils.processor import process_video_file
    from transkribator_modules.config import TRANSCRIPTIONS_DIR, AUDIO_DIR, VIDEOS_DIR
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    print("Убедитесь, что скрипт находится в корневой директории проекта"
          " и все зависимости установлены.")
    sys.exit(1)

# Фиктивные объекты для имитации окружения Telegram-бота
class FakeBot:
    async def send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
        print(f"[FAKE BOT] Сообщение для chat_id {chat_id}: {text}")
        # Возвращаем фиктивный объект сообщения, чтобы .edit_text() не падал
        return FakeStatusMessage(chat_id) 
    
    async def send_document(self, chat_id, document, filename, caption):
        print(f"[FAKE BOT] Документ для chat_id {chat_id}: {filename} - {caption}")
        
class FakeStatusMessage:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        
    async def edit_text(self, text, reply_markup=None, parse_mode=None):
        print(f"[FAKE BOT STATUS UPDATE] {text}")

class FakeContext:
    def __init__(self):
        self.bot = FakeBot()

async def main_transcribe(video_file_path_str):
    video_file_path = Path(video_file_path_str)

    if not video_file_path.exists():
        print(f"Ошибка: Видеофайл не найден: {video_file_path}")
        return

    # Убедимся, что директории существуют
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    TRANSCRIPTIONS_DIR.mkdir(parents=True, exist_ok=True)
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True) # Хотя мы не копируем сюда, но функция может ожидать


    fake_chat_id = 0 
    # Используем имя файла (без расширения) как message_id для уникальности
    fake_message_id = video_file_path.stem 

    fake_context = FakeContext()

    print(f"Запуск транскрибации для файла: {video_file_path}")
    print(f"Фиктивный chat_id: {fake_chat_id}, message_id: {fake_message_id}")

    # status_message передаем как None, чтобы он создался внутри функции
    # и использовал наш FakeBot для отправки сообщений
    transcript_path, raw_transcript_path = await process_video_file(
        video_path=video_file_path,
        chat_id=fake_chat_id,
        message_id=fake_message_id,
        context=fake_context,
        status_message=None 
    )

    if transcript_path and raw_transcript_path:
        print(f"Транскрибация завершена!")
        print(f"Отформатированная транскрипция: {transcript_path}")
        print(f"Сырая транскрипция: {raw_transcript_path}")
    else:
        print("Транскрибация не удалась.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python manual_transcribe.py <путь_к_видеофайлу>")
        sys.exit(1)
    
    video_path_arg = sys.argv[1]
    asyncio.run(main_transcribe(video_path_arg)) 