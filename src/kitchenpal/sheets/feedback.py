from datetime import datetime

from ..constants import (
    BUGS_SHEET_NAME,
    FEEDBACK_HEADER_RANGE,
    FEEDBACK_HEADERS,
    FEEDBACK_STATUS_COLUMN,
    NEW_FEATURES_SHEET_NAME,
)
from .models import FeedbackEntry


FEEDBACK_OPEN_STATUS = "Open"
FEEDBACK_DONE_STATUS = "Done"
FEEDBACK_FIXED_STATUS = "Fixed"
FEEDBACK_SHEETS = {
    "feature": NEW_FEATURES_SHEET_NAME,
    "bug": BUGS_SHEET_NAME,
}
FEEDBACK_DONE_STATUSES = {
    "feature": FEEDBACK_DONE_STATUS,
    "bug": FEEDBACK_FIXED_STATUS,
}


class FeedbackSheetsMixin:
    def get_feedback_entries(self, feedback_type: str) -> list[FeedbackEntry]:
        worksheet = self._feedback_worksheet(feedback_type)
        rows = worksheet.get_all_values()
        if not rows:
            self._ensure_feedback_headers(worksheet, rows)
            return []

        self._ensure_feedback_headers(worksheet, rows)
        entries = []
        for row_number, row in enumerate(rows[1:], start=2):
            padded_row = row + [""] * len(FEEDBACK_HEADERS)
            created_at, name, title, details, status = padded_row[: len(FEEDBACK_HEADERS)]
            if not any((created_at, name, title, details)):
                continue
            entries.append(
                FeedbackEntry(
                    row_number=row_number,
                    created_at=created_at,
                    name=name,
                    title=title,
                    details=details,
                    status=status or FEEDBACK_OPEN_STATUS,
                )
            )
        return entries

    def add_feedback_entry(self, feedback_type: str, name: str, title: str, details: str) -> FeedbackEntry:
        worksheet = self._feedback_worksheet(feedback_type)
        author = str(name or "").strip()
        entry_title = str(title or "").strip()
        entry_details = str(details or "").strip()

        if not entry_title:
            raise ValueError("Enter a short title.")
        if not entry_details:
            raise ValueError("Enter the details.")

        rows = worksheet.get_all_values()
        if not rows:
            self._ensure_feedback_headers(worksheet, rows)
            rows = [FEEDBACK_HEADERS]
        else:
            self._ensure_feedback_headers(worksheet, rows)

        entry = FeedbackEntry(
            row_number=len(rows) + 1,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            name=author or "Anonymous",
            title=entry_title,
            details=entry_details,
            status=FEEDBACK_OPEN_STATUS,
        )
        worksheet.update(
            range_name=f"A{entry.row_number}:E{entry.row_number}",
            values=[[entry.created_at, entry.name, entry.title, entry.details, entry.status]],
        )
        return entry

    def mark_feedback_entry_done(self, feedback_type: str, row_number: int):
        worksheet = self._feedback_worksheet(feedback_type)
        self._validate_feedback_row_number(row_number)
        worksheet.update(range_name=f"{FEEDBACK_STATUS_COLUMN}{row_number}", values=[[FEEDBACK_DONE_STATUSES[feedback_type]]])

    def delete_feedback_entry(self, feedback_type: str, row_number: int):
        worksheet = self._feedback_worksheet(feedback_type)
        self._validate_feedback_row_number(row_number)
        worksheet.update(range_name=f"A{row_number}:E{row_number}", values=[["", "", "", "", ""]])

    def _ensure_feedback_headers(self, worksheet, rows):
        if not rows or rows[0][: len(FEEDBACK_HEADERS)] != FEEDBACK_HEADERS:
            worksheet.update(range_name=FEEDBACK_HEADER_RANGE, values=[FEEDBACK_HEADERS])

    def _validate_feedback_row_number(self, row_number: int):
        if int(row_number) < 2:
            raise ValueError("Choose a feedback row.")

    def _feedback_worksheet(self, feedback_type: str):
        try:
            sheet_name = FEEDBACK_SHEETS[feedback_type]
        except KeyError as exc:
            raise ValueError(f"Unknown feedback type '{feedback_type}'.") from exc
        return self.get_worksheet(sheet_name)
