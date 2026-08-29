from __future__ import annotations

from datetime import date

from gspread.utils import rowcol_to_a1

from ..a1 import range_end_row as _range_end_row, range_start_row as _range_start_row
from ..constants import (
    ANDET_FIRST_ROW,
    ANDET_LAST_ROW,
    ANDET_ROW_CAPACITY,
    DAY_SHEET_CHEF_COLUMN,
    DAY_SHEET_DAY_OFFSET,
    DAY_SHEET_LAST_DAY_ROW,
    DAY_SHEET_MEAL_PRICE_COLUMN,
    DAY_SHEET_MENU_COLUMN,
    DAY_SHEET_SIGNUP_COUNT_COLUMN,
    DAY_SHEET_MENU_DESCRIPTION_COLUMN,
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
    PURCHASE_ROW_CAPACITY,
    PURCHASE_TABLE_RANGE,
    TRANSACTION_AMOUNT_COLUMN,
    TRANSACTION_INSERT_END_COLUMN,
    TRANSACTION_INSERT_START_COLUMN,
    TRANSACTION_LOOKUP_RANGE,
    TRANSACTION_ROW_CAPACITY,
    TRANSACTION_TABLE_RANGE,
)
from .log import LogEntry
from .models import (
    AndetRow,
    DayRow,
    DaySummary,
    DayToDayEntries,
    DrinkEntry,
    PersonalAccountEntry,
    PurchaseEntry,
    RoomEntry,
    TransactionEntry,
)
from .utils import (
    format_date_value as _format_date_value,
    format_room_label as _format_room_label,
    is_data_room_label as _is_data_room_label,
    is_payout_type as _is_payout_type,
    normalized_person_name as _normalized_person_name,
    ordinal,
    parse_amount_value as _parse_amount_value,
    parse_month_sheet_name as _parse_month_sheet_name,
    row_has_content as _row_has_content,
)


def _parse_signup_count(value) -> int:
    try:
        return int(str(value).strip() or 0)
    except (TypeError, ValueError):
        return 0


