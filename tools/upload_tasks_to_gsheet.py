#!/usr/bin/env python3
import sys
import os
import csv
from typing import List


def usage():
    print("Usage: upload_tasks_to_gsheet.py <csv_path> <spreadsheet_id> <service_account_json_path>")


def read_csv_rows(csv_path: str) -> List[List[str]]:
    with open(csv_path, newline='') as f:
        reader = csv.reader(f)
        rows = list(reader)
    return rows


def main():
    if len(sys.argv) != 4:
        usage()
        sys.exit(2)

    csv_path = sys.argv[1]
    spreadsheet_id = sys.argv[2]
    creds_path = sys.argv[3]

    if not os.path.exists(csv_path):
        print(f"CSV file not found: {csv_path}")
        sys.exit(1)
    if not os.path.exists(creds_path):
        print(f"Service account JSON not found: {creds_path}")
        sys.exit(1)

    rows = read_csv_rows(csv_path)
    if not rows:
        print("CSV is empty")
        sys.exit(1)

    # lazy import to avoid requiring deps if not run
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except Exception as e:
        print("Required packages not installed: gspread google-auth. Please pip install them.")
        raise

    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    gc = gspread.authorize(creds)

    print(f"Opening spreadsheet {spreadsheet_id} ...")
    sh = gc.open_by_key(spreadsheet_id)
    worksheet = sh.get_worksheet(0)
    if worksheet is None:
        worksheet = sh.add_worksheet(title='Tasks', rows=str(len(rows)+10), cols=str(len(rows[0]) if rows else 10))

    print(f"Clearing existing worksheet contents...")
    worksheet.clear()

    print(f"Updating sheet with {len(rows)-1} tasks (+1 header)...")
    # gspread expects list of lists
    worksheet.update(rows)

    print("Done. Sheet updated.")


if __name__ == '__main__':
    main()
