#!/usr/bin/env python3

import os
import sys
import time
import asyncio
import logging
from pathlib import Path

# Настройка логирования с временными метками
LOG_FILE = "async_audio_extractor.log"
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def extract_audio_using_asyncio(video_path, audio_path):
    """Извлекает аудио из видео с использованием asyncio.create_subprocess_exec"""
    logger.info(f"[ASYNCIO] Извлечение аудио из {video_path} в {audio_path}")
    
    try:
        # Логируем информацию о файлах
        logger.debug(f"[ASYNCIO] Проверка видеофайла: существует={os.path.exists(video_path)}, размер={os.path.getsize(video_path) if os.path.exists(video_path) else 'N/A'}")
        
        # Создаем директорию для аудио, если она не существует
        audio_dir = os.path.dirname(audio_path)
        if not os.path.exists(audio_dir):
            logger.debug(f"[ASYNCIO] Создание директории {audio_dir}")
            os.makedirs(audio_dir, exist_ok=True)
        
        # Формируем команду
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-vn',
            '-acodec', 'pcm_s16le',
            '-ar', '44100',
            '-ac', '2',
            '-y',
            audio_path
        ]
        logger.debug(f"[ASYNCIO] Команда: {' '.join(cmd)}")
        
        # Засекаем время начала
        start_time = time.time()
        logger.debug(f"[ASYNCIO] Начало выполнения команды: {time.strftime('%H:%M:%S')}")
        
        # Запускаем ffmpeg через asyncio.create_subprocess_exec
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        logger.debug(f"[ASYNCIO] Процесс создан, PID: {process.pid}, ожидаем завершения")
        
        # Дожидаемся завершения процесса и читаем stdout и stderr
        stdout, stderr = await process.communicate()
        
        # Вычисляем время выполнения
        end_time = time.time()
        duration = end_time - start_time
        logger.debug(f"[ASYNCIO] Завершение команды: {time.strftime('%H:%M:%S')}, длительность: {duration:.2f} секунд")
        
        # Логируем вывод
        logger.debug(f"[ASYNCIO] Код возврата: {process.returncode}")
        if stdout:
            logger.debug(f"[ASYNCIO] Stdout: {stdout.decode('utf-8', errors='replace')}")
        if stderr:
            logger.debug(f"[ASYNCIO] Stderr: {stderr.decode('utf-8', errors='replace')}")
        
        if process.returncode != 0:
            logger.error(f"[ASYNCIO] Ошибка при извлечении аудио, код возврата: {process.returncode}")
            return False
        
        # Проверяем, что файл создался и не пустой
        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
            logger.info(f"[ASYNCIO] Аудио успешно извлечено, размер: {os.path.getsize(audio_path)} байт")
            return True
        else:
            logger.error(f"[ASYNCIO] Аудиофайл не создан или пустой: существует={os.path.exists(audio_path)}, размер={os.path.getsize(audio_path) if os.path.exists(audio_path) else 'N/A'}")
            return False
    
    except Exception as e:
        logger.exception(f"[ASYNCIO] Исключение при извлечении аудио: {e}")
        return False

async def extract_audio_with_daemon(video_path, audio_path):
    """Извлекает аудио из видео с помощью создания daemon-процесса"""
    logger.info(f"[DAEMON] Извлечение аудио из {video_path} в {audio_path}")
    
    try:
        # Логируем информацию о файлах
        logger.debug(f"[DAEMON] Проверка видеофайла: существует={os.path.exists(video_path)}, размер={os.path.getsize(video_path) if os.path.exists(video_path) else 'N/A'}")
        
        # Создаем директорию для аудио, если она не существует
        audio_dir = os.path.dirname(audio_path)
        if not os.path.exists(audio_dir):
            logger.debug(f"[DAEMON] Создание директории {audio_dir}")
            os.makedirs(audio_dir, exist_ok=True)
        
        # Формируем команду, которая будет выполняться в фоне
        cmd = f'ffmpeg -i "{video_path}" -vn -acodec pcm_s16le -ar 44100 -ac 2 -y "{audio_path}" </dev/null >/dev/null 2>&1 &'
        logger.debug(f"[DAEMON] Команда: {cmd}")
        
        # Засекаем время начала
        start_time = time.time()
        logger.debug(f"[DAEMON] Начало выполнения команды: {time.strftime('%H:%M:%S')}")
        
        # Запускаем ffmpeg в фоне
        os.system(cmd)
        
        # Ждем некоторое время, чтобы процесс запустился
        await asyncio.sleep(0.5)
        
        # Ждем некоторое разумное время для завершения процесса
        max_wait_time = 60  # максимальное время ожидания в секундах
        check_interval = 0.5  # интервал проверки в секундах
        
        elapsed_time = 0
        while elapsed_time < max_wait_time:
            if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
                # Файл создан и не пустой
                end_time = time.time()
                duration = end_time - start_time
                logger.debug(f"[DAEMON] Аудиофайл создан через {duration:.2f} секунд")
                break
            
            await asyncio.sleep(check_interval)
            elapsed_time += check_interval
            
            if elapsed_time % 5 == 0:
                logger.debug(f"[DAEMON] Ожидание создания файла: {elapsed_time} секунд...")
        
        # Вычисляем время выполнения
        end_time = time.time()
        duration = end_time - start_time
        logger.debug(f"[DAEMON] Завершение команды: {time.strftime('%H:%M:%S')}, длительность: {duration:.2f} секунд")
        
        # Проверяем, что файл создался и не пустой
        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
            logger.info(f"[DAEMON] Аудио успешно извлечено, размер: {os.path.getsize(audio_path)} байт")
            return True
        else:
            logger.error(f"[DAEMON] Аудиофайл не создан или пустой после {max_wait_time} секунд ожидания")
            return False
    
    except Exception as e:
        logger.exception(f"[DAEMON] Исключение при извлечении аудио: {e}")
        return False