def _parse_optional_meal_price(value) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        amount = float(value)
        if amount < 0:
            raise ValueError("Meal price cannot be negative.")
        return amount

    text = str(value).strip().lower()
    if not text:
        return 0.0

    text = text.replace("kr", "").replace("dkk", "").replace(" ", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")

    try:
        amount = float(text)
    except ValueError as exc:
        raise ValueError("Enter a valid meal price.") from exc

    if amount < 0:
        raise ValueError("Meal price cannot be negative.")
    return amount


def _read_optional_meal_price(value) -> float:
    return max(0.0, _parse_amount_value(value))


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

    def get_day_details(self, worksheet_name: str, day: int) -> DaySummary:
        worksheet = self.get_worksheet(worksheet_name)
        row = day + DAY_SHEET_DAY_OFFSET
        summary_values, description_values = worksheet.batch_get([f"C{row}:G{row}", f"AV{row}"])

        row_values = summary_values[0] if summary_values else []
        padded_row = row_values + [""] * 5
        description = description_values[0][0] if description_values and description_values[0] else ""

        return DaySummary(
            chef=padded_row[0] or "",
            menu=padded_row[1] or "",
            signed_up=padded_row[4] or "0",
            meal_price=_read_optional_meal_price(padded_row[3]),
            menu_description=str(description or "").strip(),
        )

    def get_day_rows(self, worksheet_name: str, room_entries: List[RoomEntry]) -> List[DayRow]:
        """Every dinner day of the month in one read.

        The Dinner screen needs tonight, the next few days and the days you are
        cooking; asking day by day would be thirty round trips.
        """
        worksheet = self.get_worksheet(worksheet_name)
        first_row = 1 + DAY_SHEET_DAY_OFFSET
        description_column = rowcol_to_a1(1, DAY_SHEET_MENU_DESCRIPTION_COLUMN)[:-1]
        values, descriptions = worksheet.batch_get(
            [
                f"A{first_row}:AB{DAY_SHEET_LAST_DAY_ROW}",
                f"{description_column}{first_row}:{description_column}{DAY_SHEET_LAST_DAY_ROW}",
            ]
        )
        signup_columns = {
            entry.label: entry.signup_column for entry in room_entries if entry.signup_column is not None
        }

        rows: List[DayRow] = []
        for index, row in enumerate(values):
            padded = list(row) + [""] * 28
            if not str(padded[0] or "").strip():
                # past the end of the month
                continue
            description_row = descriptions[index] if index < len(descriptions) else []
            rows.append(
                DayRow(
                    day=index + 1,
                    chef=_format_room_label(padded[DAY_SHEET_CHEF_COLUMN - 1]),
                    menu=str(padded[DAY_SHEET_MENU_COLUMN - 1] or "").strip(),
                    menu_description=str((description_row[0] if description_row else "") or "").strip(),
                    signed_up=_parse_signup_count(padded[DAY_SHEET_SIGNUP_COUNT_COLUMN - 1]),
                    meal_price=_read_optional_meal_price(padded[DAY_SHEET_MEAL_PRICE_COLUMN - 1]),
                    signups={
                        label: _parse_signup_count(padded[column - 1]) for label, column in signup_columns.items()
                    },
                )
            )
        return rows

    def get_andet_rows(self, worksheet_name: str, room_entries: List[RoomEntry]) -> List[AndetRow]:
        """The month's undated shared costs, in one read."""
        worksheet = self.get_worksheet(worksheet_name)
        values = worksheet.batch_get([f"A{ANDET_FIRST_ROW}:AB{ANDET_LAST_ROW}"])[0]
        signup_columns = {
            entry.label: entry.signup_column for entry in room_entries if entry.signup_column is not None
        }

        rows: List[AndetRow] = []
        for index in range(ANDET_ROW_CAPACITY):
            row = list(values[index]) if index < len(values) else []
            padded = row + [""] * 28
            description = str(padded[DAY_SHEET_MENU_COLUMN - 1] or "").strip()
            payer = _format_room_label(padded[DAY_SHEET_CHEF_COLUMN - 1])
            amount = _read_optional_meal_price(padded[DAY_SHEET_MEAL_PRICE_COLUMN - 1])
            participants = {
                label: _parse_signup_count(padded[column - 1])
                for label, column in signup_columns.items()
                if _parse_signup_count(padded[column - 1])
            }
            if not description and not payer and not amount and not participants:
                continue
            rows.append(
                AndetRow(
                    row_number=ANDET_FIRST_ROW + index,
                    payer=payer,
                    description=description,
                    amount=amount,
                    participants=participants,
                )
            )
        return rows

    def save_andet(
        self,
        worksheet_name: str,
        payer: int | str,
        description: str,
        amount: float,
        participants: List[str],
        room_entries: List[RoomEntry],
        row_number: int | None = None,
    ) -> int:
        """Write a shared cost, then let the sheet do the splitting.

        Marking who was in on it is the whole point: the sheet charges every
        marked account one share and credits the payer the full amount.
        """
        if not str(description).strip():
            raise ValueError("Say what the shared cost was.")
        if not participants:
            raise ValueError("Pick at least one person to share the cost.")

        signup_columns = {
            entry.label: entry.signup_column for entry in room_entries if entry.signup_column is not None
        }
        unknown = [label for label in participants if label not in signup_columns]
        if unknown:
            raise ValueError(f"These accounts cannot take a share: {', '.join(unknown)}.")

        if row_number is None:
            taken = {row.row_number for row in self.get_andet_rows(worksheet_name, room_entries)}
            free = [row for row in range(ANDET_FIRST_ROW, ANDET_LAST_ROW + 1) if row not in taken]
            if not free:
                raise ValueError(
                    f"All {ANDET_ROW_CAPACITY} shared cost rows for {worksheet_name} are in use. "
                    "Delete one before adding another."
                )
            row_number = free[0]
        elif not ANDET_FIRST_ROW <= row_number <= ANDET_LAST_ROW:
            raise ValueError("That row is not a shared cost row.")

        worksheet = self.get_worksheet(worksheet_name)
        updates = [
            {"range": rowcol_to_a1(row_number, DAY_SHEET_CHEF_COLUMN), "values": [[payer]]},
            {"range": rowcol_to_a1(row_number, DAY_SHEET_MENU_COLUMN), "values": [[description]]},
            {"range": rowcol_to_a1(row_number, DAY_SHEET_MEAL_PRICE_COLUMN), "values": [[amount]]},
        ]
        for label, column in signup_columns.items():
            updates.append(
                {
                    "range": rowcol_to_a1(row_number, column),
                    "values": [[1 if label in participants else ""]],
                }
            )
        worksheet.batch_update(updates)
        return row_number

    def swap_dinner(
        self,
        worksheet_name: str,
        day: int,
        from_label: str,
        to_label: str,
        other_day: int | None = None,
        by: str = "",
    ) -> None:
        """Hand a cooking night over, or trade two of them.

        The chef is one cell per day, so both shapes are the same write: give
        the day away, and — when the other person is cooking too — take their
        night in return. Refuses when the sheet no longer agrees about who is
        cooking, because the screen that offered the swap may be a minute old.
        """
        source = str(from_label).strip()
        target = str(to_label).strip()
        if not source or not target:
            raise ValueError("A swap needs both people.")
        if source == target:
            raise ValueError("That is already your dinner.")

        first_row = 1 + DAY_SHEET_DAY_OFFSET
        chef_column = rowcol_to_a1(1, DAY_SHEET_CHEF_COLUMN)[:-1]
        rows = self.get_worksheet(worksheet_name).batch_get(
            [f"{chef_column}{first_row}:{chef_column}{DAY_SHEET_LAST_DAY_ROW}"]
        )[0]

        def chef_on(number: int) -> str:
            index = number - 1
            if index < 0 or index >= len(rows):
                return ""
            row = list(rows[index]) + [""]
            return _format_room_label(row[0])

        if chef_on(day) != source:
            raise ValueError(
                f"{source} is not down to cook on the {ordinal(day)} any more — reload and look again."
            )
        if other_day is not None and chef_on(other_day) != target:
            raise ValueError(
                f"{target} is not down to cook on the {ordinal(other_day)} any more — reload and look again."
            )

        worksheet = self.get_worksheet(worksheet_name)
        updates = [
            {"range": rowcol_to_a1(day + DAY_SHEET_DAY_OFFSET, DAY_SHEET_CHEF_COLUMN), "values": [[target]]}
        ]
        if other_day is not None:
            updates.append(
                {
                    "range": rowcol_to_a1(other_day + DAY_SHEET_DAY_OFFSET, DAY_SHEET_CHEF_COLUMN),
                    "values": [[source]],
                }
            )
        worksheet.batch_update(updates)

        action_id = self._new_action_id()
        if other_day is None:
            summary = f"{source} gave the dinner on the {ordinal(day)} to {target}."
        else:
            summary = f"{source} and {target} swapped the {ordinal(day)} and the {ordinal(other_day)}."
        entries = [
            LogEntry(
                event="swapped_dinner",
                summary=summary,
                action_id=action_id,
                month_sheet=worksheet_name,
                by=by,
                person=source,
                from_label=str(day),
                to_label=str(other_day) if other_day is not None else "",
            )
        ]
        entries.append(
            LogEntry(
                event="swapped_dinner",
                summary=summary,
                action_id=action_id,
                month_sheet=worksheet_name,
                by=by,
                person=target,
                from_label=str(other_day) if other_day is not None else "",
                to_label=str(day),
            )
        )
        self._log_safely(entries)

    def clear_andet(self, worksheet_name: str, row_number: int, room_entries: List[RoomEntry]) -> None:
        if not ANDET_FIRST_ROW <= row_number <= ANDET_LAST_ROW:
            raise ValueError("That row is not a shared cost row.")
        worksheet = self.get_worksheet(worksheet_name)
        updates = [
            {"range": rowcol_to_a1(row_number, DAY_SHEET_CHEF_COLUMN), "values": [[""]]},
            {"range": rowcol_to_a1(row_number, DAY_SHEET_MENU_COLUMN), "values": [[""]]},
            {"range": rowcol_to_a1(row_number, DAY_SHEET_MEAL_PRICE_COLUMN), "values": [[""]]},
        ]
        for entry in room_entries:
            if entry.signup_column is not None:
                updates.append({"range": rowcol_to_a1(row_number, entry.signup_column), "values": [[""]]})
        worksheet.batch_update(updates)

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

    def update_meal_details(
        self,
        worksheet_name: str,
        day: int,
        dish_name: str,
        meal_price,
        menu_description: str,
    ):
        worksheet = self.get_worksheet(worksheet_name)
        row = day + DAY_SHEET_DAY_OFFSET
        price_value = "" if meal_price in (None, "") else _parse_optional_meal_price(meal_price)
        updates = [
            {
                "range": rowcol_to_a1(row, DAY_SHEET_MENU_COLUMN),
                "values": [[str(dish_name or "").strip()]],
            },
            {
                "range": rowcol_to_a1(row, DAY_SHEET_MEAL_PRICE_COLUMN),
                "values": [[price_value]],
            },
            {
                "range": rowcol_to_a1(row, DAY_SHEET_MENU_DESCRIPTION_COLUMN),
                "values": [[str(menu_description or "").strip()]],
            },
        ]
        worksheet.batch_update(updates)

    def add_purchase(self, worksheet_name: str, room_number: int | str, purchase_date: date, item: str, cost: float):
        worksheet = self.get_worksheet(worksheet_name)
        rows = worksheet.batch_get([PURCHASE_LOOKUP_RANGE])[0]
        start_row = _range_start_row(PURCHASE_LOOKUP_RANGE, 2)
        last_row = _range_end_row(PURCHASE_TABLE_RANGE, 33)

        target_row = None
        for index, cell in enumerate(rows, start=start_row):
            # gspread trims an empty row to [], the openpyxl test adapter gives
            # back [None] — both mean the row is free.
            if not _row_has_content(cell):
                target_row = index
                break
        if target_row is None:
            # Trailing empty rows are trimmed off the read, so the first free
            # row is the one after the block that came back.
            target_row = start_row + len(rows)

        if target_row > last_row:
            # Never write past the table: the sheet's Indkøb formula only sums
            # AC3:AG33, and the rows below hold the STATUS box.
            raise ValueError(
                f"The purchase table in {worksheet_name} is full "
                f"({PURCHASE_ROW_CAPACITY} of {PURCHASE_ROW_CAPACITY} rows used). "
                "Edit or delete a purchase, or ask an admin to make the table longer."
            )

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
            PURCHASE_TABLE_RANGE, 33
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
            PURCHASE_TABLE_RANGE, 33
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
        last_row = _range_end_row(TRANSACTION_TABLE_RANGE, 55)

        target_row = None
        for index, current_cell in enumerate(range_values):
            if not _row_has_content(current_cell):
                target_row = start_row + index
                break
        if target_row is None:
            target_row = start_row + len(range_values)

        if target_row > last_row:
            # The Indbetalt/udbetalt formula only sums AC44:AG55.
            raise ValueError(
                f"The kitchen fund payment table in {worksheet_name} is full "
                f"({TRANSACTION_ROW_CAPACITY} of {TRANSACTION_ROW_CAPACITY} rows used). "
                "Edit or delete a payment, or ask an admin to make the table longer."
            )

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
