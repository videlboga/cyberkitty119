"""Google Drive helper functions."""

from __future__ import annotations

from typing import Optional

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaInMemoryUpload

from transkribator_modules.config import logger
from .service import build_service

ROOT_FOLDER_NAME = "CyberKitty"
SUBFOLDERS = [
    "Inbox",
    "Ideas",
    "Meetings",
    "Tasks",
    "Resources",
    "Journal",
]


def _find_item(service, name: str, mime_type: str, parent_id: Optional[str]) -> Optional[str]:
    query_parts = [f"mimeType = '{mime_type}'", f"name = '{name}'"]
    if parent_id:
        query_parts.append(f"'{parent_id}' in parents")
    else:
        query_parts.append("'root' in parents")
    query = " and ".join(query_parts)
    results = service.files().list(q=query, spaces='drive', fields="files(id, name)").execute()
    files = results.get('files', [])
    return files[0]['id'] if files else None


def _find_folder(service, name: str, parent_id: Optional[str] = None) -> Optional[str]:
    return _find_item(service, name, 'application/vnd.google-apps.folder', parent_id)


def _create_folder(service, name: str, parent_id: Optional[str]) -> str:
    file_metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
    }
    if parent_id:
        file_metadata['parents'] = [parent_id]
    folder = service.files().create(body=file_metadata, fields='id').execute()
    return folder['id']


def ensure_tree(credentials, username: str) -> dict:
    """Ensure the Google Drive folder structure exists for the user."""

    drive = build_service('drive', 'v3', credentials)
    try:
        root_id = _find_folder(drive, ROOT_FOLDER_NAME)
        if not root_id:
            root_id = _create_folder(drive, ROOT_FOLDER_NAME, None)

        user_folder_name = username or 'user'
        user_folder_id = _find_folder(drive, user_folder_name, root_id)
        if not user_folder_id:
            user_folder_id = _create_folder(drive, user_folder_name, root_id)

        folders = {'root': root_id, 'user': user_folder_id}
        for name in SUBFOLDERS:
            folder_id = _find_folder(drive, name, user_folder_id)
            if not folder_id:
                folder_id = _create_folder(drive, name, user_folder_id)
            folders[name] = folder_id

        index_folder_id = _find_folder(drive, 'Index', user_folder_id)
        if not index_folder_id:
            index_folder_id = _create_folder(drive, 'Index', user_folder_id)
        folders['Index'] = index_folder_id

        sheet_id = _find_item(
            drive,
            'Index (Google Sheet)',
            'application/vnd.google-apps.spreadsheet',
            index_folder_id,
        )
        if not sheet_id:
            sheet_metadata = {
                'name': 'Index (Google Sheet)',
                'mimeType': 'application/vnd.google-apps.spreadsheet',
                'parents': [index_folder_id],
            }
            sheet = drive.files().create(body=sheet_metadata, fields='id').execute()
            sheet_id = sheet['id']
        folders['IndexSheet'] = sheet_id
        return folders
    except HttpError as exc:
        logger.error("Google Drive ensure_tree failed", extra={"error": str(exc)})
        raise


def upload_markdown(credentials, folder_id: str, filename: str, markdown_text: str) -> dict:
    drive = build_service('drive', 'v3', credentials)
    metadata = {
        'name': filename,
        'mimeType': 'text/markdown',
        'parents': [folder_id],
    }
    try:
        media = MediaInMemoryUpload(markdown_text.encode('utf-8'), mimetype='text/markdown', resumable=False)
        file = drive.files().create(body=metadata, media_body=media, fields='id, webViewLink').execute()
        return file
    except HttpError as exc:
        logger.error("Failed to upload markdown", extra={"error": str(exc)})
        raise
