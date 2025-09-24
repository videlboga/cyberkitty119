"""Google Sheets helper for index upsert."""

from __future__ import annotations

import datetime

from googleapiclient.errors import HttpError

from transkribator_modules.config import logger
from .service import build_service

INDEX_HEADER = [
    'id',
    'date',
    'type',
    'title',
    'tags',
    'drive_path',
    'drive_url',
    'doc_url',
    'extra',
]


def _setup_sheet(sheets_service, sheet_id: str) -> None:
    sheets_service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range='A1:I1',
        valueInputOption='RAW',
        body={'values': [INDEX_HEADER]},
    ).execute()


def upsert_index(credentials, sheet_id: str, row: dict) -> None:
    sheets = build_service('sheets', 'v4', credentials)
    try:
        values = sheets.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range='A1:I1',
        ).execute()
        if not values.get('values'):
            _setup_sheet(sheets, sheet_id)
    except HttpError:
        _setup_sheet(sheets, sheet_id)

    row_values = [
        row.get('id', ''),
        row.get('date', datetime.datetime.utcnow().isoformat()),
        row.get('type', ''),
        row.get('title', ''),
        ', '.join(row.get('tags', []) or []),
        row.get('drive_path', ''),
        row.get('drive_url', ''),
        row.get('doc_url', ''),
        row.get('extra', ''),
    ]

    try:
        sheets.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range='A2',
            valueInputOption='RAW',
            insertDataOption='INSERT_ROWS',
            body={'values': [row_values]},
        ).execute()
    except HttpError as exc:
        logger.error("Failed to append row to Google Sheet", extra={"error": str(exc)})
        raise
