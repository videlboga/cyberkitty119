#!/usr/bin/env python3

import os
import sys
import time
import subprocess
import logging
from pathlib import Path

# Настройка логирования с временными метками
LOG_FILE = "audio_extractor_debug.log"
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def extract_audio_using_os_system(video_path, audio_path):
    """Извлекает аудио из видео с использованием os.system"""
    logger.info(f"[OS.SYSTEM] Извлечение аудио из {video_path} в {audio_path}")
    
    try:
        # Логируем информацию о файлах
        logger.debug(f"[OS.SYSTEM] Проверка видеофайла: существует={os.path.exists(video_path)}, размер={os.path.getsize(video_path) if os.path.exists(video_path) else 'N/A'}")
        
        # Создаем директорию для аудио, если она не существует
        audio_dir = os.path.dirname(audio_path)
        if not os.path.exists(audio_dir):
            logger.debug(f"[OS.SYSTEM] Создание директории {audio_dir}")
            os.makedirs(audio_dir, exist_ok=True)
        
        # Формируем команду
        cmd = f'ffmpeg -i "{video_path}" -vn -acodec pcm_s16le -ar 44100 -ac 2 -y "{audio_path}"'
        logger.debug(f"[OS.SYSTEM] Команда: {cmd}")
        
        # Засекаем время начала
        start_time = time.time()
        logger.debug(f"[OS.SYSTEM] Начало выполнения команды: {time.strftime('%H:%M:%S')}")
        
        # Запускаем ffmpeg через os.system
        return_code = os.system(cmd)
        
        # Вычисляем время выполнения
        end_time = time.time()
        duration = end_time - start_time
        logger.debug(f"[OS.SYSTEM] Завершение команды: {time.strftime('%H:%M:%S')}, длительность: {duration:.2f} секунд")
        
        # Проверяем код возврата
        logger.debug(f"[OS.SYSTEM] Код возврата: {return_code}")
        
        if return_code != 0:
            logger.error(f"[OS.SYSTEM] Ошибка при извлечении аудио, код возврата: {return_code}")
            return False
        
        # Проверяем, что файл создался и не пустой
        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
            logger.info(f"[OS.SYSTEM] Аудио успешно извлечено, размер: {os.path.getsize(audio_path)} байт")
            return True
        else:
            logger.error(f"[OS.SYSTEM] Аудиофайл не создан или пустой: существует={os.path.exists(audio_path)}, размер={os.path.getsize(audio_path) if os.path.exists(audio_path) else 'N/A'}")
            return False
    
    except Exception as e:
        logger.exception(f"[OS.SYSTEM] Исключение при извлечении аудио: {e}")
        return False

def extract_audio_using_subprocess_run(video_path, audio_path):
    """Извлекает аудио из видео с использованием subprocess.run"""
    logger.info(f"[SUBPROCESS.RUN] Извлечение аудио из {video_path} в {audio_path}")
    
    try:
        # Логируем информацию о файлах
        logger.debug(f"[SUBPROCESS.RUN] Проверка видеофайла: существует={os.path.exists(video_path)}, размер={os.path.getsize(video_path) if os.path.exists(video_path) else 'N/A'}")
        
        # Создаем директорию для аудио, если она не существует
        audio_dir = os.path.dirname(audio_path)
        if not os.path.exists(audio_dir):
            logger.debug(f"[SUBPROCESS.RUN] Создание директории {audio_dir}")
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
        logger.debug(f"[SUBPROCESS.RUN] Команда: {' '.join(cmd)}")
        
        # Засекаем время начала
        start_time = time.time()
        logger.debug(f"[SUBPROCESS.RUN] Начало выполнения команды: {time.strftime('%H:%M:%S')}")
        
        # Запускаем ffmpeg через subprocess.run
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        
        # Вычисляем время выполнения
        end_time = time.time()
        duration = end_time - start_time
        logger.debug(f"[SUBPROCESS.RUN] Завершение команды: {time.strftime('%H:%M:%S')}, длительность: {duration:.2f} секунд")
        
        # Логируем вывод
        logger.debug(f"[SUBPROCESS.RUN] Код возврата: {process.returncode}")
        if process.stdout:
            logger.debug(f"[SUBPROCESS.RUN] Stdout: {process.stdout}")
        if process.stderr:
            logger.debug(f"[SUBPROCESS.RUN] Stderr: {process.stderr}")
        
        if process.returncode != 0:
            logger.error(f"[SUBPROCESS.RUN] Ошибка при извлечении аудио, код возврата: {process.returncode}")
            return False
        
        # Проверяем, что файл создался и не пустой
        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
            logger.info(f"[SUBPROCESS.RUN] Аудио успешно извлечено, размер: {os.path.getsize(audio_path)} байт")
            return True
        else:
            logger.error(f"[SUBPROCESS.RUN] Аудиофайл не создан или пустой: существует={os.path.exists(audio_path)}, размер={os.path.getsize(audio_path) if os.path.exists(audio_path) else 'N/A'}")
            return False
    
    except Exception as e:
        logger.exception(f"[SUBPROCESS.RUN] Исключение при извлечении аудио: {e}")
        return False

