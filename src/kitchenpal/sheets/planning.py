from __future__ import annotations

import gspread

from ..constants import DAY_SHEET_DAY_OFFSET, PLANNING_HEADER_RANGE, PLANNING_HEADERS, PLANNING_SHEET_NAME
from .models import PlanningEntry


class PlanningSheetsMixin:
    def get_or_create_planning_worksheet(self):
        try:
            worksheet = self.get_worksheet(PLANNING_SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = self._spreadsheet.add_worksheet(title=PLANNING_SHEET_NAME, rows=200, cols=len(PLANNING_HEADERS))
            worksheet.update(range_name=PLANNING_HEADER_RANGE, values=[PLANNING_HEADERS])
            return worksheet

        values = worksheet.get_all_values()
        if not values:
            worksheet.update(range_name=PLANNING_HEADER_RANGE, values=[PLANNING_HEADERS])
        return worksheet

    def save_planning_entries(self, month_name: str, year: int, entries: List[PlanningEntry]):
        worksheet = self.get_or_create_planning_worksheet()
        existing_values = worksheet.get_all_values()
        replacement_rows = {
            (str(year), month_name, entry.person): [
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
            row_key = (str(padded_row[0]), padded_row[1], padded_row[2])
            if row_key in replacement_rows:
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
        worksheet = self.get_or_create_planning_worksheet()
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

    def populate_cooks_for_month(self, worksheet_name: str, assignments: dict[int, str], person_to_room: dict[str, str]):
        worksheet = self.get_worksheet(worksheet_name)
        updates = []

        for day, person in sorted(assignments.items()):
            room_number = person_to_room[person]
            row = day + DAY_SHEET_DAY_OFFSET
            updates.append({"range": f"C{row}", "values": [[room_number]]})

        if updates:
            worksheet.batch_update(updates)
