from __future__ import annotations

from datetime import date

import gspread

from ..constants import KITCHEN_MEETINGS_SHEET_NAME
from .models import KitchenMeetingSubject


MEETING_FIRST_ROW = 10
MEETING_LAST_ROW = 20


class KitchenMeetingSheetsMixin:
    def _kitchen_meeting_worksheet(self):
        try:
            return self.get_worksheet(KITCHEN_MEETINGS_SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound as exc:
            matching_name = next(
                (name for name in self.list_sheets() if name.casefold() == KITCHEN_MEETINGS_SHEET_NAME.casefold()),
                None,
            )
            if matching_name is None:
                raise exc
            return self.get_worksheet(matching_name)

    def get_kitchen_meeting_subjects(self, today: date | None = None) -> list[KitchenMeetingSubject]:
        worksheet = self._kitchen_meeting_worksheet()
        rows = worksheet.get_all_values()
        subjects = []
        for row_number in range(MEETING_FIRST_ROW, MEETING_LAST_ROW + 1):
            row = rows[row_number - 1] if row_number <= len(rows) else []
            subject = str(row[1]).strip() if len(row) > 1 else ""
            if subject:
                author = str(row[3]).strip() if len(row) > 3 else ""
                subjects.append(KitchenMeetingSubject(row_number, subject, author))
        return subjects

    def add_kitchen_meeting_subject(self, subject: str, submitted_by: str) -> KitchenMeetingSubject:
        worksheet = self._kitchen_meeting_worksheet()
        subject = str(subject or "").strip()
        submitted_by = str(submitted_by or "").strip()
        if not subject:
            raise ValueError("Enter a subject.")
        if not submitted_by:
            raise ValueError("Choose who submitted the subject.")

        rows = worksheet.get_all_values()
        for row_number in range(MEETING_FIRST_ROW, MEETING_LAST_ROW + 1):
            row = rows[row_number - 1] if row_number <= len(rows) else []
            if len(row) <= 1 or not str(row[1]).strip():
                worksheet.update(range_name=f"B{row_number}", values=[[subject]])
                worksheet.update(range_name=f"D{row_number}", values=[[submitted_by]])
                return KitchenMeetingSubject(row_number, subject, submitted_by)
        raise ValueError("There is no free subject row for this meeting.")

    def clear_kitchen_meeting_subjects(self) -> None:
        worksheet = self._kitchen_meeting_worksheet()
        blank_rows = [[""] for _ in range(MEETING_LAST_ROW - MEETING_FIRST_ROW + 1)]
        worksheet.update(range_name=f"B{MEETING_FIRST_ROW}:B{MEETING_LAST_ROW}", values=blank_rows)
        worksheet.update(range_name=f"D{MEETING_FIRST_ROW}:D{MEETING_LAST_ROW}", values=blank_rows)
