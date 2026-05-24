from datetime import date
from dataclasses import dataclass
from typing import List, Tuple

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread.utils import rowcol_to_a1

from .config import AppConfig, GOOGLE_SHEETS_SCOPE
from .constants import (
    DAY_SHEET_DAY_OFFSET,
    DAY_SHEET_ROOM_COLUMN_OFFSET,
    DAY_SHEET_SIGNUP_HEADER_RANGE,
    ENGLISH_MONTHS,
    PERSONAL_ACCOUNT_BEER_COLUMN,
    PERSONAL_ACCOUNT_SHEET_ACCOUNT_CELL,
    PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE,
    PERSONAL_ACCOUNT_WINE_COLUMN,
    PERSONAL_ACCOUNT_TABLE_RANGE,
    PERSONAL_ACCOUNT_TABLE_START_ROW,
    PURCHASE_INSERT_END_COLUMN,
    PURCHASE_INSERT_START_COLUMN,
    PURCHASE_LOOKUP_RANGE,
    TRANSACTION_AMOUNT_COLUMN,
    TRANSACTION_INSERT_END_COLUMN,
    TRANSACTION_INSERT_START_COLUMN,
    TRANSACTION_LOOKUP_RANGE,
)


PLANNING_SHEET_NAME = "Planning"
PLANNING_HEADERS = ["Year", "Month", "Name", "Room", "Can", "Cannot", "Prefers", "Max 1 day"]


@dataclass(frozen=True)
class PlanningEntry:
    person: str
    room_number: str
    available_dates: str
    unavailable_dates: str
    preferred_dates: str
    limit_one_day: bool


@dataclass(frozen=True)
class RoomEntry:
    label: str
    name: str
    account_row: int
    signup_column: int | None


