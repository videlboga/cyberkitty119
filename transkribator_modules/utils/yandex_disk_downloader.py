"""Yandex.Disk file downloader for large public files (up to 50 GB)."""

from __future__ import annotations

import re
import time
import requests
from pathlib import Path
from typing import Optional

from transkribator_modules.config import logger


class YandexDiskDownloadError(Exception):
    """Ошибка при скачивании с Яндекс.Диска."""
    pass


def extract_yandex_disk_id(url: str) -> Optional[str]:
    """
    Извлекает публичную ссылку из различных форматов Яндекс.Диска.
    
    Поддерживаемые форматы:
    - https://disk.yandex.ru/d/HASH
    - https://disk.yandex.com/d/HASH
    - https://yadi.sk/d/HASH
    - https://disk.yandex.ru/i/HASH (файл)
    """
    # Возвращаем полный URL, так как API работает с полными ссылками
    if is_yandex_disk_link(url):
        return url
    return None


def is_yandex_disk_link(url: str) -> bool:
    """Проверяет, является ли URL ссылкой на Яндекс.Диск."""
    return bool(re.search(r'(disk\.yandex\.(ru|com)|yadi\.sk)', url))


def extract_yandex_disk_links(text: str) -> list[str]:
    """
    Извлекает все ссылки на Яндекс.Диск из текста.
    
    Returns:
        List of Yandex.Disk URLs found in text
    """
    # Ищем ссылки на Яндекс.Диск
    pattern = r'https?://(?:disk\.yandex\.(?:ru|com)|yadi\.sk)/[^\s<>"\')\]]*'
    matches = re.findall(pattern, text)
    return matches


def download_from_yandex_disk(
    url: str,
    output_path: Path,
    chunk_size: int = 8192,
    timeout: int = 300,
) -> Path:
    """
    Скачивает файл с Яндекс.Диска через публичную ссылку.
    
    Args:
        url: Публичная ссылка на Яндекс.Диск файл
        output_path: Путь для сохранения файла
        chunk_size: Размер чанка для потоковой загрузки (байты)
        timeout: Таймаут для каждого чанка (секунды)
    
    Returns:
        Path к скачанному файлу
    
    Raises:
        YandexDiskDownloadError: Если скачивание не удалось
    """
    start_time = time.time()
    
    logger.info(f"🔽 Начинаю скачивание с Яндекс.Диска: {url}")
    logger.info(f"⏱️  Начало скачивания: {time.strftime('%H:%M:%S')}")
    
    try:
        # Получаем прямую ссылку на скачивание через API Яндекс.Диска
        # API не требует авторизации для публичных файлов
        api_url = "https://cloud-api.yandex.net/v1/disk/public/resources/download"
        params = {"public_key": url}
        
        logger.info(f"🔗 Получаю прямую ссылку через API: {api_url}")
        
        response = requests.get(api_url, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        download_url = data.get("href")
        
        if not download_url:
            raise YandexDiskDownloadError(
                "❌ Не удалось получить ссылку на скачивание. "
                "Проверьте, что файл доступен по публичной ссылке."
            )
        
        logger.info(f"✅ Получена прямая ссылка на скачивание")
        logger.info(f"📥 Начинаю потоковую загрузку...")
        
        # Скачиваем файл потоково
        download_response = requests.get(download_url, stream=True, timeout=timeout)
        download_response.raise_for_status()
        
        # Получаем размер файла, если доступен
        total_size = int(download_response.headers.get('content-length', 0))
        logger.info(f"📏 Размер файла: {total_size:,} байт ({total_size / (1024*1024):.2f} MB)")
        
        downloaded_size = 0
        last_log_time = time.time()
        
        with open(output_path, 'wb') as f:
            for chunk in download_response.iter_content(chunk_size=chunk_size):
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
        raise YandexDiskDownloadError(f"⏱️ Превышено время ожидания при скачивании с Яндекс.Диска")
    
    except requests.exceptions.ConnectionError as conn_exc:
        elapsed = time.time() - start_time
        logger.error(f"🔌 CONNECTION ERROR при скачивании после {elapsed:.1f} сек: {conn_exc}", exc_info=True)
        raise YandexDiskDownloadError(f"🔌 Потеряно соединение с Яндекс.Диском")
    
    except requests.exceptions.HTTPError as http_exc:
        status_code = http_exc.response.status_code if http_exc.response else 'unknown'
        logger.error(f"❌ HTTP ERROR {status_code}: {http_exc}", exc_info=True)
        
        if status_code == 404:
            raise YandexDiskDownloadError(
                "❌ Файл не найден (404). Проверьте, что ссылка правильная и файл не удалён."
            )
        elif status_code == 403:
            raise YandexDiskDownloadError(
                "❌ Доступ запрещён (403). Убедитесь, что файл доступен по публичной ссылке."
            )
        elif status_code == 429:
            raise YandexDiskDownloadError(
                "❌ Превышена квота (429). Яндекс.Диск: 10 GB/день для бесплатных аккаунтов.\n"
                "Попробуйте позже или используйте другой сервис."
            )
        elif status_code == 507:
            raise YandexDiskDownloadError(
                "❌ Недостаточно места на диске (507)."
            )
        else:
            raise YandexDiskDownloadError(f"❌ Ошибка HTTP {status_code} при скачивании")
    
    except Exception as exc:
        elapsed = time.time() - start_time
        error_msg = str(exc).lower()
        logger.error(f"❌ Неожиданная ошибка при скачивании после {elapsed:.1f} сек: {exc}", exc_info=True)
        
        # Проверяем специфичные ошибки в ответе API
        if 'not found' in error_msg or 'ресурс не найден' in error_msg:
            raise YandexDiskDownloadError(
                "❌ Файл не найден. Проверьте, что ссылка правильная и файл существует."
            )
        elif 'quota' in error_msg or 'квота' in error_msg:
            raise YandexDiskDownloadError(
                "❌ Превышена квота скачиваний (10 GB/день). Попробуйте позже."
            )
        else:
            raise YandexDiskDownloadError(f"❌ Не удалось скачать файл с Яндекс.Диска: {exc}")
    
    # Проверяем, что файл скачался
    if not output_path.exists():
        raise YandexDiskDownloadError("❌ Файл не найден после скачивания")
    
    file_size = output_path.stat().st_size
    logger.info(f"📏 Размер скачанного файла: {file_size:,} байт ({file_size / (1024*1024):.2f} MB)")
    
    if file_size == 0:
        raise YandexDiskDownloadError("❌ Скачан пустой файл")
    
    total_duration = time.time() - start_time
    avg_speed_mbps = (file_size / (1024 * 1024)) / total_duration if total_duration > 0 else 0
    logger.info(f"🎉 Файл успешно скачан за {total_duration:.1f} сек (средняя скорость: {avg_speed_mbps:.2f} MB/s)")
    
    return output_path
