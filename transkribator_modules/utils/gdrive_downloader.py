"""Google Drive file downloader for large public files (2-3 GB) without OAuth."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Optional

from transkribator_modules.config import logger


class GDriveDownloadError(Exception):
    """Ошибка при скачивании с Google Drive."""
    pass


def extract_gdrive_id(url: str) -> Optional[str]:
    """
    Извлекает file_id из различных форматов Google Drive ссылок.
    
    Поддерживаемые форматы:
    - https://drive.google.com/file/d/FILE_ID/view
    - https://drive.google.com/open?id=FILE_ID
    - https://drive.google.com/uc?id=FILE_ID
    - https://docs.google.com/document/d/FILE_ID/
    - https://docs.google.com/spreadsheets/d/FILE_ID/
    """
    patterns = [
        r'/file/d/([a-zA-Z0-9_-]+)',
        r'[?&]id=([a-zA-Z0-9_-]+)',
        r'/d/([a-zA-Z0-9_-]+)',
        r'/document/d/([a-zA-Z0-9_-]+)',
        r'/spreadsheets/d/([a-zA-Z0-9_-]+)',
        r'/presentation/d/([a-zA-Z0-9_-]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None


def is_gdrive_link(url: str) -> bool:
    """Проверяет, является ли URL ссылкой на Google Drive."""
    return bool(re.search(r'drive\.google\.com|docs\.google\.com', url))


def download_from_gdrive(
    url: str,
    output_path: Path,
    *,
    quiet: bool = False,
) -> Path:
    """
    Скачивает файл с Google Drive (работает с большими файлами 2-3 GB).
    
    Использует gdown с параметрами для обхода virus scan warning.
    
    Args:
        url: URL файла на Google Drive
        output_path: Путь для сохранения файла
        quiet: Отключить вывод прогресса
        
    Returns:
        Path к скачанному файлу
        
    Raises:
        GDriveDownloadError: Если не удалось скачать файл
    """
    try:
        import gdown
    except ImportError as exc:
        raise GDriveDownloadError(
            "Библиотека gdown не установлена. "
            "Установите: pip install gdown"
        ) from exc
    
    # Извлекаем file_id
    file_id = extract_gdrive_id(url)
    if not file_id:
        raise GDriveDownloadError(
            f"Не удалось извлечь file_id из URL: {url}\n"
            "Убедитесь, что ссылка имеет формат:\n"
            "https://drive.google.com/file/d/FILE_ID/view"
        )
    
    # Создаём директорию если не существует
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Формируем direct download URL
    download_url = f"https://drive.google.com/uc?id={file_id}"
    
    logger.info(
        "Начинаю скачивание с Google Drive",
        extra={
            "file_id": file_id,
            "output": str(output_path),
            "url": url,
            "download_url": download_url,
        }
    )
    
    start_time = time.time()
    
    try:
        logger.info(f"🔽 Вызываю gdown.download: url={download_url}, output={output_path}, fuzzy=True, quiet={quiet}")
        logger.info(f"⏱️  Начало скачивания: {time.strftime('%H:%M:%S')}")
        
        # КЛЮЧЕВОЙ МОМЕНТ: fuzzy=True помогает с большими файлами
        # verify=False отключает проверку SSL (иногда нужно)
        try:
            result = gdown.download(
                download_url,
                str(output_path),
                quiet=quiet,
                fuzzy=True,  # Обходит virus scan warning!
            )
        except KeyboardInterrupt:
            logger.warning("⚠️ Скачивание прервано пользователем (KeyboardInterrupt)")
            raise
        except TimeoutError as timeout_exc:
            logger.error(f"⏱️ TIMEOUT при скачивании: {timeout_exc}", exc_info=True)
            raise GDriveDownloadError(
                f"⏱️ Превышено время ожидания при скачивании с Google Drive.\n"
                f"Возможные причины:\n"
                f"1. Нестабильное интернет-соединение\n"
                f"2. Google Drive ограничил скорость загрузки\n"
                f"3. Файл слишком большой для текущих условий\n\n"
                f"Попробуйте отправить файл напрямую в бот или через другой хостинг."
            ) from timeout_exc
        except ConnectionError as conn_exc:
            logger.error(f"🔌 CONNECTION ERROR при скачивании: {conn_exc}", exc_info=True)
            raise GDriveDownloadError(
                f"🔌 Потеряно соединение с Google Drive во время скачивания.\n"
                f"Попробуйте ещё раз через несколько минут."
            ) from conn_exc
        
        end_time = time.time()
        download_duration = end_time - start_time
        
        logger.info(f"✅ gdown.download завершён за {download_duration:.1f} сек")
        logger.info(f"📦 gdown.download вернул: {result}, type={type(result)}")
        logger.info(f"⏱️  Окончание скачивания: {time.strftime('%H:%M:%S')}")
        
        if result is None:
            logger.error("❌ gdown вернул None - файл не скачан")
            raise GDriveDownloadError(
                "gdown вернул None - возможно файл приватный или удалён"
            )
        
    except GDriveDownloadError:
        # Пробрасываем наши собственные ошибки дальше
        raise
    except GDriveDownloadError:
        # Пробрасываем наши собственные ошибки дальше
        raise
    except Exception as exc:
        elapsed = time.time() - start_time
        logger.error(
            f"💥 Неожиданная ошибка при скачивании с Google Drive после {elapsed:.1f} сек: {exc}",
            exc_info=True
        )
        error_msg = str(exc).lower()
        
        # Обрабатываем специфичные ошибки
        if "quota" in error_msg or "limit" in error_msg:
            raise GDriveDownloadError(
                "❌ Превышена квота скачивания Google Drive.\n"
                "Решения:\n"
                "1. Попробуйте через несколько часов\n"
                "2. Отправьте файл напрямую в бот\n"
                "3. Загрузите на другой хостинг (Dropbox, WeTransfer)"
            ) from exc
        
        if "access denied" in error_msg or "403" in error_msg:
            raise GDriveDownloadError(
                "❌ Доступ к файлу запрещён.\n"
                "Убедитесь что файл:\n"
                "1. Открыт для доступа 'Всем, у кого есть ссылка'\n"
                "2. Не находится в корзине\n"
                "3. Не был удалён"
            ) from exc
        
        if "not found" in error_msg or "404" in error_msg:
            raise GDriveDownloadError(
                "❌ Файл не найден на Google Drive.\n"
                "Проверьте корректность ссылки."
            ) from exc
        
        if "timeout" in error_msg or "timed out" in error_msg:
            raise GDriveDownloadError(
                f"⏱️ Превышено время ожидания ({elapsed:.1f} сек).\n"
                f"Google Drive не ответил вовремя.\n"
                f"Попробуйте ещё раз или используйте другой хостинг."
            ) from exc
        
        # Общая ошибка
        raise GDriveDownloadError(
            f"Не удалось скачать файл с Google Drive (после {elapsed:.1f} сек): {exc}"
        ) from exc
    
    # Проверяем что файл скачался
    logger.info(f"🔍 Проверяю существование файла: {output_path}")
    if not output_path.exists():
        logger.error(f"❌ Файл НЕ СУЩЕСТВУЕТ после gdown.download: {output_path}")
        raise GDriveDownloadError(
            "Файл не был создан после скачивания. "
            "Возможно, недостаточно места на диске."
        )
    
    file_size = output_path.stat().st_size
    logger.info(f"📏 Размер скачанного файла: {file_size:,} байт ({file_size / (1024*1024):.2f} MB)")
    
    # Проверяем что скачали не HTML ошибку
    if file_size < 10_000:  # Меньше 10 KB подозрительно
        logger.warning(f"⚠️ Файл подозрительно маленький ({file_size} байт), проверяю на HTML...")
        with open(output_path, 'rb') as f:
            first_bytes = f.read(512)
            if b'<!DOCTYPE html>' in first_bytes or b'<html' in first_bytes:
                logger.error("❌ Обнаружен HTML вместо файла!")
                output_path.unlink()  # Удаляем HTML
                raise GDriveDownloadError(
                    "❌ Google Drive вернул HTML страницу вместо файла.\n"
                    "Возможные причины:\n"
                    "1. Файл слишком популярен (превышена квота)\n"
                    "2. Файл приватный (нужен доступ)\n"
                    "3. Требуется авторизация для больших файлов\n\n"
                    "Решение: отправьте файл напрямую в бот."
                )
        logger.info("✅ Файл маленький, но это не HTML - всё в порядке")
    
    duration = time.time() - start_time
    avg_speed_mbps = (file_size / (1024 * 1024)) / duration if duration > 0 else 0
    
    logger.info(
        f"🎉 Файл успешно скачан с Google Drive за {duration:.1f} сек (средняя скорость: {avg_speed_mbps:.2f} MB/s)",
        extra={
            "file_id": file_id,
            "size_mb": file_size / (1024 * 1024),
            "duration_sec": duration,
            "avg_speed_mbps": avg_speed_mbps,
            "output": str(output_path),
        }
    )
    
    return output_path


def extract_gdrive_links(text: str) -> list[str]:
    """
    Извлекает все ссылки Google Drive из текста.
    
    Returns:
        Список найденных URL
    """
    patterns = [
        r'https://drive\.google\.com/file/d/[a-zA-Z0-9_-]+[^\s]*',
        r'https://drive\.google\.com/open\?id=[a-zA-Z0-9_-]+[^\s]*',
        r'https://docs\.google\.com/document/d/[a-zA-Z0-9_-]+[^\s]*',
        r'https://docs\.google\.com/spreadsheets/d/[a-zA-Z0-9_-]+[^\s]*',
        r'https://docs\.google\.com/presentation/d/[a-zA-Z0-9_-]+[^\s]*',
    ]
    
    links = []
    for pattern in patterns:
        found = re.findall(pattern, text)
        links.extend(found)
    
    # Убираем дубликаты
    return list(set(links))


# Пример использования
if __name__ == "__main__":
    # Тестовая ссылка (замените на свою)
    test_url = "https://drive.google.com/file/d/1XXXXX/view"
    output = Path("/tmp/test_download.mp4")
    
    try:
        result = download_from_gdrive(test_url, output)
        print(f"✅ Файл скачан: {result}")
        print(f"Размер: {result.stat().st_size / (1024*1024):.2f} MB")
    except GDriveDownloadError as e:
        print(f"❌ Ошибка: {e}")
