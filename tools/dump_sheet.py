#!/usr/bin/env python3
"""Read-only dump of every worksheet to .cache/*.csv

Authenticates the same way the app does (kitchenpal.config.AppConfig:
GOOGLE_CREDENTIALS_JSON env var, then st.secrets, then keyfile), but with
readonly scopes so it can never write to the sheet.
"""
import csv
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from kitchenpal.config import AppConfig

READONLY_SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

config = AppConfig()
if config.google_credentials_info:
    creds = ServiceAccountCredentials.from_json_keyfile_dict(config.google_credentials_info, READONLY_SCOPE)
else:
    creds = ServiceAccountCredentials.from_json_keyfile_name(config.credentials_file, READONLY_SCOPE)
sh = gspread.authorize(creds).open(config.spreadsheet_name)

out = pathlib.Path(".cache")
out.mkdir(exist_ok=True)
print(f"Dumping: {sh.title}")
for ws in sh.worksheets():
    rows = ws.get_all_values()
    p = out / f"{ws.title.replace('/', '_')}.csv"
    with p.open("w", newline="") as f:
        csv.writer(f).writerows(rows)
    print(f"  {p}  ({len(rows)} rows)")
