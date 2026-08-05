from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from ..constants import LOG_HEADERS, LOG_SHEET_NAME

# Column ↔ dataclass field mapping. Readers and writers go by header name,
# never by column index — see "Log sheet schema" in CLAUDE.md.
_FIELD_BY_HEADER = {
    "Timestamp": "timestamp",
    "Event": "event",
    "Summary": "summary",
    "Action id": "action_id",
    "Month sheet": "month_sheet",
    "By": "by",
    "Person": "person",
    "From": "from_label",
    "To": "to_label",
    "Balance": "balance",
    "Room intent": "room_intent",
}


@dataclass
class LogEntry:
    event: str = ""
    summary: str = ""
    action_id: str = ""
    month_sheet: str = ""
    by: str = ""
    person: str = ""
    from_label: str = ""
    to_label: str = ""
    balance: object = ""
    room_intent: str = ""
    timestamp: str = ""


class LogSheetsMixin:
    def append_log_entries(self, entries: list[LogEntry]) -> None:
        worksheet = self.get_worksheet(LOG_SHEET_NAME)
        stamp = datetime.now(ZoneInfo("Europe/Copenhagen")).strftime("%Y-%m-%d %H:%M:%S")

        rows = []
        existing = worksheet.get_all_values()
        if not any(any(str(cell).strip() for cell in row) for row in existing):
            rows.append(list(LOG_HEADERS))

        for entry in entries:
            values = {field: getattr(entry, field) for field in _FIELD_BY_HEADER.values()}
            values["timestamp"] = entry.timestamp or stamp
            rows.append([values[_FIELD_BY_HEADER[header]] for header in LOG_HEADERS])

        worksheet.append_rows(rows, value_input_option="USER_ENTERED")

    def get_log_entries(self) -> list[LogEntry]:
        worksheet = self.get_worksheet(LOG_SHEET_NAME)
        rows = worksheet.get_all_values()
        if not rows:
            return []

        header = [str(cell).strip() for cell in rows[0]]
        entries = []
        for row in rows[1:]:
            if not any(str(cell).strip() for cell in row):
                continue
            entry = LogEntry()
            for index, header_name in enumerate(header):
                field = _FIELD_BY_HEADER.get(header_name)
                if field and index < len(row):
                    setattr(entry, field, row[index])
            entries.append(entry)

        entries.reverse()
        return entries
