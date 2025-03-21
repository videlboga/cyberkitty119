import os
import re
import logging
import tempfile
import subprocess
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
import yt_dlp
import gdown
from pydub import AudioSegment
from telethon.sync import TelegramClient
import openai
import asyncio

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot.log',
    filemode='a'
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DEEPINFRA_API_KEY = os.getenv('DEEPINFRA_API_KEY')
TELEGRAM_API_ID = int(os.getenv('TELEGRAM_API_ID'))
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')
TELEGRAM_PHONE_NUMBER = os.getenv('TELEGRAM_PHONE_NUMBER')

# Добавляем конфигурацию для OpenRouter API
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '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')
OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'deepseek/deepseek-chat:free')

# Создание директорий для хранения файлов
VIDEOS_DIR = Path("videos")
AUDIO_DIR = Path("audio")
TRANSCRIPTIONS_DIR = Path("transcriptions")

VIDEOS_DIR.mkdir(exist_ok=True)
AUDIO_DIR.mkdir(exist_ok=True)
TRANSCRIPTIONS_DIR.mkdir(exist_ok=True)

# Инициализация клиента Telegram для загрузки больших файлов
client = TelegramClient('transkribator_user', TELEGRAM_API_ID, TELEGRAM_API_HASH)

# ID чата для пересылки видео для загрузки через Telethon
# Создайте канал и добавьте туда бота и Telethon-аккаунт
# Укажите ID этого канала здесь (начинается с -100...)
RELAY_CHAT_ID = -1002616815315  # ID релейного чата (супергруппа)

# Хранилище для отслеживания пересланных видео
# ключ - ID сообщения в RELAY_CHAT_ID, значение - (chat_id, message_id) исходного пользователя
forwarded_videos = {}

