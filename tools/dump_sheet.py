#!/usr/bin/env python3
"""Read-only dump of every worksheet to .cache/*.csv

Authenticates the same way the app does (kitchenpal.config.AppConfig:
GOOGLE_CREDENTIALS_JSON env var, then st.secrets, then keyfile), but with
readonly scopes so it can never write to the sheet.

The dumped CSVs get read into an AI model's context, and residents consented
to sharing their details within the app — not to that. So in the resident
roster ("Kopi af In-House Liste") the personal columns (phone, email,
birthday, study, favorites) are masked character-class-wise: digits -> 0,
letters -> x, punctuation/spacing/@/+/-/: kept, so the format survives but
the real values never land in .cache/. Room number and name stay as-is.
This is a dump-only restriction: the app still reads the real values at
runtime — do not revert this, and do not move it into src/kitchenpal/.
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

# Real contact details stay out of the dump — see module docstring.
ROSTER_SHEET = "Kopi af In-House Liste"
MASKED_HEADERS = {
    "Mobil",
    "E-mail",
    "Studie",
    "Fødselsdag",
    "Yndlingcocktail",
    "Yndlingsfarve",
    "Yndlingssang",
    "Yndlingsret",
    "Yndlingsslik",
}


def _mask(value: str) -> str:
    return "".join("0" if ch.isdigit() else "x" if ch.isalpha() else ch for ch in value)

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
    if ws.title == ROSTER_SHEET and rows:
        masked = {i for i, header in enumerate(rows[0]) if header.strip() in MASKED_HEADERS}
        rows = [rows[0]] + [
            [_mask(cell) if i in masked else cell for i, cell in enumerate(row)]
            for row in rows[1:]
        ]
    p = out / f"{ws.title.replace('/', '_')}.csv"
    with p.open("w", newline="") as f:
        csv.writer(f).writerows(rows)
    print(f"  {p}  ({len(rows)} rows)")
