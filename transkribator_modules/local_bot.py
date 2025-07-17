#!/usr/bin/env python3
"""
Локальный бот для работы с API сервером
"""

import asyncio
import os
import time
from pathlib import Path
from typing import Optional, Dict, Any
import logging

from transkribator_modules.config import logger, VIDEOS_DIR, AUDIO_DIR, TRANSCRIPTIONS_DIR
from transkribator_modules.api_client import initialize_api_client, get_api_client, get_mock_bot
from transkribator_modules.utils.processor import process_video_file, process_audio_file

class LocalBot:
    """Локальный бот для работы с API сервером"""
    
    def __init__(self, api_url: str = None, api_key: str = None):
        self.api_url = api_url or "http://localhost:8000"
        self.api_key = api_key
        self.running = False
        
        # Инициализируем API клиент
        initialize_api_client(self.api_url, self.api_key)
        
    async def start(self):
        """Запустить бота"""
        logger.info("Запуск локального бота...")
        
        # Проверяем подключение к API серверу
        try:
            async with get_api_client() as client:
                health = await client.health_check()
                logger.info(f"API сервер доступен: {health}")
        except Exception as e:
            logger.error(f"Не удалось подключиться к API серверу: {e}")
            return
            
        self.running = True
        logger.info("Локальный бот запущен и готов к работе")
        
        # Основной цикл мониторинга директорий
        await self._monitor_directories()
        
    async def stop(self):
        """Остановить бота"""
        logger.info("Остановка локального бота...")
        self.running = False
        
    async def _monitor_directories(self):
        """Мониторинг директорий для новых файлов"""
        logger.info("Начинаю мониторинг директорий...")
        
        # Создаем директории если их нет
        VIDEOS_DIR.mkdir(exist_ok=True)
        AUDIO_DIR.mkdir(exist_ok=True)
        TRANSCRIPTIONS_DIR.mkdir(exist_ok=True)
        
        # Словарь для отслеживания обработанных файлов
        processed_files = set()
        
        while self.running:
            try:
                # Проверяем pending файлы (приоритет)
                await self._process_pending_files(processed_files)
                
                # Проверяем видео файлы
                await self._process_new_files(VIDEOS_DIR, processed_files, "video")
                
                # Проверяем аудио файлы
                await self._process_new_files(AUDIO_DIR, processed_files, "audio")
                
                # Пауза между проверками
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"Ошибка в мониторинге директорий: {e}")
                await asyncio.sleep(10)
                
    async def _process_pending_files(self, processed_files: set):
        """Обработать pending файлы от Telegram бота"""
        # Проверяем pending файлы в обеих директориях
        for directory in [VIDEOS_DIR, AUDIO_DIR]:
            if not directory.exists():
                continue
                
            for file_path in directory.iterdir():
                if not file_path.is_file():
                    continue
                    
                # Ищем файлы с префиксом "pending_"
                if not file_path.name.startswith("pending_"):
                    continue
                    
                # Проверяем, не обработан ли уже файл
                file_id = f"{file_path.name}_{file_path.stat().st_mtime}"
                if file_id in processed_files:
                    continue
                    
                # Обрабатываем pending файл
                logger.info(f"Найден pending файл: {file_path.name}")
                await self._process_pending_file(file_path)
                
                # Отмечаем файл как обработанный
                processed_files.add(file_id)
                
    async def _process_pending_file(self, pending_file: Path):
        """Обработать pending файл"""
        try:
            # Читаем информацию из pending файла
            pending_info = {}
            with open(pending_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if '=' in line:
                        key, value = line.strip().split('=', 1)
                        pending_info[key] = value
                        
            logger.info(f"Обрабатываю pending файл для пользователя {pending_info.get('user_id')}, "
                       f"message_id {pending_info.get('message_id')}")
            
            # Здесь должна быть логика для получения файла из Telegram
            # Пока просто удаляем pending файл
            pending_file.unlink()
            logger.info(f"Pending файл {pending_file.name} обработан и удален")
            
        except Exception as e:
            logger.error(f"Ошибка обработки pending файла {pending_file.name}: {e}")
            
    async def _process_new_files(self, directory: Path, processed_files: set, file_type: str):
        """Обработать новые файлы в директории"""
        if not directory.exists():
            return
            
        # Поддерживаемые форматы
        video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.m4v'}
        audio_extensions = {'.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg'}
        
        extensions = video_extensions if file_type == "video" else audio_extensions
        
        for file_path in directory.iterdir():
            if not file_path.is_file():
                continue
                
            if file_path.suffix.lower() not in extensions:
                continue
                
            # Проверяем, не обработан ли уже файл
            file_id = f"{file_path.name}_{file_path.stat().st_mtime}"
            if file_id in processed_files:
                continue
                
            # Проверяем, что файл полностью записан (не копируется)
            try:
                size1 = file_path.stat().st_size
                await asyncio.sleep(2)
                size2 = file_path.stat().st_size
                
                if size1 != size2:
                    logger.info(f"Файл {file_path.name} еще копируется, пропускаю")
                    continue
                    
            except Exception as e:
                logger.warning(f"Ошибка проверки размера файла {file_path.name}: {e}")
                continue
                
            # Обрабатываем файл
            logger.info(f"Найден новый {file_type} файл: {file_path.name}")
            await self._process_file(file_path, file_type)
            
            # Отмечаем файл как обработанный
            processed_files.add(file_id)
            
    async def _process_file(self, file_path: Path, file_type: str):
        """Обработать файл через API сервер"""
        try:
            # Создаем мок-контекст для совместимости с существующим кодом
            mock_context = self._create_mock_context()
            
            # Отправляем файл на транскрибацию через API
            async with get_api_client() as client:
                logger.info(f"Отправляю {file_type} файл {file_path.name} на транскрибацию")
                
                result = await client.transcribe_file(file_path, format_with_llm=True)
                
                logger.info(f"Транскрибация завершена: {result.get('filename')}")
                
                # Сохраняем результат в файл
                await self._save_transcription_result(result, file_path)
                
        except Exception as e:
            logger.error(f"Ошибка обработки файла {file_path.name}: {e}")
            
    async def _save_transcription_result(self, result: Dict[str, Any], original_file: Path):
        """Сохранить результат транскрибации в файл"""
        try:
            # Создаем имя файла для транскрипции
            base_name = original_file.stem
            timestamp = int(time.time())
            transcript_file = TRANSCRIPTIONS_DIR / f"{base_name}_{timestamp}.txt"
            
            # Сохраняем форматированную транскрипцию
            with open(transcript_file, 'w', encoding='utf-8') as f:
                f.write(f"Файл: {result.get('filename', original_file.name)}\n")
                f.write(f"Размер: {result.get('file_size_mb', 0):.2f} MB\n")
                f.write(f"Длительность: {result.get('audio_duration_minutes', 0):.2f} мин\n")
                f.write(f"Время обработки: {result.get('processing_time_seconds', 0):.2f} сек\n")
                f.write("=" * 50 + "\n\n")
                f.write(result.get('formatted_transcript', ''))
                
            logger.info(f"Транскрипция сохранена: {transcript_file}")
            
            # Также сохраняем сырую транскрипцию
            raw_file = TRANSCRIPTIONS_DIR / f"{base_name}_{timestamp}_raw.txt"
            with open(raw_file, 'w', encoding='utf-8') as f:
                f.write(result.get('raw_transcript', ''))
                
            logger.info(f"Сырая транскрипция сохранена: {raw_file}")
            
        except Exception as e:
            logger.error(f"Ошибка сохранения транскрипции: {e}")
            
    def _create_mock_context(self):
        """Создать мок-контекст для совместимости"""
        class MockContext:
            def __init__(self):
                self.bot = get_mock_bot()
                
        return MockContext()


async def main():
    """Главная функция для запуска локального бота"""
    # Получаем настройки из переменных окружения
    api_url = os.getenv("LOCAL_API_URL", "http://localhost:8000")
    api_key = os.getenv("LOCAL_API_KEY")
    
    # Создаем и запускаем бота
    bot = LocalBot(api_url, api_key)
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main()) 