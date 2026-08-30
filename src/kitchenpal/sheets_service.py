import gspread
from oauth2client.service_account import ServiceAccountCredentials

from .config import AppConfig, GOOGLE_SHEETS_SCOPE
from .sheets.accounts import AccountSheetsMixin
from .sheets.day_to_day import DayToDaySheetsMixin
from .sheets.feedback import FeedbackSheetsMixin
from .sheets.models import (
    AccountStatement,
    AndetRow,
    DayRow,
    DayToDayEntries,
    DaySummary,
    DrinkEntry,
    FeedbackEntry,
    PersonalAccountEntry,
    PlanningEntry,
    PurchaseEntry,
    RoomEntry,
    TransactionEntry,
)
from .sheets.log import LogEntry, LogSheetsMixin
from .sheets.months import MonthSheetsMixin
from .sheets.planning import PlanningSheetsMixin
from .sheets.transient import retry_reads


class SheetsService(AccountSheetsMixin, PlanningSheetsMixin, DayToDaySheetsMixin, MonthSheetsMixin, FeedbackSheetsMixin, LogSheetsMixin):
    def __init__(self, config: AppConfig):
        if config.google_credentials_info:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(config.google_credentials_info, GOOGLE_SHEETS_SCOPE)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name(config.credentials_file, GOOGLE_SHEETS_SCOPE)
        client = gspread.authorize(creds)
        # Opening the spreadsheet is a read, and it is the first thing every
        # session does — so a few seconds of Google being unavailable used to
        # take the whole app down for whoever arrived during them.
        self._spreadsheet = retry_reads(lambda: client.open(config.spreadsheet_name))
        self._template_sheet_name = config.template_sheet_name

    def list_sheets(self) -> list[str]:
        return [ws.title for ws in retry_reads(self._spreadsheet.worksheets)]

    def get_worksheet(self, worksheet_name: str):
        """A worksheet handle, kept once we have it.

        gspread's Spreadsheet.worksheet() re-fetches the whole sheet list on
        every call — a round trip of its own before any data is read. Holding
        the handle turned out to be a third of every page's traffic.
        """
        cache = self.__dict__.setdefault("_worksheet_cache", {})
        worksheet = cache.get(worksheet_name)
        if worksheet is None:
            worksheet = retry_reads(lambda: self._spreadsheet.worksheet(worksheet_name))
            cache[worksheet_name] = worksheet
        return worksheet

    def forget_worksheets(self) -> None:
        """Drop the handles: a sheet was added, renamed or deleted."""
        self.__dict__.pop("_worksheet_cache", None)


__all__ = [
    "AccountStatement",
    "AndetRow",
    "DayRow",
    "DayToDayEntries",
    "DaySummary",
    "DrinkEntry",
    "FeedbackEntry",
    "LogEntry",
    "PersonalAccountEntry",
    "PlanningEntry",
    "PurchaseEntry",
    "RoomEntry",
    "SheetsService",
    "TransactionEntry",
]
