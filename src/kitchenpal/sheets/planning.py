from __future__ import annotations

import gspread

from ..constants import (
    DAY_SHEET_DAY_OFFSET,
    PLANNING_HEADER_RANGE,
    PLANNING_HEADERS,
    PLANNING_SHEET_NAME,
    POSSIBLE_DAYS_HEADER_RANGE,
    POSSIBLE_DAYS_HEADERS,
    POSSIBLE_DAYS_SHEET_NAME,
)
from .models import PlanningEntry


def _planning_row_identity(year, month_name: str, room_number, person: str) -> tuple:
    """The stable identity of a planning row.

    A row belongs to a ROOM, not to whatever the month sheet happened to call
    its occupant when the row was written. The name in column C is display
    only: it is refreshed on every save. Keying on the name instead flipped a
    person's identity whenever B45:B65 changed (a fresh sheet blanks it, a
    copy-balances run fills it back in), which orphaned their preferences and
    appended a duplicate row on the next save.
    """
    room = str(room_number or "").strip()
    if room:
        return (str(year), month_name, "room", room)
    return (str(year), month_name, "name", " ".join(str(person or "").strip().lower().split()))


class PlanningSheetsMixin:
    def get_or_create_planning_worksheet(self, ensure_header: bool = True):
        """ensure_header=False skips a whole read: the caller is about to read anyway."""
        try:
            worksheet = self.get_worksheet(PLANNING_SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = self._spreadsheet.add_worksheet(title=PLANNING_SHEET_NAME, rows=200, cols=len(PLANNING_HEADERS))
            self.forget_worksheets()
            worksheet.update(range_name=PLANNING_HEADER_RANGE, values=[PLANNING_HEADERS])
            return worksheet

        if ensure_header and not worksheet.get_all_values():
            worksheet.update(range_name=PLANNING_HEADER_RANGE, values=[PLANNING_HEADERS])
        return worksheet

    def save_planning_entries(self, month_name: str, year: int, entries: List[PlanningEntry]):
        worksheet = self.get_or_create_planning_worksheet()
        existing_values = worksheet.get_all_values()
        replacement_rows = {
            _planning_row_identity(year, month_name, entry.room_number, entry.person): [
                year,
                month_name,
                entry.person,
                entry.room_number,
                entry.available_dates,
                entry.unavailable_dates,
                entry.preferred_dates,
                "TRUE" if entry.limit_one_day else "FALSE",
            ]
            for entry in entries
        }

        final_rows = []
        replaced_keys = set()

        for row in existing_values[1:]:
            padded_row = row + [""] * (len(PLANNING_HEADERS) - len(row))
            row_key = _planning_row_identity(padded_row[0], padded_row[1], padded_row[3], padded_row[2])
            if row_key in replacement_rows:
                # The first row for this room is replaced in place; any further
                # rows for the same room are duplicates left behind by the old
                # name-keyed matching, so this save collapses them.
                if row_key not in replaced_keys:
                    final_rows.append(replacement_rows[row_key])
                    replaced_keys.add(row_key)
                continue
            final_rows.append(padded_row[: len(PLANNING_HEADERS)])

        for row_key, row in replacement_rows.items():
            if row_key not in replaced_keys:
                final_rows.append(row)

        worksheet.clear()
        worksheet.update(range_name=PLANNING_HEADER_RANGE, values=[PLANNING_HEADERS])
        if final_rows:
            row_count = len(final_rows) + 1
            worksheet.update(range_name=f"A2:H{row_count}", values=final_rows)

    def get_planning_entries(self, month_name: str, year: int) -> List[PlanningEntry]:
        worksheet = self.get_or_create_planning_worksheet(ensure_header=False)
        values = worksheet.get_all_values()[1:]
        entries = []

        for row in values:
            padded_row = row + [""] * (len(PLANNING_HEADERS) - len(row))
            row_year, row_month, person, room_number, available, unavailable, preferred, limit_one_day = padded_row[
                : len(PLANNING_HEADERS)
            ]
            if row_year != str(year) or row_month != month_name or not person:
                continue

            entries.append(
                PlanningEntry(
                    person=person,
                    room_number=room_number,
                    available_dates=available,
                    unavailable_dates=unavailable,
                    preferred_dates=preferred,
                    limit_one_day=limit_one_day.upper() == "TRUE",
                )
            )

        return entries

    def get_or_create_possible_days_worksheet(self, ensure_header: bool = True):
        try:
            worksheet = self.get_worksheet(POSSIBLE_DAYS_SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = self._spreadsheet.add_worksheet(title=POSSIBLE_DAYS_SHEET_NAME, rows=100, cols=len(POSSIBLE_DAYS_HEADERS))
            self.forget_worksheets()
            worksheet.update(range_name=POSSIBLE_DAYS_HEADER_RANGE, values=[POSSIBLE_DAYS_HEADERS])
            return worksheet

        if ensure_header and not worksheet.get_all_values():
            worksheet.update(range_name=POSSIBLE_DAYS_HEADER_RANGE, values=[POSSIBLE_DAYS_HEADERS])
        return worksheet

    def get_possible_days_limit(self, month_name: str, year: int) -> str:
        worksheet = self.get_or_create_possible_days_worksheet(ensure_header=False)
        values = worksheet.get_all_values()[1:]

        for row in values:
            padded_row = row + [""] * len(POSSIBLE_DAYS_HEADERS)
            row_year, row_month, limit_days = padded_row[: len(POSSIBLE_DAYS_HEADERS)]
            if row_year == str(year) and row_month == month_name:
                return limit_days
        return ""

    def save_possible_days_limit(self, month_name: str, year: int, limit_days: str):
        worksheet = self.get_or_create_possible_days_worksheet()
        existing_values = worksheet.get_all_values()
        replacement_row = [year, month_name, str(limit_days or "").strip()]
        final_rows = []
        replaced = False

        for row in existing_values[1:]:
            padded_row = row + [""] * len(POSSIBLE_DAYS_HEADERS)
            row_year, row_month = padded_row[0], padded_row[1]
            if row_year == str(year) and row_month == month_name:
                if not replaced:
                    final_rows.append(replacement_row)
                    replaced = True
                continue
            final_rows.append(padded_row[: len(POSSIBLE_DAYS_HEADERS)])

        if not replaced:
            final_rows.append(replacement_row)

        worksheet.clear()
        worksheet.update(range_name=POSSIBLE_DAYS_HEADER_RANGE, values=[POSSIBLE_DAYS_HEADERS])
        if final_rows:
            row_count = len(final_rows) + 1
            worksheet.update(range_name=f"A2:C{row_count}", values=final_rows)

    def populate_cooks_for_month(self, worksheet_name: str, assignments: dict[int, str], person_to_room: dict[str, str]):
        worksheet = self.get_worksheet(worksheet_name)
        updates = []

        for day, person in sorted(assignments.items()):
            room_number = person_to_room[person]
            row = day + DAY_SHEET_DAY_OFFSET
            updates.append({"range": f"C{row}", "values": [[room_number]]})

        if updates:
            worksheet.batch_update(updates)
