from __future__ import annotations

from datetime import date

from gspread.utils import rowcol_to_a1

from ..a1 import range_end_row as _range_end_row, range_start_row as _range_start_row
from ..constants import (
    DAY_SHEET_DAY_OFFSET,
    DAY_SHEET_MENU_COLUMN,
    DAY_SHEET_SIGNUP_HEADER_RANGE,
    DRINK_TABLE_RANGE,
    PERSONAL_ACCOUNT_BEER_COLUMN,
    PERSONAL_ACCOUNT_PREVIOUS_BALANCE_COLUMN,
    PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE,
    PERSONAL_ACCOUNT_TABLE_RANGE,
    PERSONAL_ACCOUNT_TABLE_START_ROW,
    PERSONAL_ACCOUNT_WINE_COLUMN,
    PURCHASE_AMOUNT_COLUMN,
    PURCHASE_INSERT_END_COLUMN,
    PURCHASE_INSERT_START_COLUMN,
    PURCHASE_LOOKUP_RANGE,
    PURCHASE_TABLE_RANGE,
    TRANSACTION_AMOUNT_COLUMN,
    TRANSACTION_INSERT_END_COLUMN,
    TRANSACTION_INSERT_START_COLUMN,
    TRANSACTION_LOOKUP_RANGE,
    TRANSACTION_TABLE_RANGE,
)
from .models import DayToDayEntries, DrinkEntry, PersonalAccountEntry, PurchaseEntry, RoomEntry, TransactionEntry
from .utils import (
    format_date_value as _format_date_value,
    format_room_label as _format_room_label,
    is_data_room_label as _is_data_room_label,
    is_payout_type as _is_payout_type,
    normalized_person_name as _normalized_person_name,
    parse_amount_value as _parse_amount_value,
    parse_month_sheet_name as _parse_month_sheet_name,
    row_has_content as _row_has_content,
)


