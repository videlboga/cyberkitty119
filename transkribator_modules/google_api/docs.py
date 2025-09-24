"""Google Docs helper functions."""

from __future__ import annotations

from googleapiclient.errors import HttpError

from transkribator_modules.config import logger
from .service import build_service


def create_doc(credentials, folder_id: str, title: str, blocks: list[str]) -> dict:
    docs = build_service('docs', 'v1', credentials)
    drive = build_service('drive', 'v3', credentials)

    try:
        doc = docs.documents().create(body={'title': title}).execute()
        doc_id = doc.get('documentId')

        requests = []
        cursor = 1
        for block in blocks:
            requests.append({'insertText': {'location': {'index': cursor}, 'text': block + '\n'}})
            cursor += len(block) + 1

        if requests:
            docs.documents().batchUpdate(documentId=doc_id, body={'requests': requests}).execute()

        # Move the document into target folder
        drive.files().update(
            fileId=doc_id,
            addParents=folder_id,
            removeParents='root',
            fields='id, webViewLink',
        ).execute()

        file = drive.files().get(fileId=doc_id, fields='id, webViewLink').execute()
        return {'doc_id': doc_id, 'link': file.get('webViewLink')}
    except HttpError as exc:
        logger.error("Failed to create Google Doc", extra={"error": str(exc)})
        raise