async def run_all_methods(video_path, audio_path_prefix):
    """Выполняет извлечение аудио всеми доступными асинхронными методами"""
    logger.info(f"Начало извлечения аудио из {video_path} всеми асинхронными методами")
    
    # Извлекаем информацию о видеофайле
    video_size = os.path.getsize(video_path) if os.path.exists(video_path) else "N/A"
    video_stats = f"Видеофайл: {video_path}, существует={os.path.exists(video_path)}, размер={video_size}"
    logger.info(video_stats)
    
    # Формируем имена выходных файлов
    audio_path_asyncio = f"{audio_path_prefix}_asyncio.wav"
    audio_path_daemon = f"{audio_path_prefix}_daemon.wav"
    
    # Системная информация
    logger.info(f"Система: {sys.platform}, Python: {sys.version}")
    logger.info(f"Текущая директория: {os.getcwd()}")
    logger.info(f"Асинхронный цикл: {asyncio.get_event_loop()}")
    
    results = {}
    
    # Метод 1: asyncio.create_subprocess_exec
    try:
        logger.info("=" * 50)
        logger.info("МЕТОД 1: asyncio.create_subprocess_exec")
        success = await extract_audio_using_asyncio(video_path, audio_path_asyncio)
        results["asyncio"] = success
        logger.info(f"Результат asyncio: {'УСПЕХ' if success else 'ОШИБКА'}")
    except Exception as e:
        logger.exception(f"Исключение при использовании asyncio: {e}")
        results["asyncio"] = False
    
    # Метод 2: фоновое выполнение с периодической проверкой
    try:
        logger.info("=" * 50)
        logger.info("МЕТОД 2: daemon process")
        success = await extract_audio_with_daemon(video_path, audio_path_daemon)
        results["daemon"] = success
        logger.info(f"Результат daemon: {'УСПЕХ' if success else 'ОШИБКА'}")
    except Exception as e:
        logger.exception(f"Исключение при использовании daemon: {e}")
        results["daemon"] = False
    
    # Итоговый результат
    logger.info("=" * 50)
    logger.info("ИТОГОВЫЕ РЕЗУЛЬТАТЫ:")
    for method, success in results.items():
        logger.info(f"{method}: {'УСПЕХ' if success else 'ОШИБКА'}")
    
    successful_methods = [method for method, success in results.items() if success]
    if successful_methods:
        logger.info(f"Успешные методы: {', '.join(successful_methods)}")
        if "asyncio" in successful_methods:
            return audio_path_asyncio
        elif "daemon" in successful_methods:
            return audio_path_daemon
    else:
        logger.error("Все методы завершились с ошибкой")
        return None

async def main():
    """Основная функция скрипта"""
    if len(sys.argv) < 3:
        logger.error("Использование: python async_audio_extractor.py <путь_к_видео> <префикс_аудио>")
        sys.exit(1)
    
    video_path = sys.argv[1]
    audio_path_prefix = sys.argv[2]
    
    # Проверка наличия видеофайла
    if not os.path.exists(video_path):
        logger.error(f"Видеофайл не найден: {video_path}")
        sys.exit(1)
    
    # Запуск всех методов
    result_path = await run_all_methods(video_path, audio_path_prefix)
    
    if result_path:
        logger.info(f"Успешно извлечено аудио: {result_path}")
        return 0
    else:
        logger.error("Не удалось извлечь аудио ни одним из методов")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 