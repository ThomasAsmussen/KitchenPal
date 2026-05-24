from dataclasses import dataclass
import os


@dataclass(frozen=True)
class AppConfig:
    credentials_file: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "koekkenregnskab-3d-ny-040a2ee5b105.json")
    spreadsheet_name: str = os.getenv("KITCHEN_SPREADSHEET_NAME", "Køkkenregnskab 3D ny")
    template_sheet_name: str = os.getenv("KITCHEN_TEMPLATE_SHEET", "Skabelon")


GOOGLE_SHEETS_SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
]
