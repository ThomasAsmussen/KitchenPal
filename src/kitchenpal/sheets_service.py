import gspread
from oauth2client.service_account import ServiceAccountCredentials

from .config import AppConfig, GOOGLE_SHEETS_SCOPE
from .sheets.accounts import AccountSheetsMixin
from .sheets.day_to_day import DayToDaySheetsMixin
from .sheets.feedback import FeedbackSheetsMixin
from .sheets.models import (
    DayToDayEntries,
    DrinkEntry,
    FeedbackEntry,
    PersonalAccountEntry,
    PlanningEntry,
    PurchaseEntry,
    RoomEntry,
    TransactionEntry,
)
from .sheets.months import MonthSheetsMixin
from .sheets.planning import PlanningSheetsMixin


class SheetsService(AccountSheetsMixin, PlanningSheetsMixin, DayToDaySheetsMixin, MonthSheetsMixin, FeedbackSheetsMixin):
    def __init__(self, config: AppConfig):
        if config.google_credentials_info:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(config.google_credentials_info, GOOGLE_SHEETS_SCOPE)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name(config.credentials_file, GOOGLE_SHEETS_SCOPE)
        client = gspread.authorize(creds)
        self._spreadsheet = client.open(config.spreadsheet_name)
        self._template_sheet_name = config.template_sheet_name

    def list_sheets(self) -> list[str]:
        return [ws.title for ws in self._spreadsheet.worksheets()]

    def get_worksheet(self, worksheet_name: str):
        return self._spreadsheet.worksheet(worksheet_name)


__all__ = [
    "DayToDayEntries",
    "DrinkEntry",
    "FeedbackEntry",
    "PersonalAccountEntry",
    "PlanningEntry",
    "PurchaseEntry",
    "RoomEntry",
    "SheetsService",
    "TransactionEntry",
]
