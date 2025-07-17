"""Утилиты для работы с Google Docs через сервис-аккаунт.

Основная точка входа – функция create_transcript_google_doc(),
которую вызывает processor.py, когда транскрипция слишком длинная.
Файл был случайно урезан; восстанавливаю полноценную реализацию.
"""

import os
from pathlib import Path
from typing import Optional, Callable
import asyncio
import socket

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import httplib2
from google_auth_httplib2 import AuthorizedHttp  # Используем для авторизации кастомного HTTP

from transkribator_modules.config import logger

# Области доступа: создаём документ и управляем файлами на Google Drive
SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]

# Путь к JSON-файлу сервис-аккаунта можно переопределить переменной окружения
DEFAULT_CREDS_PATH = "/app/credentials/google-sa.json"

# Таймаут 300 с; параметр retries не поддерживается в версии httplib2 внутри контейнера
# Создаём объект HTTP, который затем авторизуем через google-auth-httplib2
_HTTP = httplib2.Http(timeout=300)


def _get_credentials() -> Credentials:
    """Возвращает учетные данные сервис-аккаунта."""

    # Возможные варианты:
    # 1. Явно указан GOOGLE_CREDENTIALS_PATH (наш приоритет)
    # 2. Стандартная переменная Google SDK – GOOGLE_APPLICATION_CREDENTIALS
    # 3. Путь по умолчанию внутри контейнера
    creds_path = (
        os.getenv("GOOGLE_CREDENTIALS_PATH")
        or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        or DEFAULT_CREDS_PATH
    )

    if not Path(creds_path).exists():
        raise FileNotFoundError(
            f"Файл ключа сервис-аккаунта не найден: {creds_path}. "
            "Положи его в ./data либо укажи путь через переменную GOOGLE_CREDENTIALS_PATH."
        )

    return Credentials.from_service_account_file(creds_path, scopes=SCOPES)


async def create_transcript_google_doc(
    transcript_text: str,
    video_filename: str,
    chat_id: Optional[int] = None,
) -> Optional[str]:
    """Асинхронно создаёт Google Doc с транскрипцией и (опционально) переносит его в указанную папку.

    Обёртка выполняет блокирующую работу Google API в пуле потоков,
    поэтому функцию можно безопасно *await*-ить из обработчиков Telegram-бота.
    Возвращает URL созданного документа или None, если произошла ошибка.
    """

    def _sync_create() -> Optional[str]:
        try:
            socket.setdefaulttimeout(300)

            creds = _get_credentials()

            # Авторизуем ранее созданный HTTP-клиент, чтобы не передавать одновременно
            # credentials и http (эти аргументы взаимно исключают друг друга).
            authed_http = AuthorizedHttp(creds, http=_HTTP)

            # Выключаем discovery-кэш, чтобы не плодить файлы в контейнере
            docs_service = build("docs", "v1", http=authed_http, cache_discovery=False)
            drive_service = build("drive", "v3", http=authed_http, cache_discovery=False)

            title = f"Транскрипция – {video_filename}"

            # 1. Создаём пустой документ
            doc_meta = docs_service.documents().create(body={"title": title}).execute()
            document_id = doc_meta.get("documentId")

            # 2. Вставляем текст после заголовка (index=1)
            requests = [
                {
                    "insertText": {
                        "location": {"index": 1},
                        "text": transcript_text,
                    }
                }
            ]
            docs_service.documents().batchUpdate(
                documentId=document_id, body={"requests": requests}
            ).execute()

            # 3. Перемещаем документ в целевую папку, если она задана
            target_folder = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
            if target_folder:
                try:
                    drive_service.files().update(
                        fileId=document_id,
                        addParents=target_folder,
                        removeParents="root",
                        fields="id, parents",
                    ).execute()
                    logger.info(f"Документ перемещён в папку {target_folder}")
                except Exception as move_err:
                    logger.error(
                        f"Не удалось переместить документ {document_id} в папку {target_folder}: {move_err}"
                    )

            doc_url = f"https://docs.google.com/document/d/{document_id}/edit"
            logger.info(f"Создан Google Doc {doc_url} для chat_id={chat_id}")
            return doc_url

        except Exception as e:
            logger.error(f"Ошибка создания Google Doc: {e}")
            return None

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync_create) 