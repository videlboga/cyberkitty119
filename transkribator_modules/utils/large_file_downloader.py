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

logger = logging.getLogger(__name__)

async def download_large_file(
    bot_token: str,
    file_id: str,
    destination: Path,
    bot_api_url: str = "http://telegram-bot-api:8081"
) -> bool:
    """
    Скачивает большой файл через прямые HTTP запросы к Bot API Server
    
    Args:
        bot_token: Токен бота
        file_id: ID файла в Telegram
        destination: Путь для сохранения файла
        bot_api_url: URL Bot API Server
        
    Returns:
        True если файл скачан успешно, False в случае ошибки
    """
    
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
            
            # В локальном режиме Bot API Server часто возвращает абсолютный путь внутри своего контейнера,
            # например: /var/lib/telegram-bot-api/... Этот путь НЕ существует в контейнере бота.
            # Попробуем смэппить его в локальный путь, примонтированный в контейнер бота
            if file_path.startswith('/'):
                bot_api_data_dir = os.getenv('BOT_API_DATA_DIR', '/app/telegram-bot-api-data')
                candidates = [
                    ('/var/lib/telegram-bot-api', bot_api_data_dir),
                    ('/var/lib/telegram-bot-api-data', bot_api_data_dir),
                ]

                # Попытаемся смэппить абсолютный путь в примонтированный каталог
                mapped_path = None
                for src_prefix, dst_prefix in candidates:
                    if file_path.startswith(src_prefix + '/'):
                        candidate_path = file_path.replace(src_prefix, dst_prefix, 1)
                        if os.path.exists(candidate_path):
                            mapped_path = candidate_path
                            break

                if mapped_path:
                    logger.info("🔧 Локальный режим: копируем файл напрямую (через примонтированный каталог)")
                    logger.info(f"📂 Источник: {mapped_path}")
                    logger.info(f"📂 Назначение: {destination}")

                    destination.parent.mkdir(parents=True, exist_ok=True)
                    import shutil
                    shutil.copy2(mapped_path, destination)

                    copied_size = os.path.getsize(destination)
                    logger.info(f"✅ Файл успешно скопирован: {copied_size / (1024*1024):.1f} МБ")
                    return True

                # Если смэппинг не сработал, попробуем HTTP-скачивание.
                # Но Bot API /file ожидает относительный file_path без абсолютных префиксов и токена.
                rel_path = file_path
                # Уберём корневой каталог данных
                for src_prefix, _ in candidates:
                    if rel_path.startswith(src_prefix + '/'):
                        rel_path = rel_path[len(src_prefix) + 1:]
                        break
                # Если в начале остался токен, удалим и его
                token_prefix = f"{bot_token}/"
                if rel_path.startswith(token_prefix):
                    rel_path = rel_path[len(token_prefix):]

                logger.info("🔧 HTTP режим: скачиваем через Bot API")
                download_url = f"{bot_api_url}/file/bot{bot_token}/{rel_path}"
                logger.info(f"⬇️ Скачиваю файл с {download_url}")
                
                async with session.get(download_url) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"❌ Ошибка скачивания: {resp.status} - {error_text}")
                        return False

                    destination.parent.mkdir(parents=True, exist_ok=True)
                    total_size = 0
                    with open(destination, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(8192):
                            f.write(chunk)
                            total_size += len(chunk)
                            if total_size and total_size % (10 * 1024 * 1024) == 0:
                                logger.info(f"📥 Скачано: {total_size / (1024*1024):.1f} МБ")
                    logger.info(f"✅ Файл успешно скачан: {total_size / (1024*1024):.1f} МБ")
                    return True
            else:
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
    bot_api_url: str = "http://telegram-bot-api:8081"
) -> Optional[dict]:
    """
    Получает информацию о файле
    
    Returns:
        Словарь с информацией о файле или None в случае ошибки
    """
    
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