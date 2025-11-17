"""Mega.nz file downloader for large public files (up to 20 GB) without authentication."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Optional

from transkribator_modules.config import logger


class MegaDownloadError(Exception):
    """Ошибка при скачивании с Mega.nz."""
    pass


def extract_mega_id(url: str) -> Optional[str]:
    """
    Извлекает ID файла или папки из Mega.nz ссылок.
    
    Поддерживаемые форматы:
    - https://mega.nz/file/FILE_ID#KEY
    - https://mega.nz/#!FILE_ID!KEY
    - https://mega.co.nz/file/FILE_ID#KEY
    """
    # Возвращаем полный URL, так как mega.py работает с полными ссылками
    if is_mega_link(url):
        return url
    return None


def is_mega_link(url: str) -> bool:
    """Проверяет, является ли URL ссылкой на Mega.nz."""
    return bool(re.search(r'mega\.(nz|co\.nz)', url))


def extract_mega_links(text: str) -> list[str]:
    """
    Извлекает все Mega.nz ссылки из текста.
    
    Returns:
        List of Mega.nz URLs found in text
    """
    # Ищем ссылки на Mega.nz (включая # и ! в URL)
    pattern = r'https?://mega\.(?:nz|co\.nz)/[^\s<>"\')\]]*'
    matches = re.findall(pattern, text)
    return matches


def download_from_mega(
    url: str,
    output_path: Path,
) -> Path:
    """
    Скачивает файл с Mega.nz.
    
    Args:
        url: Публичная ссылка на Mega.nz файл
        output_path: Путь для сохранения файла
    
    Returns:
        Path к скачанному файлу
    
    Raises:
        MegaDownloadError: Если скачивание не удалось
    """
    start_time = time.time()
    
    try:
        from mega import Mega
    except ImportError:
        logger.error("❌ Библиотека mega.py не установлена")
        raise MegaDownloadError(
            "❌ Mega.nz поддержка не настроена на сервере. "
            "Попробуйте другой способ загрузки файла."
        )
    
    logger.info(f"🔽 Начинаю скачивание с Mega.nz: {url}")
    logger.info(f"⏱️  Начало скачивания: {time.strftime('%H:%M:%S')}")
    
    try:
        # Создаём анонимное подключение
        mega = Mega()
        m = mega.login()  # anonymous login
        
        logger.info(f"🔐 Анонимное подключение к Mega.nz установлено")
        
        # Скачиваем файл
        # mega.py скачивает во временную папку, потом перемещает
        dest_folder = output_path.parent
        dest_folder.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"📥 Скачиваю файл в: {dest_folder}")
        
        # download_url возвращает путь к скачанному файлу
        downloaded_file_path = m.download_url(url, dest_path=str(dest_folder))
        
        end_time = time.time()
        download_duration = end_time - start_time
        
        logger.info(f"✅ Скачивание завершено за {download_duration:.1f} сек")
        logger.info(f"📦 Скачанный файл: {downloaded_file_path}")
        
        # Переименовываем в нужное имя, если отличается
        downloaded_path = Path(downloaded_file_path)
        if downloaded_path != output_path:
            logger.info(f"📝 Переименовываю: {downloaded_path.name} -> {output_path.name}")
            downloaded_path.rename(output_path)
            downloaded_path = output_path
        
    except ImportError as import_exc:
        logger.error(f"❌ Import error: {import_exc}", exc_info=True)
        raise MegaDownloadError(
            "❌ Mega.nz поддержка не настроена. Используйте Telegram или другой сервис."
        )
    
    except Exception as exc:
        elapsed = time.time() - start_time
        error_msg = str(exc).lower()
        
        logger.error(f"❌ Ошибка при скачивании после {elapsed:.1f} сек: {exc}", exc_info=True)
        
        # Проверяем типичные ошибки
        if 'quota' in error_msg or 'bandwidth' in error_msg:
            raise MegaDownloadError(
                "❌ Превышена квота на скачивание с Mega.nz (10 GB/день для анонимных пользователей).\n"
                "Попробуйте:\n"
                "1. Подождать несколько часов\n"
                "2. Использовать другой сервис (Telegram, Dropbox)"
            )
        elif 'not found' in error_msg or '404' in error_msg:
            raise MegaDownloadError(
                "❌ Файл не найден. Проверьте, что ссылка правильная и файл не удалён."
            )
        elif 'expired' in error_msg or 'invalid' in error_msg:
            raise MegaDownloadError(
                "❌ Ссылка недействительна или истекла. Запросите новую ссылку."
            )
        elif 'timeout' in error_msg:
            raise MegaDownloadError(
                "⏱️ Превышено время ожидания при скачивании с Mega.nz. Попробуйте ещё раз."
            )
        elif 'connection' in error_msg:
            raise MegaDownloadError(
                "🔌 Потеряно соединение с Mega.nz. Проверьте интернет-соединение."
            )
        else:
            raise MegaDownloadError(f"❌ Не удалось скачать файл с Mega.nz: {exc}")
    
    # Проверяем, что файл скачался
    if not output_path.exists():
        raise MegaDownloadError("❌ Файл не найден после скачивания")
    
    file_size = output_path.stat().st_size
    logger.info(f"📏 Размер скачанного файла: {file_size:,} байт ({file_size / (1024*1024):.2f} MB)")
    
    if file_size == 0:
        raise MegaDownloadError("❌ Скачан пустой файл")
    
    total_duration = time.time() - start_time
    avg_speed_mbps = (file_size / (1024 * 1024)) / total_duration if total_duration > 0 else 0
    logger.info(f"🎉 Файл успешно скачан за {total_duration:.1f} сек (средняя скорость: {avg_speed_mbps:.2f} MB/s)")
    
    return output_path