# Добавляем словарь для хранения последних транскрипций пользователей
user_transcriptions = {}  # {user_id: {'raw': '...', 'formatted': '...', 'path': '...'}}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветственное сообщение при команде /start."""
    await update.message.reply_text(
        'Привет! Я бот для транскрибации видео. Отправь мне видео, перешли сообщение с видео или отправь ссылку на видео '
        '(YouTube, Google Drive), и я создам для тебя текстовую транскрипцию.'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет справочное сообщение при команде /help."""
    await update.message.reply_text(
        'Я могу транскрибировать видео в текст. Вот что я умею:\n\n'
        '1. Получать видео через загрузку файла в Telegram\n'
        '2. Получать видео через пересланное сообщение с видео\n'
        '3. Скачивать видео по ссылке (YouTube, Google Drive)\n\n'
        'Просто отправь мне видео любым из этих способов, и я верну тебе текстовую транскрипцию '
        'с таймкодами в формате [ЧЧ:ММ:СС] в начале каждого абзаца!\n\n'
        'Дополнительные команды:\n'
        '/rawtranscript - получить необработанную версию последней транскрипции с таймкодами'
    )

async def raw_transcript_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет пользователю сырую (необработанную) версию последней транскрипции."""
    user_id = update.effective_user.id
    
    if user_id not in user_transcriptions or 'raw' not in user_transcriptions[user_id]:
        await update.message.reply_text(
            'У меня нет сохраненных транскрипций для тебя. Отправь мне видео для обработки!'
        )
        return
    
    transcript_data = user_transcriptions[user_id]
    raw_transcript = transcript_data['raw']
    
    # Если текст слишком длинный, отправляем файлом
    if len(raw_transcript) > 4000:
        # Получаем путь к файлу или создаем временный файл
        if 'raw_path' in transcript_data and Path(transcript_data['raw_path']).exists():
            file_path = transcript_data['raw_path']
        else:
            # Создаем временный файл
            file_path = TRANSCRIPTIONS_DIR / f"raw_transcript_{user_id}.txt"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(raw_transcript)
            
        await update.message.reply_document(
            document=open(file_path, "rb"),
            filename=f"Сырая_транскрипция.txt",
            caption="Сырая (необработанная) версия транскрипции"
        )
    else:
        await update.message.reply_text(
            f"Сырая (необработанная) версия транскрипции:\n\n{raw_transcript}"
        )

def is_youtube_url(url: str) -> bool:
    """Проверяет, является ли ссылка YouTube ссылкой."""
    youtube_regex = r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    return bool(re.match(youtube_regex, url))

def is_gdrive_url(url: str) -> bool:
    """Проверяет, является ли ссылка Google Drive ссылкой."""
    gdrive_regex = r'https://drive\.google\.com/file/d/([^/]+)/view|https://drive\.google\.com/open\?id=([^/]+)'
    return bool(re.match(gdrive_regex, url))

def download_video_from_youtube(url: str, output_path: Path) -> Path:
    """Скачивает видео с YouTube."""
    ydl_opts = {
        'format': 'best',
        'outtmpl': str(output_path),
        'quiet': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    
    return output_path

def extract_file_id_from_gdrive(url: str) -> str:
    """Извлекает ID файла из ссылки Google Drive."""
    match1 = re.search(r'https://drive\.google\.com/file/d/([^/]+)/view', url)
    match2 = re.search(r'https://drive\.google\.com/open\?id=([^/]+)', url)
    
    if match1:
        return match1.group(1)
    elif match2:
        return match2.group(1)
    else:
        return None

def download_video_from_gdrive(url: str, output_path: Path) -> Path:
    """Скачивает видео с Google Drive."""
    file_id = extract_file_id_from_gdrive(url)
    if file_id:
        gdown.download(f"https://drive.google.com/uc?id={file_id}", str(output_path), quiet=False)
        return output_path
    return None

async def download_telegram_video(message_id: int, chat_id: int, user_id: int) -> Path:
    """Скачивает видео из Telegram с помощью telethon."""
    try:
        if not client.is_connected():
            await client.connect()
            if not await client.is_user_authorized():
                await client.send_code_request(TELEGRAM_PHONE_NUMBER)
                logger.info("Пожалуйста, авторизуйтесь в телефоне с помощью кода подтверждения")
                code = input('Введите код подтверждения: ')
                await client.sign_in(TELEGRAM_PHONE_NUMBER, code)
        
        output_path = VIDEOS_DIR / f"telegram_video_{message_id}.mp4"
        
        # Пытаемся получить сообщение разными способами
        message = None
        
        # Сначала пробуем прямой метод
        try:
            message = await client.get_messages(chat_id, ids=message_id)
        except Exception as e:
            logger.error(f"Ошибка при прямом получении сообщения: {e}")
            
        # Если не получилось, пробуем получить последние сообщения и найти нужное
        if message is None or not hasattr(message, 'media') or message.media is None:
            try:
                messages = await client.get_messages(entity=chat_id, limit=20)  # Получаем последние 20 сообщений
                
                for msg in messages:
                    if hasattr(msg, 'id') and msg.id == message_id and hasattr(msg, 'media') and msg.media is not None:
                        message = msg
                        break
            except Exception as e:
                logger.error(f"Ошибка при получении списка сообщений: {e}")
        
        # Проверяем, нашли ли мы сообщение с медиа
        if message is None or not hasattr(message, 'media') or message.media is None:
            logger.error(f"Не удалось найти сообщение с ID {message_id} в чате {chat_id} или в нем нет медиа")
            return None
        
        # Скачиваем видео
        await client.download_media(message.media, file=str(output_path))
        
        # Проверяем, что файл существует и не пустой
        if output_path.exists() and output_path.stat().st_size > 0:
            return output_path
        else:
            logger.error("Файл был скачан, но оказался пустым или не существует")
            return None
            
    except Exception as e:
        logger.error(f"Ошибка при скачивании видео из Telegram: {e}")
        return None

def extract_audio_from_video(video_path: Path) -> Path:
    """Извлекает аудио из видео файла, сжимает его и сохраняет в формате WAV."""
    audio_path = AUDIO_DIR / f"{video_path.stem}.wav"
    
    # Проверяем, что видео файл существует
    if not video_path.exists():
        logger.error(f"Видео файл не существует: {video_path}")
        return None
        
    # Проверяем, что видео файл не пустой
    if video_path.stat().st_size == 0:
        logger.error(f"Видео файл пустой: {video_path}")
        return None
    
    logger.info(f"Извлекаю аудио из видео {video_path} (размер: {video_path.stat().st_size} байт)")
    
    # Используем subprocess для вызова ffmpeg
    try:
        result = subprocess.run([
            'ffmpeg', '-i', str(video_path), 
            '-vn', '-acodec', 'pcm_s16le', 
            '-ar', '16000', '-ac', '1', 
            str(audio_path)
        ], check=True, capture_output=True)
        
        logger.info(f"FFmpeg успешно выполнен, код возврата: {result.returncode}")
        
        # Проверяем, что аудио файл создан и не пустой
        if audio_path.exists() and audio_path.stat().st_size > 0:
            logger.info(f"Аудио файл успешно создан: {audio_path} (размер: {audio_path.stat().st_size} байт)")
            return audio_path
        else:
            logger.error(f"Аудио файл не создан или пустой: {audio_path}")
            return None
            
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка при извлечении аудио: {e}")
        logger.error(f"STDOUT: {e.stdout.decode()}")
        logger.error(f"STDERR: {e.stderr.decode()}")
        return None
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при извлечении аудио: {e}")
        return None

def format_timestamp(seconds: float) -> str:
    """Форматирует время в секундах в формат [ЧЧ:ММ:СС]."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"[{hours:02d}:{minutes:02d}:{seconds:02d}]"

def split_audio_into_chunks(audio_path: Path, chunk_size_ms=600000) -> list:
    """Разделяет аудио файл на части по 10 минут."""
    try:
        audio = AudioSegment.from_file(audio_path)
        
        # Разделяем аудио на части по 10 минут
        chunks = []
        for i in range(0, len(audio), chunk_size_ms):
            chunk = audio[i:i + chunk_size_ms]
            chunk_path = AUDIO_DIR / f"{audio_path.stem}_chunk_{i//chunk_size_ms}.wav"
            chunk.export(chunk_path, format="wav")
            chunks.append(chunk_path)
        
        return chunks
    except Exception as e:
        logger.error(f"Ошибка при разделении аудио на части: {e}")
        return []

def transcribe_audio_chunk(chunk_path: Path) -> dict:
    """Отправляет аудио чанк в DeepInfra для транскрибации с таймкодами."""
    url = "https://api.deepinfra.com/v1/openai/audio/transcriptions"
    
    headers = {
        "Authorization": f"Bearer {DEEPINFRA_API_KEY}"
    }
    
    try:
        # Проверяем, что аудио файл существует и не пустой
        if not chunk_path.exists():
            logger.error(f"Аудио файл не существует: {chunk_path}")
            return {"text": "", "segments": []}
            
        if chunk_path.stat().st_size == 0:
            logger.error(f"Аудио файл пустой: {chunk_path}")
            return {"text": "", "segments": []}
            
        logger.info(f"Отправляю файл {chunk_path} размером {chunk_path.stat().st_size} байт на транскрибацию")
        
        with open(chunk_path, "rb") as audio_file:
            files = {"file": (chunk_path.name, audio_file, "audio/wav")}
            data = {
                "model": "openai/whisper-large-v3-turbo",
                "response_format": "verbose_json",
                "timestamp_granularities[]": "segment"
            }
            logger.info(f"Отправляю запрос в DeepInfra API: {url} с данными {data}")
            response = requests.post(url, headers=headers, files=files, data=data)
        
        if response.status_code == 200:
            result = response.json()
            text = result.get("text", "")
            segments = result.get("segments", [])
            logger.info(f"Получена транскрипция длиной {len(text)} символов с {len(segments)} сегментами")
            return {"text": text, "segments": segments}
        else:
            logger.error(f"Ошибка при транскрибации: {response.status_code}, {response.text}")
            return {"text": "", "segments": []}
    except Exception as e:
        logger.error(f"Исключение при транскрибации: {e}")
        return {"text": "", "segments": []}

async def format_transcript_with_llm(raw_transcript: str) -> str:
    """
    Форматирует сырую транскрипцию с помощью ЛЛМ через OpenRouter API.
    
    Преобразует сырой текст в более читаемый формат, добавляя пунктуацию и
    разделяя на абзацы, сохраняя при этом исходное содержание.
    
    Args:
        raw_transcript: Исходная сырая транскрипция от Whisper.
        
    Returns:
        Отформатированная транскрипция.
    """
    try:
        # Настраиваем клиент OpenAI для работы с OpenRouter
        client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
            # Добавляем необходимые заголовки для OpenRouter
            default_headers={
                "HTTP-Referer": "https://github.com/videlboga/cyberkitty119",  # Ваш домен
                "X-Title": "Transkribator Bot"  # Название вашего приложения
            }
        )
        
        # Если транскрипция слишком большая, разделим ее на части
        max_chunk_size = 15000  # Максимальный размер части в символах
        if len(raw_transcript) > max_chunk_size:
            logger.info(f"Транскрипция слишком большая ({len(raw_transcript)} символов), разделяю на части")
            chunks = [raw_transcript[i:i+max_chunk_size] for i in range(0, len(raw_transcript), max_chunk_size)]
            formatted_chunks = []
            
            for i, chunk in enumerate(chunks):
                logger.info(f"Обрабатываю часть {i+1} из {len(chunks)}")
                formatted_chunk = await format_transcript_chunk(client, chunk)
                formatted_chunks.append(formatted_chunk)
                
            return "\n\n".join(formatted_chunks)
        else:
            return await format_transcript_chunk(client, raw_transcript)
            
    except Exception as e:
        logger.error(f"Ошибка при форматировании транскрипции: {e}")
        # В случае ошибки возвращаем исходный текст
        return raw_transcript

async def format_transcript_chunk(client, chunk: str) -> str:
    """Обрабатывает один фрагмент транскрипции через OpenRouter API."""
    try:
        # Создаем запрос к модели
        prompt = f"""Твоя задача - отформатировать сырую транскрипцию видео, сделав её более читаемой. Требования:
1. НЕ МЕНЯЙ содержание и смысл.
2. ОБЯЗАТЕЛЬНО СОХРАНИ все таймкоды в формате [ЧЧ:ММ:СС] в начале абзацев.
3. Добавь правильную пунктуацию (точки, запятые, тире, знаки вопроса).
4. Раздели текст на логические абзацы там, где это уместно.
5. Исправь очевидные ошибки распознавания речи.
6. Убери лишние повторения слов и слова-паразиты (если это не меняет смысл).
7. Форматируй прямую речь с помощью кавычек или тире.
8. Каждый абзац должен начинаться с таймкода в формате [ЧЧ:ММ:СС].

Вот сырая транскрипция, которую нужно отформатировать:

{chunk}"""

        # Отправляем запрос
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": "Ты эксперт по обработке и форматированию транскрипций видео. Твоя задача - сделать сырую транскрипцию более читаемой, сохраняя при этом исходное содержание и все таймкоды в формате [ЧЧ:ММ:СС]."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,  # Низкая температура для более детерминированных результатов
            max_tokens=4096
        )
        
        # Извлекаем ответ
        formatted_text = response.choices[0].message.content
        
        logger.info(f"Транскрипция успешно отформатирована (было {len(chunk)} символов, стало {len(formatted_text)} символов)")
        return formatted_text
        
    except Exception as e:
        logger.error(f"Ошибка при обработке части транскрипции: {e}")
        # В случае ошибки возвращаем исходный текст
        return chunk

async def process_video_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает сообщение с видео."""
    chat_id = update.effective_chat.id
    message = update.message
    user_id = update.effective_user.id
    message_id = update.message.message_id
    
    # Отправляем сообщение о начале обработки
    progress_message = await message.reply_text("Начинаю обработку видео. Это может занять некоторое время...")
    
    try:
        # Получаем информацию о видео
        video_file = message.video or message.document
        video_path = VIDEOS_DIR / f"telegram_video_{message_id}.mp4"
        
        # Проверяем размер файла
        if video_file.file_size and video_file.file_size > 19 * 1024 * 1024:  # Если файл больше 19 МБ
            await progress_message.edit_text("Файл больше 20 МБ, использую альтернативный метод скачивания...")
            
            # Пересылаем видео в промежуточный чат для скачивания через Telethon
            await progress_message.edit_text("Пересылаю видео для обработки...")
            
            # Добавляем метаданные для идентификации пользователя
            caption = f"#user_{chat_id}_{message_id}"
            
            try:
                # Пересылаем видео в специальный чат
                forwarded_msg = await context.bot.copy_message(
                    chat_id=RELAY_CHAT_ID,
                    from_chat_id=chat_id,
                    message_id=message_id,
                    caption=caption
                )
                
                # Запоминаем связь между пересланным сообщением и исходным запросом
                forwarded_videos[forwarded_msg.message_id] = (chat_id, message_id, progress_message.message_id)
                
                await progress_message.edit_text("Видео отправлено на обработку. Пожалуйста, подождите...")
                
                # Теперь скачиваем через Telethon из промежуточного чата
                if not client.is_connected():
                    await client.connect()
                    if not await client.is_user_authorized():
                        await client.send_code_request(TELEGRAM_PHONE_NUMBER)
                        logger.info("Пожалуйста, авторизуйтесь в телефоне с помощью кода подтверждения")
                        code = input('Введите код подтверждения: ')
                        await client.sign_in(TELEGRAM_PHONE_NUMBER, code)
                
                # Получаем сообщение из релейного чата
                logger.info(f"Пытаюсь получить сообщение {forwarded_msg.message_id} из чата {RELAY_CHAT_ID}")
                await asyncio.sleep(2)  # Добавляем небольшую задержку, чтобы сообщение гарантированно успело дойти
                
                telethon_message = None
                try:
                    telethon_message = await client.get_messages(RELAY_CHAT_ID, ids=forwarded_msg.message_id)
                    logger.info(f"Получено сообщение из релейного чата: {telethon_message}")
                except Exception as e:
                    logger.error(f"Ошибка при получении сообщения из релейного чата: {e}")
                
                # Если не смогли получить сообщение, попробуем найти его среди последних сообщений
                if telethon_message is None or not hasattr(telethon_message, 'media') or telethon_message.media is None:
                    logger.info("Пытаюсь найти сообщение среди последних сообщений в релейном чате")
                    
                    try:
                        # Получаем последние сообщения и ищем нужное по ID
                        messages = await client.get_messages(RELAY_CHAT_ID, limit=20)
                        
                        for msg in messages:
                            logger.info(f"Проверяю сообщение ID {msg.id}")
                            if msg.id == forwarded_msg.message_id:
                                telethon_message = msg
                                logger.info(f"Найдено сообщение: {telethon_message}")
                                break
                    except Exception as e:
                        logger.error(f"Ошибка при поиске сообщения среди последних: {e}")
                
                if telethon_message and hasattr(telethon_message, 'media') and telethon_message.media:
                    await progress_message.edit_text("Скачиваю видео через Telethon...")
                    logger.info(f"Начинаю скачивание медиа из сообщения {telethon_message.id}")
                    
                    try:
                        await client.download_media(telethon_message.media, file=str(video_path))
                        logger.info(f"Медиа файл скачан в {video_path}")
                    except Exception as download_error:
                        logger.error(f"Ошибка при скачивании медиа: {download_error}")
                        raise download_error
                    
                    if video_path.exists() and video_path.stat().st_size > 0:
                        logger.info(f"Видео успешно загружено, размер: {video_path.stat().st_size} байт")
                        await progress_message.edit_text("Видео успешно загружено, начинаю обработку...")
                        await process_video(video_path, chat_id, progress_message, context)
                        return
                    else:
                        logger.error(f"Файл не существует или пустой: {video_path}")
                        await progress_message.edit_text("Не удалось скачать видео. Файл пустой или отсутствует.")
                else:
                    logger.error(f"Медиа в сообщении не найдено. telethon_message: {telethon_message}")
                    await progress_message.edit_text("Не удалось найти пересланное видео через Telethon. Попробуйте отправить его напрямую или через ссылку.")
            except Exception as relay_error:
                logger.error(f"Ошибка при пересылке/загрузке видео: {relay_error}")
                await progress_message.edit_text(f"Ошибка при пересылке/загрузке видео: {str(relay_error)}\n\n"
                                               "Попробуйте отправить ссылку на YouTube или Google Drive.")
                return
        else:
            # Для небольших файлов используем стандартный API
            await progress_message.edit_text("Скачиваю видео через Telegram API...")
            try:
                video_file_obj = await context.bot.get_file(video_file.file_id)
                await video_file_obj.download_to_drive(str(video_path))
                
                if video_path.exists() and video_path.stat().st_size > 0:
                    await process_video(video_path, chat_id, progress_message, context)
                else:
                    await progress_message.edit_text("Не удалось скачать видео. Файл пустой или отсутствует.")
            except Exception as api_error:
                logger.error(f"Ошибка при использовании Bot API: {api_error}")
                await progress_message.edit_text(f"Не удалось загрузить видео: {str(api_error)}")
    except Exception as general_error:
        logger.error(f"Общая ошибка при обработке видео: {general_error}")
        await progress_message.edit_text(f"Произошла ошибка при обработке видео: {str(general_error)}")

async def process_forwarded_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает пересланное сообщение с видео."""
    chat_id = update.effective_chat.id
    message = update.message
    
    # Проверяем, что это пересланное сообщение
    forward_info = getattr(message, 'forward_origin', None) or getattr(message, 'forward_from_chat', None)
    if not forward_info:
        await message.reply_text("Это не пересланное сообщение или в нем нет видео.")
        return
    
    # Отправляем сообщение о начале обработки
    progress_message = await message.reply_text("Начинаю обработку пересланного видео. Это может занять некоторое время...")
    
    try:
        # Проверяем, есть ли в пересланном сообщении видео
        has_video = False
        
        # Проверяем явные признаки видео
        if (hasattr(message, 'forward_from_message') and 
            (hasattr(message.forward_from_message, 'video') and message.forward_from_message.video) or
            (hasattr(message.forward_from_message, 'document') and message.forward_from_message.document and 
             hasattr(message.forward_from_message.document, 'mime_type') and 
             'video' in message.forward_from_message.document.mime_type)):
            has_video = True
        
        # Скачиваем видео через telethon
        await progress_message.edit_text("Скачиваю видео из пересланного сообщения...")
        
        # Получаем ID сообщения и чата из forward_origin или forward_from_chat
        forwarded_message_id = getattr(message, 'forward_from_message_id', None)
        if hasattr(message, 'forward_origin') and hasattr(message.forward_origin, 'message_id'):
            forwarded_message_id = message.forward_origin.message_id
            
        forwarded_chat_id = None
        if hasattr(message, 'forward_origin') and hasattr(message.forward_origin, 'chat'):
            forwarded_chat_id = message.forward_origin.chat.id
        elif hasattr(message, 'forward_from_chat'):
            forwarded_chat_id = message.forward_from_chat.id
        
        if not forwarded_message_id or not forwarded_chat_id:
            await progress_message.edit_text("Не удалось определить источник пересланного сообщения.")
            return
        
        video_path = await download_telegram_video(forwarded_message_id, forwarded_chat_id, update.effective_user.id)
        
        if video_path and video_path.exists() and video_path.stat().st_size > 0:
            # Обрабатываем видео
            await process_video(video_path, chat_id, progress_message, context)
        else:
            # Если не удалось скачать, пробуем прямое скачивание через API, если в сообщении есть прикрепленное видео
            if hasattr(message, 'video') and message.video:
                await progress_message.edit_text("Не удалось скачать через Telethon, пробую через API...")
                video_file = message.video
                video_path = VIDEOS_DIR / f"telegram_video_{message.message_id}.mp4"
                video_file_obj = await context.bot.get_file(video_file.file_id)
                await video_file_obj.download_to_drive(str(video_path))
                
                if video_path.exists() and video_path.stat().st_size > 0:
                    await process_video(video_path, chat_id, progress_message, context)
                else:
                    await progress_message.edit_text("Не удалось скачать видео из пересланного сообщения.")
            else:
                await progress_message.edit_text("Не удалось скачать видео из пересланного сообщения. Убедитесь, что оно содержит видео и доступно для скачивания.")
    except Exception as e:
        logger.error(f"Ошибка при обработке пересланного видео: {e}")
        await progress_message.edit_text(f"Произошла ошибка при обработке пересланного видео: {str(e)}")

async def process_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает URL с видео."""
    chat_id = update.effective_chat.id
    message = update.message
    url = message.text
    
    # Отправляем сообщение о начале обработки
    progress_message = await message.reply_text("Начинаю обработку видео по ссылке. Это может занять некоторое время...")
    
    try:
        video_path = None
        
        # Скачиваем видео в зависимости от типа ссылки
        if is_youtube_url(url):
            await progress_message.edit_text("Скачиваю видео с YouTube...")
            # Выполняем эту тяжелую операцию в фоновом режиме через ThreadPoolExecutor
            video_path = await asyncio.to_thread(
                download_video_from_youtube, 
                url, 
                VIDEOS_DIR / f"youtube_{url.split('v=')[-1]}.mp4"
            )
        elif is_gdrive_url(url):
            await progress_message.edit_text("Скачиваю видео с Google Drive...")
            # Выполняем эту тяжелую операцию в фоновом режиме через ThreadPoolExecutor
            video_path = await asyncio.to_thread(
                download_video_from_gdrive, 
                url, 
                VIDEOS_DIR / f"gdrive_{extract_file_id_from_gdrive(url)}.mp4"
            )
        else:
            await progress_message.edit_text("Неподдерживаемый URL. Поддерживаются только YouTube и Google Drive.")
            return
        
        if video_path and video_path.exists():
            # Обрабатываем видео
            await process_video(video_path, chat_id, progress_message, context)
        else:
            await progress_message.edit_text("Не удалось скачать видео по ссылке.")
    except Exception as e:
        logger.error(f"Ошибка при обработке видео по ссылке: {e}")
        await progress_message.edit_text(f"Произошла ошибка при обработке видео по ссылке: {str(e)}")

async def process_video(video_path: Path, chat_id: int, progress_message, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает видео файл: извлекает аудио, разделяет на части и транскрибирует."""
    try:
        # Извлекаем аудио из видео
        await progress_message.edit_text("Извлекаю аудио из видео...")
        # Выполняем эту тяжелую операцию в фоновом режиме через ThreadPoolExecutor
        audio_path = await asyncio.to_thread(extract_audio_from_video, video_path)
        
        if not audio_path:
            await progress_message.edit_text("Не удалось извлечь аудио из видео.")
            return
        
        # Разделяем аудио на части
        await progress_message.edit_text("Разделяю аудио на части...")
        # Выполняем эту тяжелую операцию в фоновом режиме через ThreadPoolExecutor
        audio_chunks = await asyncio.to_thread(split_audio_into_chunks, audio_path)
        
        if not audio_chunks:
            await progress_message.edit_text("Не удалось разделить аудио на части.")
            return
        
        # Транскрибируем каждую часть
        await progress_message.edit_text(f"Начинаю транскрибацию аудио ({len(audio_chunks)} частей)...")
        
        full_transcript = ""
        full_transcript_with_timestamps = ""
        all_segments = []
        chunk_offset = 0  # смещение в секундах для каждого следующего чанка
        current_timestamp = 0  # текущее время для фиксированных таймкодов
        time_step = 30  # шаг таймкодов в секундах
        
        for i, chunk_path in enumerate(audio_chunks):
            await progress_message.edit_text(f"Транскрибирую часть {i+1} из {len(audio_chunks)}...")
            # Выполняем эту тяжелую операцию в фоновом режиме через ThreadPoolExecutor
            result = await asyncio.to_thread(transcribe_audio_chunk, chunk_path)
            transcript = result["text"]
            segments = result["segments"]
            
            # Добавляем текст к полной транскрипции без таймкодов
            full_transcript += transcript + "\n\n"
            
            # Получаем текст из сегментов, но с фиксированными таймкодами каждые 30 секунд
            if segments:
                # Соединяем все тексты сегментов
                combined_text = ""
                segment_texts = [s['text'] for s in segments]
                
                # Для каждого сегмента сохраняем информацию о начале и длительности
                for segment in segments:
                    segment["start"] += chunk_offset
                    segment["end"] += chunk_offset
                    all_segments.append(segment)
                
                # Создаем новый текст с фиксированными таймкодами
                combined_text = ' '.join(segment_texts)
                words = combined_text.split()
                
                # Разбиваем текст на части примерно по 30-40 слов
                words_per_step = 35  # среднее количество слов за 30 секунд
                word_chunks = [' '.join(words[i:i+words_per_step]) for i in range(0, len(words), words_per_step)]
                
                # Добавляем каждый чанк с соответствующим таймкодом
                for word_chunk in word_chunks:
                    if word_chunk.strip():  # Проверяем, что чанк не пустой
                        timestamp = format_timestamp(current_timestamp)
                        full_transcript_with_timestamps += f"{timestamp} {word_chunk.strip()}\n\n"
                        current_timestamp += time_step
            else:
                # Если нет сегментов, просто добавляем текст с текущим таймкодом
                if transcript.strip():
                    timestamp = format_timestamp(current_timestamp)
                    full_transcript_with_timestamps += f"{timestamp} {transcript.strip()}\n\n"
                    current_timestamp += time_step
            
            # Обновляем смещение для следующего чанка (10 минут = 600 секунд)
            chunk_offset += 600
        
        # Форматируем транскрипцию с помощью ЛЛМ
        await progress_message.edit_text("Улучшаю читаемость транскрипции с помощью ИИ...")
        # Передаем транскрипцию с таймкодами для форматирования
        formatted_transcript = await format_transcript_with_llm(full_transcript_with_timestamps)
        
        # Сохраняем транскрипцию
        transcript_path = TRANSCRIPTIONS_DIR / f"{video_path.stem}.txt"
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(formatted_transcript)
        
        # Сохраняем исходную транскрипцию для сравнения
        raw_transcript_path = TRANSCRIPTIONS_DIR / f"{video_path.stem}_raw.txt"
        with open(raw_transcript_path, "w", encoding="utf-8") as f:
            f.write(full_transcript_with_timestamps)
        
        # Сохраняем транскрипции для пользователя
        user_id = None
        if message := getattr(progress_message, 'message', None):
            if message.chat:
                user_id = chat_id
        
        if user_id:
            user_transcriptions[user_id] = {
                'raw': full_transcript_with_timestamps,
                'formatted': formatted_transcript,
                'path': str(transcript_path),
                'raw_path': str(raw_transcript_path),
                'timestamp': asyncio.get_event_loop().time()
            }
        
        # Отправляем транскрипцию пользователю
        await progress_message.edit_text("Транскрипция готова!")
        
        # Если текст слишком длинный, отправляем файлом
        if len(formatted_transcript) > 4000:
            await context.bot.send_document(
                chat_id=chat_id,
                document=open(transcript_path, "rb"),
                filename=f"Транскрипция_{video_path.stem}.txt",
                caption="Транскрипция видео (как файл, т.к. текст слишком длинный)"
            )
        else:
            await context.bot.send_message(chat_id=chat_id, text=f"Транскрипция видео:\n\n{formatted_transcript}")
        
        # Добавляем подсказку о возможности получить сырую версию
        await context.bot.send_message(
            chat_id=chat_id,
            text="Используйте команду /rawtranscript, чтобы получить оригинальную (необработанную) версию транскрипции с таймкодами."
        )
        
    except Exception as e:
        logger.error(f"Ошибка при обработке видео: {e}")
        await progress_message.edit_text(f"Произошла ошибка при обработке видео: {str(e)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает все входящие сообщения."""
    message = update.message
    
    # Проверяем, содержит ли сообщение видео или документ
    if message.video or (message.document and message.document.mime_type and 'video' in message.document.mime_type):
        await process_video_message(update, context)
    # Проверяем, является ли сообщение пересланным
    elif getattr(message, 'forward_origin', None) or getattr(message, 'forward_from_chat', None):
        await process_forwarded_video(update, context)
    # Проверяем, содержит ли сообщение URL
    elif message.text and ('youtube.com' in message.text or 'youtu.be' in message.text or 'drive.google.com' in message.text):
        await process_url(update, context)
    else:
        await update.message.reply_text(
            "Пожалуйста, отправь мне видео файлом, перешли сообщение с видео или отправь ссылку на YouTube/Google Drive."
        )

# Добавляем функцию для мониторинга релейного канала
async def monitor_relay_chat(client, application):
    """Мониторит релейный канал на наличие новых видео для обработки."""
    logger.info(f"Запущен мониторинг релейного канала {RELAY_CHAT_ID}")
    
    try:
        # Получаем последнее обработанное сообщение (или 0, если не было)
        last_processed_id = 0
        
        # Проверяем, что аккаунт Telethon авторизован
        if not client.is_connected():
            await client.connect()
            if not await client.is_user_authorized():
                logger.warning("Пользователь Telethon не авторизован. Отправляю код.")
                await client.send_code_request(TELEGRAM_PHONE_NUMBER)
                logger.info("Пожалуйста, авторизуйтесь в телефоне с помощью кода подтверждения")
                code = input('Введите код подтверждения: ')
                await client.sign_in(TELEGRAM_PHONE_NUMBER, code)
                logger.info("Telethon пользователь успешно авторизован")
        
        # Проверяем доступ к релейному чату
        try:
            chat_entity = await client.get_entity(RELAY_CHAT_ID)
            logger.info(f"Доступ к релейному чату подтвержден: {chat_entity.title if hasattr(chat_entity, 'title') else 'Чат'}")
        except Exception as e:
            logger.error(f"Ошибка при получении информации о релейном чате: {e}")
            logger.warning("Возможно, пользователь Telethon не имеет доступа к релейному чату")
        
        while True:
            try:
                # Получаем новые сообщения
                logger.debug(f"Проверяю новые сообщения в релейном чате (last_id = {last_processed_id})")
                messages = await client.get_messages(RELAY_CHAT_ID, limit=10, min_id=last_processed_id)
                
                if messages:
                    logger.info(f"Получено {len(messages)} новых сообщений в релейном чате")
                
                for message in messages:
                    if not message.id > last_processed_id:
                        continue
                        
                    last_processed_id = max(last_processed_id, message.id)
                    logger.info(f"Обрабатываю сообщение {message.id} из релейного чата")
                    
                    # Проверяем, что это сообщение с видео
                    if hasattr(message, 'media') and message.media is not None:
                        logger.info(f"Сообщение {message.id} содержит медиа")
                        
                        # Проверяем, что это наше сообщение для обработки
                        caption = None
                        if hasattr(message, 'caption') and message.caption is not None:
                            caption = message.caption
                            logger.info(f"Подпись сообщения: {caption}")
                        
                        if caption and caption.startswith('#user_'):
                            logger.info(f"Найдено сообщение для обработки с тегом: {caption}")
                            try:
                                # Извлекаем метаданные
                                parts = caption.split('_')
                                if len(parts) >= 3:
                                    user_chat_id = int(parts[1])
                                    user_message_id = int(parts[2])
                                    
                                    logger.info(f"Метаданные: user_chat_id={user_chat_id}, user_message_id={user_message_id}")
                                    
                                    # Скачиваем видео
                                    video_path = VIDEOS_DIR / f"relay_{message.id}.mp4"
                                    logger.info(f"Начинаю скачивать видео из сообщения {message.id} в {video_path}")
                                    
                                    try:
                                        await client.download_media(message.media, file=str(video_path))
                                        logger.info(f"Видео успешно скачано: {video_path}")
                                    except Exception as download_error:
                                        logger.error(f"Ошибка при скачивании видео: {download_error}")
                                        continue
                                    
                                    if video_path.exists() and video_path.stat().st_size > 0:
                                        logger.info(f"Видео существует и не пустое: {video_path.stat().st_size} байт")
                                        
                                        # Отправляем сообщение пользователю
                                        try:
                                            await application.bot.send_message(
                                                chat_id=user_chat_id,
                                                text=f"Видео получено и скачано. Начинаю обработку..."
                                            )
                                            logger.info(f"Отправлено сообщение пользователю {user_chat_id} о начале обработки")
                                        except Exception as msg_error:
                                            logger.error(f"Ошибка при отправке сообщения пользователю: {msg_error}")
                                        
                                        # Создаем фиктивное сообщение для progress_message
                                        class ProgressMessage:
                                            def __init__(self, chat_id, message_id):
                                                self.chat_id = chat_id
                                                self.message_id = message_id
                                                
                                            async def edit_text(self, text):
                                                try:
                                                    await application.bot.edit_message_text(
                                                        chat_id=self.chat_id,
                                                        message_id=self.message_id,
                                                        text=text
                                                    )
                                                except Exception as edit_error:
                                                    logger.error(f"Ошибка при обновлении сообщения о прогрессе: {edit_error}")
                                        
                                        # Если в forwarded_videos есть информация о сообщениях
                                        progress_message_id = None
                                        if message.id in forwarded_videos:
                                            _, _, progress_message_id = forwarded_videos[message.id]
                                            logger.info(f"Найден ID сообщения о прогрессе: {progress_message_id}")
                                        
                                        progress_message = None
                                        if progress_message_id:
                                            progress_message = ProgressMessage(user_chat_id, progress_message_id)
                                        else:
                                            # Создаем новое сообщение о прогрессе
                                            try:
                                                sent_message = await application.bot.send_message(
                                                    chat_id=user_chat_id,
                                                    text="Начинаю обработку видео..."
                                                )
                                                progress_message = ProgressMessage(user_chat_id, sent_message.message_id)
                                                logger.info(f"Создано новое сообщение о прогрессе: {sent_message.message_id}")
                                            except Exception as send_error:
                                                logger.error(f"Ошибка при создании сообщения о прогрессе: {send_error}")
                                                # Используем заглушку для progress_message
                                                class DummyProgressMessage:
                                                    async def edit_text(self, text):
                                                        logger.info(f"[DUMMY] Обновление прогресса: {text}")
                                                progress_message = DummyProgressMessage()
                                        
                                        # Обрабатываем видео
                                        logger.info(f"Начинаю обработку видео {video_path}")
                                        await process_video(video_path, user_chat_id, progress_message, application)
                                        logger.info(f"Обработка видео {video_path} завершена")
                                    else:
                                        logger.error(f"Видео не существует или пустое: {video_path}")
                            except Exception as e:
                                logger.error(f"Ошибка при обработке видео из релейного канала: {e}")
            except Exception as loop_error:
                logger.error(f"Ошибка в цикле мониторинга релейного канала: {loop_error}")
            
            # Пауза перед следующей проверкой
            await asyncio.sleep(5)
    except Exception as e:
        logger.error(f"Критическая ошибка в мониторинге релейного канала: {e}")
        # Перезапускаем мониторинг через 30 секунд
        logger.info("Перезапуск мониторинга релейного канала через 30 секунд...")
        await asyncio.sleep(30)
        asyncio.create_task(monitor_relay_chat(client, application))

# Изменяем функцию main, чтобы запустить мониторинг релейного канала
async def main() -> None:
    """Запускает бота."""
    # Создаем Application и передаем ему токен бота
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("rawtranscript", raw_transcript_command))
    
    # Регистрируем обработчик сообщений
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    
    # Запускаем бота
    logger.info("Запускаю бота...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    logger.info("Бот запущен")
    
    # Запускаем мониторинг релейного канала
    asyncio.create_task(monitor_relay_chat(client, application))
    
    # Используем asyncio.Event чтобы держать бота запущенным
    stop_event = asyncio.Event()
    
    # Возвращаем объекты для дальнейшего использования и остановки
    return application, stop_event

if __name__ == '__main__':
    # Инициализируем клиент Telegram
    try:
        # Нам нужно асинхронно запустить telethon и основной telegram бот
        async def init():
            # Инициализация Telethon
            await client.connect()
            if not await client.is_user_authorized():
                await client.send_code_request(TELEGRAM_PHONE_NUMBER)
                logger.info("Пожалуйста, авторизуйтесь в телефоне с помощью кода подтверждения")
                code = input('Введите код подтверждения: ')
                await client.sign_in(TELEGRAM_PHONE_NUMBER, code)
            
            # Запуск основного бота
            app, stop_event = await main()
            
            # Ждем сигнала остановки
            try:
                # Блокируем выполнение до отмены (Ctrl+C)
                await stop_event.wait()
            except (KeyboardInterrupt, SystemExit):
                logger.info("Получен сигнал завершения, останавливаю бота...")
            finally:
                # Останавливаем бота при выходе
                await app.updater.stop()
                await app.stop()
                await client.disconnect()
                logger.info("Бот остановлен")
        
        # Запускаем инициализацию и основной код бота
        asyncio.run(init())
    except Exception as e:
        logger.error(f"Ошибка при инициализации: {e}") 