class DayToDaySheetsMixin:
    def get_day_summary(self, worksheet_name: str, day: int) -> tuple[str, str, str]:
        worksheet = self.get_worksheet(worksheet_name)
        row = day + DAY_SHEET_DAY_OFFSET
        values = worksheet.batch_get([f"C{row}:G{row}"])[0]
        row_values = values[0] if values else []
        padded_row = row_values + [""] * 5
        chef = padded_row[0] or ""
        menu = padded_row[1] or ""
        signed_up = padded_row[4] or "0"
        return chef, menu, signed_up

    def get_signed_up_people(self, worksheet_name: str, day: int, room_entries: List[RoomEntry]) -> List[str]:
        worksheet = self.get_worksheet(worksheet_name)
        row = day + DAY_SHEET_DAY_OFFSET
        sign_up_entries = [entry for entry in room_entries if entry.signup_column is not None]
        ranges = [rowcol_to_a1(row, entry.signup_column) for entry in sign_up_entries]
        if not ranges:
            return []

        values = worksheet.batch_get(ranges)
        signed_people: List[str] = []
        for entry, value_rows in zip(sign_up_entries, values):
            cell_value = value_rows[0][0] if value_rows and value_rows[0] else ""
            try:
                count = int(cell_value) if cell_value else 0
            except (TypeError, ValueError):
                count = 0
            if count > 0:
                display_name = entry.name or entry.label
                if count > 1:
                    display_name = f"{display_name} ({count})"
                signed_people.append(display_name)

        return signed_people

    def update_dish_signup(self, worksheet_name: str, day: int, room_label: int | str, people_count: int):
        worksheet = self.get_worksheet(worksheet_name)
        row = day + DAY_SHEET_DAY_OFFSET
        room_entry = self.get_room_entry_map(worksheet_name).get(str(room_label))
        if room_entry is None or room_entry.signup_column is None:
            raise ValueError(f"No signup column found for room '{room_label}'")

        col = room_entry.signup_column
        worksheet.update_cell(row, col, people_count)

    def update_dish_name(self, worksheet_name: str, day: int, dish_name: str):
        worksheet = self.get_worksheet(worksheet_name)
        worksheet.update_cell(day + DAY_SHEET_DAY_OFFSET, DAY_SHEET_MENU_COLUMN, dish_name)

    def add_purchase(self, worksheet_name: str, room_number: int | str, purchase_date: date, item: str, cost: float):
        worksheet = self.get_worksheet(worksheet_name)
        rows = worksheet.batch_get([PURCHASE_LOOKUP_RANGE])[0]
        target_row = None
        for index, cell in enumerate(rows, start=2):
            if not cell:
                target_row = index
                break

        if target_row is None:
            # If the lookup range is full, pick the first row after the lookup.
            # Try to expand the worksheet if supported; otherwise raise.
            start_row = _range_start_row(PURCHASE_LOOKUP_RANGE, 2)
            desired_row = start_row + len(rows)
            if hasattr(worksheet, "row_count") and hasattr(worksheet, "add_rows"):
                if desired_row > worksheet.row_count:
                    worksheet.add_rows(desired_row - worksheet.row_count)
                target_row = desired_row
            else:
                raise ValueError(f"No available purchase rows in {PURCHASE_LOOKUP_RANGE}")

        updates = [
            {
                "range": f"{PURCHASE_INSERT_START_COLUMN}{target_row}:{PURCHASE_INSERT_END_COLUMN}{target_row}",
                "values": [[room_number, purchase_date.strftime("%Y-%m-%d"), item]],
            },
            {
                "range": f"{PURCHASE_AMOUNT_COLUMN}{target_row}",
                "values": [[cost]],
            },
        ]
        worksheet.batch_update(updates)

    def add_drinks(self, worksheet_name: str, room_number: int | str, beer_quantity: int, wine_quantity: int):
        worksheet = self.get_worksheet(worksheet_name)
        row = self._find_account_row_in_kovs(worksheet, str(room_number))
        if row is None:
            raise ValueError(f"No account row found for room '{room_number}'")
        beer_col = PERSONAL_ACCOUNT_BEER_COLUMN
        wine_col = PERSONAL_ACCOUNT_WINE_COLUMN

        current_beer = worksheet.cell(row, beer_col).value
        current_wine = worksheet.cell(row, wine_col).value
        current_beer = int(current_beer) if current_beer else 0
        current_wine = int(current_wine) if current_wine else 0

        new_beer = current_beer + beer_quantity
        new_wine = current_wine + wine_quantity

        worksheet.update_cell(row, beer_col, new_beer)
        worksheet.update_cell(row, wine_col, new_wine)
        return new_beer, new_wine

    def _parse_drink_entries(self, rows, room_name_by_label: dict[str, str]) -> List[DrinkEntry]:
        entries: List[DrinkEntry] = []

        for row_number, row in enumerate(rows, start=3):
            if not row:
                continue
            room_value = row[0] if len(row) > 0 else None
            if not _is_data_room_label(room_value):
                continue
            room = _format_room_label(room_value)
            room_name = room_name_by_label.get(room, "")
            beer_soda = row[1] if len(row) > 1 and row[1] is not None else 0
            wine = row[2] if len(row) > 2 and row[2] is not None else 0
            entries.append(
                DrinkEntry(
                    row_number=row_number,
                    room=room,
                    name=room_name,
                    beer_soda=int(beer_soda) if beer_soda != "" else 0,
                    wine=int(wine) if wine != "" else 0,
                )
            )

        return entries

    def get_drink_entries(self, worksheet_name: str) -> List[DrinkEntry]:
        worksheet = self.get_worksheet(worksheet_name)
        room_entries = self.get_room_entry_map(worksheet_name)
        rows = worksheet.batch_get([DRINK_TABLE_RANGE])[0]
        room_name_by_label = {entry.label: entry.name for entry in room_entries.values()}
        return self._parse_drink_entries(rows, room_name_by_label)

    def update_drinks(self, worksheet_name: str, row_number: int, beer_soda: int, wine: int):
        if row_number < 3:
            raise ValueError("Drink row must be in the drink section")

        worksheet = self.get_worksheet(worksheet_name)
        updates = [
            {"range": rowcol_to_a1(row_number, PERSONAL_ACCOUNT_BEER_COLUMN), "values": [[beer_soda]]},
            {"range": rowcol_to_a1(row_number, PERSONAL_ACCOUNT_WINE_COLUMN), "values": [[wine]]},
        ]
        worksheet.batch_update(updates)

    def _parse_purchase_entries(self, rows) -> List[PurchaseEntry]:
        entries: List[PurchaseEntry] = []

        for row_number, row in enumerate(rows, start=3):
            if not _row_has_content(row):
                continue
            room_value = row[0] if len(row) > 0 else None
            if not _is_data_room_label(room_value):
                continue
            entries.append(
                PurchaseEntry(
                    row_number=row_number,
                    room=_format_room_label(room_value),
                    date=_format_date_value(row[1] if len(row) > 1 else None),
                    item=str(row[2]).strip() if len(row) > 2 and row[2] is not None else "",
                    amount=_parse_amount_value(row[4] if len(row) > 4 else None),
                )
            )

        return entries

    def get_purchase_entries(self, worksheet_name: str) -> List[PurchaseEntry]:
        worksheet = self.get_worksheet(worksheet_name)
        rows = worksheet.batch_get([PURCHASE_TABLE_RANGE])[0]
        return self._parse_purchase_entries(rows)

    def update_purchase(
        self,
        worksheet_name: str,
        row_number: int,
        room_number: int | str,
        purchase_date: date,
        item: str,
        cost: float,
    ):
        if row_number < _range_start_row(PURCHASE_TABLE_RANGE, 3) or row_number > _range_end_row(
            PURCHASE_TABLE_RANGE, 43
        ):
            raise ValueError("Purchase row must be in the purchase section")

        worksheet = self.get_worksheet(worksheet_name)
        updates = [
            {
                "range": f"{PURCHASE_INSERT_START_COLUMN}{row_number}:{PURCHASE_INSERT_END_COLUMN}{row_number}",
                "values": [[room_number, purchase_date.strftime("%Y-%m-%d"), item]],
            },
            {
                "range": f"{PURCHASE_AMOUNT_COLUMN}{row_number}",
                "values": [[cost]],
            },
        ]
        worksheet.batch_update(updates)

    def delete_purchase(self, worksheet_name: str, row_number: int):
        if row_number < _range_start_row(PURCHASE_TABLE_RANGE, 3) or row_number > _range_end_row(
            PURCHASE_TABLE_RANGE, 43
        ):
            raise ValueError("Purchase row must be in the purchase section")

        worksheet = self.get_worksheet(worksheet_name)
        worksheet.batch_update(
            [
                {
                    "range": f"{PURCHASE_INSERT_START_COLUMN}{row_number}:{PURCHASE_INSERT_END_COLUMN}{row_number}",
                    "values": [["", "", ""]],
                },
                {
                    "range": f"{PURCHASE_AMOUNT_COLUMN}{row_number}",
                    "values": [[""]],
                },
            ]
        )

    def _parse_transaction_entries(self, rows) -> List[TransactionEntry]:
        entries: List[TransactionEntry] = []

        for row_number, row in enumerate(rows, start=44):
            if not _row_has_content(row):
                continue
            entries.append(
                TransactionEntry(
                    row_number=row_number,
                    room=_format_room_label(row[0] if len(row) > 0 else None),
                    date=_format_date_value(row[1] if len(row) > 1 else None),
                    transaction_type=str(row[2]).strip() if len(row) > 2 and row[2] is not None else "",
                    amount=_parse_amount_value(row[4] if len(row) > 4 else None),
                )
            )

        return entries

    def get_transaction_entries(self, worksheet_name: str) -> List[TransactionEntry]:
        worksheet = self.get_worksheet(worksheet_name)
        rows = worksheet.batch_get([TRANSACTION_TABLE_RANGE])[0]
        return self._parse_transaction_entries(rows)

    def get_day_to_day_entries(self, worksheet_name: str, room_entries: List[RoomEntry]) -> DayToDayEntries:
        worksheet = self.get_worksheet(worksheet_name)
        drink_rows, purchase_rows, transaction_rows = worksheet.batch_get(
            [DRINK_TABLE_RANGE, PURCHASE_TABLE_RANGE, TRANSACTION_TABLE_RANGE]
        )
        room_name_by_label = {entry.label: entry.name for entry in room_entries}
        return DayToDayEntries(
            drinks=self._parse_drink_entries(drink_rows, room_name_by_label),
            purchases=self._parse_purchase_entries(purchase_rows),
            transactions=self._parse_transaction_entries(transaction_rows),
        )

    def update_transaction(
        self,
        worksheet_name: str,
        row_number: int,
        room_number: int | str,
        transaction_type: str,
        amount: float,
        transaction_date: date,
    ):
        if row_number < _range_start_row(TRANSACTION_TABLE_RANGE, 44):
            raise ValueError("Transaction row must be in the transaction section")

        worksheet = self.get_worksheet(worksheet_name)
        normalized_amount = -abs(amount) if _is_payout_type(transaction_type) and amount >= 0 else amount
        updates = [
            {
                "range": f"{TRANSACTION_INSERT_START_COLUMN}{row_number}:{TRANSACTION_INSERT_END_COLUMN}{row_number}",
                "values": [[room_number, transaction_date.strftime("%d/%m"), transaction_type]],
            },
            {
                "range": f"{TRANSACTION_AMOUNT_COLUMN}{row_number}",
                "values": [[normalized_amount]],
            },
        ]
        worksheet.batch_update(updates)

    def delete_transaction(self, worksheet_name: str, row_number: int):
        if row_number < _range_start_row(TRANSACTION_TABLE_RANGE, 44):
            raise ValueError("Transaction row must be in the transaction section")

        worksheet = self.get_worksheet(worksheet_name)
        worksheet.batch_update(
            [
                {
                    "range": f"{TRANSACTION_INSERT_START_COLUMN}{row_number}:{TRANSACTION_INSERT_END_COLUMN}{row_number}",
                    "values": [["", "", ""]],
                },
                {
                    "range": f"{TRANSACTION_AMOUNT_COLUMN}{row_number}",
                    "values": [[""]],
                },
            ]
        )

    def add_transaction(self, worksheet_name: str, room_number: int | str, transaction_type: str, amount: float, transaction_date: date):
        worksheet = self.get_worksheet(worksheet_name)
        range_values = worksheet.batch_get([TRANSACTION_LOOKUP_RANGE])[0]

        start_row = _range_start_row(TRANSACTION_LOOKUP_RANGE, 44)

        target_row = None
        for index, current_cell in enumerate(range_values):
            if not current_cell:
                target_row = start_row + index
                break

        if target_row is None:
            # If lookup is full, append after the lookup. Try to expand the
            # worksheet if supported; otherwise preserve previous behavior and raise.
            desired_row = start_row + len(range_values)
            if hasattr(worksheet, "row_count") and hasattr(worksheet, "add_rows"):
                if desired_row > worksheet.row_count:
                    worksheet.add_rows(desired_row - worksheet.row_count)
                target_row = desired_row
            else:
                raise ValueError(f"No available transaction rows in {TRANSACTION_LOOKUP_RANGE}")

        updates = [
            {
                "range": f"{TRANSACTION_INSERT_START_COLUMN}{target_row}:{TRANSACTION_INSERT_END_COLUMN}{target_row}",
                "values": [[room_number, transaction_date.strftime("%d/%m"), transaction_type]],
            },
            {
                "range": f"{TRANSACTION_AMOUNT_COLUMN}{target_row}",
                "values": [[(-abs(amount) if _is_payout_type(transaction_type) and amount >= 0 else amount)]],
            },
        ]
        worksheet.batch_update(updates)
