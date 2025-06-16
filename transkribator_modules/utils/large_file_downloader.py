#!/usr/bin/env python3
"""
Утилита для скачивания больших файлов через локальный Bot API Server
Обходит ограничения python-telegram-bot библиотеки
"""

import aiohttp
import asyncio
from pathlib import Path
from typing import Optional
import logging
import os

# Импортируем конфигурацию
try:
    from ..config import LOCAL_BOT_API_URL
    DEFAULT_BOT_API_URL = LOCAL_BOT_API_URL
except ImportError:
    DEFAULT_BOT_API_URL = "http://localhost:9081"

logger = logging.getLogger(__name__)

async def download_large_file(
    bot_token: str,
    file_id: str,
    destination: Path,
    bot_api_url: str = None
) -> bool:
    """
    Скачивает большой файл через прямые HTTP запросы к Bot API Server
    
    Args:
        bot_token: Токен бота
        file_id: ID файла в Telegram
        destination: Путь для сохранения файла
        bot_api_url: URL Bot API Server (если None, используется из конфигурации)
        
    Returns:
        True если файл скачан успешно, False в случае ошибки
    """
    
    if bot_api_url is None:
        bot_api_url = DEFAULT_BOT_API_URL
    
    try:
        async with aiohttp.ClientSession() as session:
            
            # Получаем информацию о файле
            logger.info(f"🔍 Получаю информацию о файле {file_id}")
            
            get_file_url = f"{bot_api_url}/bot{bot_token}/getFile"
            
            async with session.post(get_file_url, json={"file_id": file_id}) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"❌ Ошибка getFile: {resp.status} - {error_text}")
                    return False
                
                file_info = await resp.json()
                
                if not file_info.get("ok"):
                    logger.error(f"❌ Bot API вернул ошибку: {file_info}")
                    return False
                
                file_path = file_info["result"]["file_path"]
                file_size = file_info["result"].get("file_size", 0)
                
                logger.info(f"📄 Файл: {file_path}")
                logger.info(f"📊 Размер: {file_size / (1024*1024):.1f} МБ")
            
            # В локальном режиме Bot API Server возвращает абсолютный путь к файлу
            # Преобразуем путь контейнера в локальный путь через volume mapping
            if file_path.startswith('/var/lib/telegram-bot-api/'):
                # Заменяем путь контейнера на локальный путь (внутри контейнера бота)
                local_file_path = file_path.replace('/var/lib/telegram-bot-api/', '/app/telegram-bot-api-data/')
                
                if os.path.exists(local_file_path):
                    logger.info(f"🔧 Локальный режим: копируем файл напрямую")
                    logger.info(f"📂 Источник: {local_file_path}")
                    logger.info(f"📂 Назначение: {destination}")
                    
                    # Создаем директорию если нужно
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Копируем файл напрямую
                    import shutil
                    shutil.copy2(local_file_path, destination)
                    
                    # Проверяем размер скопированного файла
                    copied_size = os.path.getsize(destination)
                    logger.info(f"✅ Файл успешно скопирован: {copied_size / (1024*1024):.1f} МБ")
                    return True
                else:
                    logger.warning(f"⚠️ Локальный файл не найден: {local_file_path}")
            
            # Если локальный файл не найден, пробуем HTTP скачивание
            if file_path.startswith('/'):
                # Для абсолютных путей убираем начальный слеш
                file_path = file_path.lstrip('/')
            
            # Fallback: пытаемся скачать через HTTP (для совместимости)
            logger.info(f"🔧 HTTP режим: скачиваем через Bot API")
            download_url = f"{bot_api_url}/file/bot{bot_token}/{file_path}"
            logger.info(f"⬇️ Скачиваю файл с {download_url}")
            
            async with session.get(download_url) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"❌ Ошибка скачивания: {resp.status} - {error_text}")
                    return False
                
                # Создаем директорию если нужно
                destination.parent.mkdir(parents=True, exist_ok=True)
                
                # Сохраняем файл
                total_size = 0
                with open(destination, 'wb') as f:
                    async for chunk in resp.content.iter_chunked(8192):
                        f.write(chunk)
                        total_size += len(chunk)
                        
                        # Логируем прогресс для больших файлов
                        if total_size % (10 * 1024 * 1024) == 0:  # Каждые 10 МБ
                            logger.info(f"📥 Скачано: {total_size / (1024*1024):.1f} МБ")
                
                logger.info(f"✅ Файл успешно скачан: {total_size / (1024*1024):.1f} МБ")
                return True
                
    except Exception as e:
        logger.error(f"❌ Исключение при скачивании файла: {e}")
        return False

async def get_file_info(
    bot_token: str,
    file_id: str,
    bot_api_url: str = None
) -> Optional[dict]:
    """
    Получает информацию о файле
    
    Returns:
        Словарь с информацией о файле или None в случае ошибки
    """
    
    if bot_api_url is None:
        bot_api_url = DEFAULT_BOT_API_URL
    
    try:
        async with aiohttp.ClientSession() as session:
            get_file_url = f"{bot_api_url}/bot{bot_token}/getFile"
            
            async with session.post(get_file_url, json={"file_id": file_id}) as resp:
                if resp.status != 200:
                    return None
                
                file_info = await resp.json()
                
                if file_info.get("ok"):
                    return file_info["result"]
                else:
                    return None
                    
    except Exception as e:
        logger.error(f"❌ Ошибка получения информации о файле: {e}")
        return None 