class SheetsService:
    def __init__(self, config: AppConfig):
        creds = ServiceAccountCredentials.from_json_keyfile_name(config.credentials_file, GOOGLE_SHEETS_SCOPE)
        client = gspread.authorize(creds)
        self._spreadsheet = client.open(config.spreadsheet_name)
        self._template_sheet_name = config.template_sheet_name

    def list_sheets(self) -> List[str]:
        return [ws.title for ws in self._spreadsheet.worksheets()]

    def get_worksheet(self, worksheet_name: str):
        return self._spreadsheet.worksheet(worksheet_name)

    def get_room_entries(self, worksheet_name: str) -> List[RoomEntry]:
        worksheet = self.get_worksheet(worksheet_name)
        signup_header = worksheet.batch_get([DAY_SHEET_SIGNUP_HEADER_RANGE])[0][0]
        signup_columns = {
            label.strip(): column_index
            for column_index, label in enumerate(signup_header, start=9)
            if label and label.strip()
        }

        account_rows = worksheet.batch_get([PERSONAL_ACCOUNT_TABLE_RANGE])[0]
        room_entries: List[RoomEntry] = []

        for row_offset, row in enumerate(account_rows, start=PERSONAL_ACCOUNT_TABLE_START_ROW):
            padded_row = row + [""] * 2
            label = padded_row[0].strip()
            if not label:
                continue

            room_entries.append(
                RoomEntry(
                    label=label,
                    name=padded_row[1].strip(),
                    account_row=row_offset,
                    signup_column=signup_columns.get(label),
                )
            )

        return room_entries

    def get_day_summary(self, worksheet_name: str, day: int) -> Tuple[str, str, str]:
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
            except Exception:
                count = 0
            if count > 0:
                signed_people.append(entry.name or entry.label)

        return signed_people

    def get_signup_room_entries(self, worksheet_name: str) -> List[RoomEntry]:
        return [entry for entry in self.get_room_entries(worksheet_name) if entry.signup_column is not None]

    def get_room_entry_map(self, worksheet_name: str) -> dict[str, RoomEntry]:
        return {entry.label: entry for entry in self.get_room_entries(worksheet_name)}

    def get_or_create_planning_worksheet(self):
        try:
            worksheet = self.get_worksheet(PLANNING_SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = self._spreadsheet.add_worksheet(title=PLANNING_SHEET_NAME, rows=200, cols=len(PLANNING_HEADERS))
            worksheet.update(range_name="A1:H1", values=[PLANNING_HEADERS])
            return worksheet

        values = worksheet.get_all_values()
        if not values:
            worksheet.update(range_name="A1:H1", values=[PLANNING_HEADERS])
        return worksheet

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

    def save_planning_entries(self, month_name: str, year: int, entries: List[PlanningEntry]):
        worksheet = self.get_or_create_planning_worksheet()
        existing_values = worksheet.get_all_values()
        preserved_rows = []

        for row in existing_values[1:]:
            padded_row = row + [""] * (len(PLANNING_HEADERS) - len(row))
            row_year, row_month = padded_row[0], padded_row[1]
            if row_year == str(year) and row_month == month_name:
                continue
            preserved_rows.append(padded_row[: len(PLANNING_HEADERS)])

        new_rows = [
            [
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
        ]
        worksheet.clear()
        worksheet.update(range_name="A1:H1", values=[PLANNING_HEADERS])
        if preserved_rows or new_rows:
            row_count = len(preserved_rows) + len(new_rows) + 1
            worksheet.update(range_name=f"A2:H{row_count}", values=preserved_rows + new_rows)

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

    def add_purchase(self, worksheet_name: str, room_number: int | str, purchase_date: date, item: str, cost: float):
        worksheet = self.get_worksheet(worksheet_name)
        rows = worksheet.batch_get([PURCHASE_LOOKUP_RANGE])[0]
        target_row = None
        for index, cell in enumerate(rows, start=2):
            if not cell:
                target_row = index
                break

        if target_row is None:
            target_row = 201

        updates = [
            {
                "range": f"{PURCHASE_INSERT_START_COLUMN}{target_row}:{PURCHASE_INSERT_END_COLUMN}{target_row}",
                "values": [[room_number, purchase_date.strftime("%Y-%m-%d"), item, cost]],
            }
        ]
        worksheet.batch_update(updates)

    def add_drinks(self, worksheet_name: str, room_number: int | str, beer_quantity: int, wine_quantity: int):
        worksheet = self.get_worksheet(worksheet_name)
        room_entry = self.get_room_entry_map(worksheet_name).get(str(room_number))
        if room_entry is None:
            raise ValueError(f"No account row found for room '{room_number}'")

        row = room_entry.account_row
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

    def add_transaction(self, worksheet_name: str, room_number: int | str, transaction_type: str, amount: float, transaction_date: date):
        worksheet = self.get_worksheet(worksheet_name)
        range_values = worksheet.batch_get([TRANSACTION_LOOKUP_RANGE])[0]

        target_row = None
        for index, current_cell in enumerate(range_values):
            if not current_cell:
                target_row = 44 + index
                break

        if target_row is None:
            raise ValueError(f"No available transaction rows in {TRANSACTION_LOOKUP_RANGE}")

        updates = [
            {
                "range": f"{TRANSACTION_INSERT_START_COLUMN}{target_row}:{TRANSACTION_INSERT_END_COLUMN}{target_row}",
                "values": [[room_number, transaction_date.strftime("%d/%m"), transaction_type]],
            },
            {
                "range": f"{TRANSACTION_AMOUNT_COLUMN}{target_row}",
                "values": [[amount]],
            },
        ]
        worksheet.batch_update(updates)

    def create_month_sheet(self, month_name: str, year: int):
        new_sheet_name = f"{month_name} {year}"
        existing = self.list_sheets()
        if new_sheet_name in existing:
            raise ValueError(f"A sheet named '{new_sheet_name}' already exists")

        template_sheet = self.get_worksheet(self._template_sheet_name)
        self._spreadsheet.duplicate_sheet(template_sheet.id, new_sheet_name=new_sheet_name)

    def copy_balances_from_previous_month(self, month_name: str, year: int):
        month_number = ENGLISH_MONTHS.index(month_name) + 1
        previous_month_index = (month_number - 2) % 12
        previous_month_year = year - 1 if month_number == 1 else year

        previous_sheet_name = f"{ENGLISH_MONTHS[previous_month_index]} {previous_month_year}"
        current_sheet_name = f"{month_name} {year}"

        previous_sheet = self.get_worksheet(previous_sheet_name)
        current_sheet = self.get_worksheet(current_sheet_name)

        data = previous_sheet.batch_get([PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, PERSONAL_ACCOUNT_SHEET_ACCOUNT_CELL])
        raw_balances = [item for sublist in data[0] for item in sublist]
        balances = [float(item.replace("kr", "").replace(" ", "").replace(".", "").replace(",", ".")) for item in raw_balances]

        account = data[1][0][0].replace("kr", "").replace(" ", "").replace(".", "")
        account_formula = f"={account}+sum(AF44:AF55)"

        updates = [
            {"range": "H45:H65", "values": [[value] for value in balances]},
            {"range": "AR3:AS3", "values": [[month_number, year]]},
        ]
        current_sheet.batch_update(updates)
        current_sheet.update_acell(PERSONAL_ACCOUNT_SHEET_ACCOUNT_CELL, account_formula)
