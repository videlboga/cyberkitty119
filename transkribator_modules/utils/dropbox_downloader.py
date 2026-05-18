"""Dropbox file downloader for large public files (2-3 GB) without OAuth."""

from __future__ import annotations

import re
import time
import requests
from pathlib import Path
from typing import Optional

from transkribator_modules.config import logger


class DropboxDownloadError(Exception):
    """Ошибка при скачивании с Dropbox."""
    pass


def extract_dropbox_id(url: str) -> Optional[str]:
    """
    Извлекает полный путь файла из Dropbox ссылок и возвращает direct download URL.
    
    Поддерживаемые форматы:
    - https://www.dropbox.com/s/HASH/filename.ext?dl=0
    - https://www.dropbox.com/scl/fi/HASH/filename.ext?rlkey=KEY&dl=0
    - https://dropbox.com/s/HASH/filename.ext
    """
    # Dropbox делает редирект, достаточно заменить dl=0 на dl=1
    if 'dropbox.com' in url:
        # Убираем параметры и заменяем на dl=1
        base_url = url.split('?')[0]
        return f"{base_url}?dl=1"
    return None


def is_dropbox_link(url: str) -> bool:
    """Проверяет, является ли URL ссылкой на Dropbox."""
    return bool(re.search(r'dropbox\.com', url))


def extract_dropbox_links(text: str) -> list[str]:
    """
    Извлекает все Dropbox ссылки из текста.
    
    Returns:
        List of Dropbox URLs found in text
    """
    # Ищем ссылки на Dropbox
    pattern = r'https?://(?:www\.)?dropbox\.com/[^\s<>"\')]*'
    matches = re.findall(pattern, text)
    return matches


def download_from_dropbox(
    url: str,
    output_path: Path,
    chunk_size: int = 8192,
    timeout: int = 300,
) -> Path:
    """
    Скачивает файл с Dropbox.
    
    Args:
        url: Публичная ссылка на Dropbox файл
        output_path: Путь для сохранения файла
        chunk_size: Размер чанка для потоковой загрузки (байты)
        timeout: Таймаут для каждого чанка (секунды)
    
    Returns:
        Path к скачанному файлу
    
    Raises:
        DropboxDownloadError: Если скачивание не удалось
    """
    start_time = time.time()
    
    # Получаем direct download URL
    download_url = extract_dropbox_id(url)
    if not download_url:
        raise DropboxDownloadError("❌ Не удалось извлечь Dropbox URL")
    
    logger.info(f"🔽 Начинаю скачивание с Dropbox: {download_url}")
    logger.info(f"⏱️  Начало скачивания: {time.strftime('%H:%M:%S')}")
    
    try:
        # Используем requests для потоковой загрузки с прогрессом
        response = requests.get(download_url, stream=True, timeout=timeout)
        response.raise_for_status()
        
        # Получаем размер файла, если доступен
        total_size = int(response.headers.get('content-length', 0))
        logger.info(f"📏 Размер файла: {total_size:,} байт ({total_size / (1024*1024):.2f} MB)")
        
        downloaded_size = 0
        last_log_time = time.time()
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    
                    # Логируем прогресс каждые 10 секунд
                    current_time = time.time()
                    if current_time - last_log_time >= 10:
                        elapsed = current_time - start_time
                        speed_mbps = (downloaded_size / (1024 * 1024)) / elapsed if elapsed > 0 else 0
                        if total_size > 0:
                            progress = (downloaded_size / total_size) * 100
                            logger.info(
                                f"⬇️  Прогресс: {progress:.1f}% "
                                f"({downloaded_size / (1024*1024):.1f} / {total_size / (1024*1024):.1f} MB) "
                                f"@ {speed_mbps:.2f} MB/s"
                            )
                        else:
                            logger.info(
                                f"⬇️  Скачано: {downloaded_size / (1024*1024):.1f} MB "
                                f"@ {speed_mbps:.2f} MB/s"
                            )
                        last_log_time = current_time
        
        end_time = time.time()
        download_duration = end_time - start_time
        
        logger.info(f"✅ Скачивание завершено за {download_duration:.1f} сек")
        
    except requests.exceptions.Timeout as timeout_exc:
        elapsed = time.time() - start_time
        logger.error(f"⏱️ TIMEOUT при скачивании после {elapsed:.1f} сек: {timeout_exc}", exc_info=True)
        raise DropboxDownloadError(f"⏱️ Превышено время ожидания при скачивании с Dropbox")
    
    except requests.exceptions.ConnectionError as conn_exc:
        elapsed = time.time() - start_time
        logger.error(f"🔌 CONNECTION ERROR при скачивании после {elapsed:.1f} сек: {conn_exc}", exc_info=True)
        raise DropboxDownloadError(f"🔌 Потеряно соединение с Dropbox")
    
    except requests.exceptions.HTTPError as http_exc:
        status_code = http_exc.response.status_code if http_exc.response else 'unknown'
        logger.error(f"❌ HTTP ERROR {status_code}: {http_exc}", exc_info=True)
        
        if status_code == 404:
            raise DropboxDownloadError("❌ Файл не найден (404). Проверьте, что ссылка публичная и файл существует")
        elif status_code == 403:
            raise DropboxDownloadError("❌ Доступ запрещён (403). Убедитесь, что файл доступен по публичной ссылке")
        elif status_code == 429:
            raise DropboxDownloadError("❌ Слишком много запросов (429). Попробуйте позже")
        else:
            raise DropboxDownloadError(f"❌ Ошибка HTTP {status_code} при скачивании")
    
    except Exception as exc:
        elapsed = time.time() - start_time
        logger.error(f"❌ Неожиданная ошибка при скачивании после {elapsed:.1f} сек: {exc}", exc_info=True)
        raise DropboxDownloadError(f"❌ Не удалось скачать файл с Dropbox: {exc}")
    
    # Проверяем, что файл скачался
    if not output_path.exists():
        raise DropboxDownloadError("❌ Файл не найден после скачивания")
    
    file_size = output_path.stat().st_size
    logger.info(f"📏 Размер скачанного файла: {file_size:,} байт ({file_size / (1024*1024):.2f} MB)")
    
    if file_size == 0:
        raise DropboxDownloadError("❌ Скачан пустой файл")
    
    total_duration = time.time() - start_time
    avg_speed_mbps = (file_size / (1024 * 1024)) / total_duration if total_duration > 0 else 0
    logger.info(f"🎉 Файл успешно скачан за {total_duration:.1f} сек (средняя скорость: {avg_speed_mbps:.2f} MB/s)")
    
    return output_path
