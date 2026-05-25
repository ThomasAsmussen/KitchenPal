from __future__ import annotations

from gspread.utils import rowcol_to_a1

from ..constants import (
    DAY_SHEET_SIGNUP_HEADER_RANGE,
    PERSONAL_ACCOUNT_KOVS_HEADER_RANGE,
    PERSONAL_ACCOUNT_KOVS_SEARCH_END_ROW,
    PERSONAL_ACCOUNT_KOVS_SEARCH_START_ROW,
    PERSONAL_ACCOUNT_PREVIOUS_BALANCE_COLUMN,
    PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE,
    PERSONAL_ACCOUNT_TABLE_RANGE,
    PERSONAL_ACCOUNT_TABLE_START_ROW,
)
from .models import PersonalAccountEntry, RoomEntry
from .utils import (
    format_room_label as _format_room_label,
    normalized_person_name as _normalized_person_name,
    parse_amount_value as _parse_amount_value,
    parse_month_sheet_name as _parse_month_sheet_name,
    resolve_month_sheet_name as _resolve_month_sheet_name,
)


class AccountSheetsMixin:
    def get_room_entries(self, worksheet_name: str) -> List[RoomEntry]:
        worksheet = self.get_worksheet(worksheet_name)
        signup_header = worksheet.batch_get([DAY_SHEET_SIGNUP_HEADER_RANGE])[0][0]
        signup_columns = {}
        for column_index, label in enumerate(signup_header, start=9):
            if label is None:
                continue
            label_str = str(label).strip()
            if label_str:
                signup_columns[label_str] = column_index

        account_rows = worksheet.batch_get([PERSONAL_ACCOUNT_TABLE_RANGE])[0]
        room_entries: List[RoomEntry] = []

        for row_offset, row in enumerate(account_rows, start=PERSONAL_ACCOUNT_TABLE_START_ROW):
            padded_row = row + [""] * 2
            if padded_row[0] is None:
                continue
            label = str(padded_row[0]).strip()
            if not label:
                continue

            room_entries.append(
                RoomEntry(
                    label=label,
                    name=str(padded_row[1]).strip() if padded_row[1] is not None else "",
                    account_row=row_offset,
                    signup_column=signup_columns.get(label),
                )
            )

        return room_entries

    def get_signup_room_entries(self, worksheet_name: str) -> List[RoomEntry]:
        return [entry for entry in self.get_room_entries(worksheet_name) if entry.signup_column is not None]

    def get_room_entry_map(self, worksheet_name: str) -> dict[str, RoomEntry]:
        return {entry.label: entry for entry in self.get_room_entries(worksheet_name)}

    def get_personal_account_entries(self, worksheet_name: str) -> List[PersonalAccountEntry]:
        worksheet = self.get_worksheet(worksheet_name)
        account_rows, balance_rows = worksheet.batch_get([PERSONAL_ACCOUNT_TABLE_RANGE, PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE])
        entries: List[PersonalAccountEntry] = []

        for row_number, account_row in enumerate(account_rows, start=PERSONAL_ACCOUNT_TABLE_START_ROW):
            padded_account = account_row + [""] * 2
            label = _format_room_label(padded_account[0])
            if not label:
                continue

            balance_index = row_number - PERSONAL_ACCOUNT_TABLE_START_ROW
            balance_row = balance_rows[balance_index] if balance_index < len(balance_rows) else []
            entries.append(
                PersonalAccountEntry(
                    label=label,
                    name=str(padded_account[1]).strip() if padded_account[1] is not None else "",
                    row_number=row_number,
                    balance=_parse_amount_value(balance_row[0] if balance_row else None),
                )
            )

        return entries

    def _account_entries_by_label(self, worksheet_name: str) -> dict[str, PersonalAccountEntry]:
        return {entry.label: entry for entry in self.get_personal_account_entries(worksheet_name)}

    def _account_entries_by_name(self, worksheet_name: str) -> dict[str, PersonalAccountEntry]:
        entries_by_name = {}
        for entry in self.get_personal_account_entries(worksheet_name):
            key = _normalized_person_name(entry.name)
            if not key:
                continue
            if key in entries_by_name:
                raise ValueError(f"'{entry.name}' appears more than once in {worksheet_name}.")
            entries_by_name[key] = entry
        return entries_by_name

    def _first_available_fl_entry(self, worksheet_name: str) -> PersonalAccountEntry | None:
        for entry in self.get_personal_account_entries(worksheet_name):
            if entry.label.upper().startswith("FL") and not entry.name:
                return entry
        return None

    def previous_month_sheet_name(self, worksheet_name: str) -> str | None:
        parsed = _parse_month_sheet_name(worksheet_name)
        if parsed is None:
            return None

        month_number, year = parsed
        previous_month_number = 12 if month_number == 1 else month_number - 1
        previous_year = year - 1 if month_number == 1 else year
        return _resolve_month_sheet_name(self.list_sheets(), previous_month_number, previous_year)

    def add_person_as_fl(self, worksheet_name: str, person_name: str) -> str:
        person = str(person_name).strip()
        if not person:
            raise ValueError("Enter a person name.")

        existing_people = self._account_entries_by_name(worksheet_name)
        if _normalized_person_name(person) in existing_people:
            raise ValueError(f"{person} already has an account in {worksheet_name}.")

        fl_entry = self._first_available_fl_entry(worksheet_name)
        if fl_entry is None:
            raise ValueError("No available FL spots.")

        worksheet = self.get_worksheet(worksheet_name)
        worksheet.batch_update(
            [
                {"range": f"B{fl_entry.row_number}", "values": [[person]]},
                {"range": rowcol_to_a1(fl_entry.row_number, PERSONAL_ACCOUNT_PREVIOUS_BALANCE_COLUMN), "values": [[0.0]]},
            ]
        )
        return fl_entry.label

    def replace_room_person(self, worksheet_name: str, room_label: str, new_person_name: str) -> str:
        new_person = str(new_person_name).strip()
        if not new_person:
            raise ValueError("Enter a person name.")

        entries_by_label = self._account_entries_by_label(worksheet_name)
        target_entry = entries_by_label.get(str(room_label))
        if target_entry is None or not target_entry.label.isdigit():
            raise ValueError(f"Choose a room-number account to replace, not '{room_label}'.")
        if not target_entry.name:
            raise ValueError(f"Room {target_entry.label} has no person to replace.")

        entries_by_name = self._account_entries_by_name(worksheet_name)
        existing_new_person = entries_by_name.get(_normalized_person_name(new_person))
        if existing_new_person and existing_new_person.label == target_entry.label:
            return target_entry.label
        if existing_new_person and not existing_new_person.label.upper().startswith("FL"):
            raise ValueError(f"{new_person} already has room {existing_new_person.label}.")

        fl_entry = existing_new_person or self._first_available_fl_entry(worksheet_name)
        if fl_entry is None:
            raise ValueError("No available FL spots for the replaced person.")

        replaced_person = target_entry.name
        worksheet = self.get_worksheet(worksheet_name)
        target_previous_balance = _parse_amount_value(
            worksheet.cell(target_entry.row_number, PERSONAL_ACCOUNT_PREVIOUS_BALANCE_COLUMN).value
        )
        fl_previous_balance = (
            _parse_amount_value(worksheet.cell(fl_entry.row_number, PERSONAL_ACCOUNT_PREVIOUS_BALANCE_COLUMN).value)
            if existing_new_person
            else 0.0
        )
        worksheet.batch_update(
            [
                {"range": f"B{target_entry.row_number}", "values": [[new_person]]},
                {
                    "range": rowcol_to_a1(target_entry.row_number, PERSONAL_ACCOUNT_PREVIOUS_BALANCE_COLUMN),
                    "values": [[fl_previous_balance]],
                },
                {"range": f"B{fl_entry.row_number}", "values": [[replaced_person]]},
                {
                    "range": rowcol_to_a1(fl_entry.row_number, PERSONAL_ACCOUNT_PREVIOUS_BALANCE_COLUMN),
                    "values": [[target_previous_balance]],
                },
            ]
        )
        return fl_entry.label

    def delete_fl_person(self, worksheet_name: str, person_name: str, balance_source_worksheet_name: str | None = None):
        person = str(person_name).strip()
        if not person:
            raise ValueError("Choose a person to delete.")

        entry = self._account_entries_by_name(worksheet_name).get(_normalized_person_name(person))
        if entry is None:
            raise ValueError(f"{person} was not found in {worksheet_name}.")
        if not entry.label.upper().startswith("FL"):
            raise ValueError(f"{person} can only be deleted from an FL account.")

        balance_entry = entry
        if balance_source_worksheet_name:
            balance_entry = self._account_entries_by_name(balance_source_worksheet_name).get(_normalized_person_name(person), entry)
        if balance_entry.balance != 0:
            raise ValueError(f"{person} cannot be deleted because their balance is {balance_entry.balance:.2f} DKK.")

        worksheet = self.get_worksheet(worksheet_name)
        worksheet.batch_update(
            [
                {"range": f"B{entry.row_number}", "values": [[""]]},
                {"range": rowcol_to_a1(entry.row_number, PERSONAL_ACCOUNT_PREVIOUS_BALANCE_COLUMN), "values": [[0.0]]},
            ]
        )

    def _find_account_row_in_kovs(self, worksheet, room_label: str) -> int | None:
        """Find the KØVS section, then search the `Værelse` rows below it.

        The sheet layout is expected to be:
        - row 1: `KØVS`
        - row 2: `Værelse`
        - row 3 and below: the first room row and following room rows
        """
        try:
            header_row = worksheet.batch_get([PERSONAL_ACCOUNT_KOVS_HEADER_RANGE])[0][0]
        except Exception:
            return None

        # Find the KØVS column in row 1.
        kovs_col_index = None
        for idx, cell in enumerate(header_row, start=1):
            if cell and isinstance(cell, str) and "KØVS" in cell.upper():
                kovs_col_index = idx
                break

        if kovs_col_index is None:
            return None

        # Search downward starting from the first room row below the headers.
        start_search_row = PERSONAL_ACCOUNT_KOVS_SEARCH_START_ROW
        end_search_row = PERSONAL_ACCOUNT_KOVS_SEARCH_END_ROW
        start_a1 = rowcol_to_a1(start_search_row, kovs_col_index)
        end_a1 = rowcol_to_a1(end_search_row, kovs_col_index)
        try:
            values = worksheet.batch_get([f"{start_a1}:{end_a1}"])[0]
        except Exception:
            return None

        for offset, row_vals in enumerate(values, start=0):
            if not row_vals:
                continue
            cell = row_vals[0]
            if cell is None:
                continue
            # direct string match
            if str(cell).strip() == room_label:
                return start_search_row + offset
            # numeric match (cells may be floats like 346.0)
            try:
                if int(float(cell)) == int(room_label):
                    return start_search_row + offset
            except (TypeError, ValueError):
                pass

        return None
