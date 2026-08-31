import functools
import threading

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from .config import AppConfig, GOOGLE_SHEETS_SCOPE
from .sheets.accounts import AccountSheetsMixin
from .sheets.day_to_day import DayToDaySheetsMixin
from .sheets.feedback import FeedbackSheetsMixin
from .sheets.models import (
    AccountStatement,
    AndetRow,
    BankDetails,
    DayRow,
    DayToDayEntries,
    KitchenFundStatus,
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


def _serialise_requests(http_client, lock: "threading.RLock") -> None:
    """Put a lock around the one method every Sheets call goes through.

    An instance attribute shadows the class method, so every gspread object
    built from this client is covered without patching the library globally
    or wrapping an API surface that could grow underneath us.
    """
    inner = http_client.request

    @functools.wraps(inner)
    def request(*args, **kwargs):
        with lock:
            return inner(*args, **kwargs)

    http_client.request = request


class SheetsService(AccountSheetsMixin, PlanningSheetsMixin, DayToDaySheetsMixin, MonthSheetsMixin, FeedbackSheetsMixin, LogSheetsMixin):
    def __init__(self, config: AppConfig):
        if config.google_credentials_info:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(config.google_credentials_info, GOOGLE_SHEETS_SCOPE)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name(config.credentials_file, GOOGLE_SHEETS_SCOPE)
        client = gspread.authorize(creds)

        # One connection serves the whole house (see runtime_state), so the
        # requests.Session underneath gspread is shared by every session's
        # thread. Serialise it: a read is ~300 ms and the house is fifteen
        # people, so the wait is rare and cheap, while an interleaved
        # read-modify-write is somebody's dinner charged twice.
        self._http_lock = threading.RLock()
        _serialise_requests(client.http_client, self._http_lock)

        if config.spreadsheet_id:
            # open_by_key costs NOTHING: gspread just wraps the id, no request
            # at all. Opening by NAME costs two — a Drive search for a file
            # with that title, then the spreadsheet metadata — measured at
            # 850 ms + 415 ms on a cold session.
            self._spreadsheet = client.open_by_key(config.spreadsheet_id)
        else:
            # No id configured: fall back to the name so nothing breaks, and
            # pay for the search. Opening is a read, and it is the first thing
            # a new process does — a few seconds of Google being unavailable
            # used to take the app down for whoever arrived during them.
            self._spreadsheet = retry_reads(lambda: client.open(config.spreadsheet_name))
        self._template_sheet_name = config.template_sheet_name

    def _load_worksheets(self) -> dict:
        """Every worksheet handle, from ONE metadata fetch.

        gspread's Spreadsheet.worksheet(title) re-fetches the whole document's
        metadata every time, so asking for four sheets by name cost four
        identical round trips. Traced on a cold Dinner load, six such fetches
        came to 2.4 s — more than the six calls that read actual data. One
        fetch returns them all, so the second name onwards is free.
        """
        worksheets = {ws.title: ws for ws in retry_reads(self._spreadsheet.worksheets)}
        self.__dict__["_worksheet_cache"] = worksheets
        return worksheets

    def list_sheets(self) -> list[str]:
        """The sheet names, always fresh — and the handles come with them.

        Deliberately not served from the cache: this is the app's one way of
        noticing a sheet somebody added in the browser, and ui/data.py already
        holds it behind a TTL. Filling the handle cache here is what makes
        every get_worksheet on the page that follows cost nothing.
        """
        return list(self._load_worksheets())

    def get_worksheet(self, worksheet_name: str):
        """A worksheet handle, from the handles loaded in one go."""
        cache = self.__dict__.get("_worksheet_cache")
        if cache is None or worksheet_name not in cache:
            # Not loaded yet, or a name we have not seen — which may be a sheet
            # created since, so look once more before giving up.
            cache = self._load_worksheets()
        worksheet = cache.get(worksheet_name)
        if worksheet is None:
            raise gspread.exceptions.WorksheetNotFound(worksheet_name)
        return worksheet

    def forget_worksheets(self) -> None:
        """Drop the handles: a sheet was added, renamed or deleted."""
        self.__dict__.pop("_worksheet_cache", None)


__all__ = [
    "AccountStatement",
    "BankDetails",
    "KitchenFundStatus",
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