def extract_audio_using_bash_script(video_path, audio_path):
    """Извлекает аудио из видео с использованием bash-скрипта"""
    logger.info(f"[BASH] Извлечение аудио из {video_path} в {audio_path}")
    
    try:
        # Логируем информацию о файлах
        logger.debug(f"[BASH] Проверка видеофайла: существует={os.path.exists(video_path)}, размер={os.path.getsize(video_path) if os.path.exists(video_path) else 'N/A'}")
        
        # Формируем команду
        bash_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extract_audio_simple.sh")
        cmd = [bash_script, video_path, audio_path]
        logger.debug(f"[BASH] Команда: {' '.join(cmd)}")
        
        # Проверяем наличие скрипта
        if not os.path.exists(bash_script):
            logger.error(f"[BASH] Скрипт {bash_script} не найден")
            return False
        
        # Проверяем права на выполнение
        if not os.access(bash_script, os.X_OK):
            logger.debug(f"[BASH] Устанавливаем права на выполнение для {bash_script}")
            os.chmod(bash_script, 0o755)
        
        # Засекаем время начала
        start_time = time.time()
        logger.debug(f"[BASH] Начало выполнения команды: {time.strftime('%H:%M:%S')}")
        
        # Запускаем bash-скрипт
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        
        # Вычисляем время выполнения
        end_time = time.time()
        duration = end_time - start_time
        logger.debug(f"[BASH] Завершение команды: {time.strftime('%H:%M:%S')}, длительность: {duration:.2f} секунд")
        
        # Логируем вывод
        logger.debug(f"[BASH] Код возврата: {process.returncode}")
        if process.stdout:
            logger.debug(f"[BASH] Stdout: {process.stdout}")
        if process.stderr:
            logger.debug(f"[BASH] Stderr: {process.stderr}")
        
        if process.returncode != 0:
            logger.error(f"[BASH] Ошибка при извлечении аудио, код возврата: {process.returncode}")
            return False
        
        # Проверяем, что файл создался и не пустой
        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
            logger.info(f"[BASH] Аудио успешно извлечено, размер: {os.path.getsize(audio_path)} байт")
            return True
        else:
            logger.error(f"[BASH] Аудиофайл не создан или пустой: существует={os.path.exists(audio_path)}, размер={os.path.getsize(audio_path) if os.path.exists(audio_path) else 'N/A'}")
            return False
    
    except Exception as e:
        logger.exception(f"[BASH] Исключение при извлечении аудио: {e}")
        return False

def run_all_methods(video_path, audio_path_prefix):
    """Выполняет извлечение аудио всеми доступными методами последовательно"""
    logger.info(f"Начало извлечения аудио из {video_path} всеми методами")
    
    # Извлекаем информацию о видеофайле
    video_size = os.path.getsize(video_path) if os.path.exists(video_path) else "N/A"
    video_stats = f"Видеофайл: {video_path}, существует={os.path.exists(video_path)}, размер={video_size}"
    logger.info(video_stats)
    
    # Формируем имена выходных файлов
    audio_path_os = f"{audio_path_prefix}_os.wav"
    audio_path_subprocess = f"{audio_path_prefix}_subprocess.wav"
    audio_path_bash = f"{audio_path_prefix}_bash.wav"
    
    # Системная информация
    logger.info(f"Система: {sys.platform}, Python: {sys.version}")
    logger.info(f"Текущая директория: {os.getcwd()}")
    
    results = {}
    
    # Метод 1: os.system
    try:
        logger.info("=" * 50)
        logger.info("МЕТОД 1: os.system")
        success = extract_audio_using_os_system(video_path, audio_path_os)
        results["os.system"] = success
        logger.info(f"Результат os.system: {'УСПЕХ' if success else 'ОШИБКА'}")
    except Exception as e:
        logger.exception(f"Исключение при использовании os.system: {e}")
        results["os.system"] = False
    
    # Метод 2: subprocess.run
    try:
        logger.info("=" * 50)
        logger.info("МЕТОД 2: subprocess.run")
        success = extract_audio_using_subprocess_run(video_path, audio_path_subprocess)
        results["subprocess.run"] = success
        logger.info(f"Результат subprocess.run: {'УСПЕХ' if success else 'ОШИБКА'}")
    except Exception as e:
        logger.exception(f"Исключение при использовании subprocess.run: {e}")
        results["subprocess.run"] = False
    
    # Метод 3: bash script
    try:
        logger.info("=" * 50)
        logger.info("МЕТОД 3: bash script")
        success = extract_audio_using_bash_script(video_path, audio_path_bash)
        results["bash"] = success
        logger.info(f"Результат bash script: {'УСПЕХ' if success else 'ОШИБКА'}")
    except Exception as e:
        logger.exception(f"Исключение при использовании bash script: {e}")
        results["bash"] = False
    
    # Итоговый результат
    logger.info("=" * 50)
    logger.info("ИТОГОВЫЕ РЕЗУЛЬТАТЫ:")
    for method, success in results.items():
        logger.info(f"{method}: {'УСПЕХ' if success else 'ОШИБКА'}")
    
    successful_methods = [method for method, success in results.items() if success]
    if successful_methods:
        logger.info(f"Успешные методы: {', '.join(successful_methods)}")
        if "os.system" in successful_methods:
            return audio_path_os
        elif "subprocess.run" in successful_methods:
            return audio_path_subprocess
        elif "bash" in successful_methods:
            return audio_path_bash
    else:
        logger.error("Все методы завершились с ошибкой")
        return None

def main():
    """Основная функция скрипта"""
    if len(sys.argv) < 3:
        logger.error("Использование: python audio_extractor_debug.py <путь_к_видео> <префикс_аудио>")
        sys.exit(1)
    
    video_path = sys.argv[1]
    audio_path_prefix = sys.argv[2]
    
    # Проверка наличия видеофайла
    if not os.path.exists(video_path):
        logger.error(f"Видеофайл не найден: {video_path}")
        sys.exit(1)
    
    # Запуск всех методов
    result_path = run_all_methods(video_path, audio_path_prefix)
    
    if result_path:
        logger.info(f"Успешно извлечено аудио: {result_path}")
        sys.exit(0)
    else:
        logger.error("Не удалось извлечь аудио ни одним из методов")
        sys.exit(1)

if __name__ == "__main__":
    main() 