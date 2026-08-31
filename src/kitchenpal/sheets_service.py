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


# (connect, read). Reads of this sheet run about 300 ms and the slowest thing
# the app does is a month copy, so ten seconds to connect and twenty to answer
# is far outside normal and still bounded.
REQUEST_TIMEOUT_SECONDS = (10, 20)

# There was a lock around gspread's HTTPClient.request here, on the reasoning
# that one shared connection is touched by every session's thread. It was
# removed on 2026-08-31 because both halves of that reasoning were wrong.
#
# gspread does not hand out a bare requests.Session: it builds google-auth's
# AuthorizedSession, whose request() is written for concurrent use (it copies
# the headers per call and says so in a comment), over a connection pool that
# is thread-safe and a cookie jar that holds its own lock. The one unguarded
# race left is a token refresh — two threads can both fetch one, which costs a
# redundant HTTP call about once an hour and leaves both tokens valid.
#
# And the thing the lock was justified with, an interleaved read-modify-write,
# is not something it could ever have prevented: it serialised ONE request at
# a time, while add_drinks reads and writes in four separate ones with the
# lock released in between. See the note there.
#
# What it did do was make every resident wait behind the slowest request in
# the process. Do not put it back without a race that is both real and
# actually covered by a per-request lock.


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
        # gspread ships with NO timeout (HTTPClient.timeout is None), so a
        # stalled socket waits for as long as the network allows — and one
        # connection now serves the whole house, so that is everybody's page,
        # not one person's. Bounded, the worst case is one slow request, and
        # retry_reads gets another go at it.
        client.http_client.set_timeout(REQUEST_TIMEOUT_SECONDS)

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
