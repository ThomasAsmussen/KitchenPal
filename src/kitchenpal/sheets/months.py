from ..constants import (
    ENGLISH_MONTHS,
    MONTH_METADATA_RANGE,
    PERSONAL_ACCOUNT_SHEET_ACCOUNT_CELL,
    PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE,
    PERSONAL_ACCOUNT_SHEET_PREVIOUS_BALANCE_RANGE,
    PERSONAL_ACCOUNT_TABLE_RANGE,
    PERSONAL_ACCOUNT_TRANSACTION_TOTAL_RANGE,
)
from .utils import (
    month_number as _month_number,
    month_sheet_candidates as _month_sheet_candidates,
    normalized_person_name as _normalized_person_name,
    parse_amount_value as _parse_amount_value,
    required_first_cell_value as _required_first_cell_value,
    resolve_month_sheet_name as _resolve_month_sheet_name,
)


class MonthSheetsMixin:
    def create_month_sheet(self, month_name: str, year: int):
        new_sheet_name = f"{month_name} {year}"
        existing = self.list_sheets()
        if new_sheet_name in existing:
            raise ValueError(f"A sheet named '{new_sheet_name}' already exists")

        template_sheet = self.get_worksheet(self._template_sheet_name)
        self._spreadsheet.duplicate_sheet(template_sheet.id, new_sheet_name=new_sheet_name)

    def copy_balances_from_previous_month(self, month_name: str, year: int):
        month_number = _month_number(month_name)
        previous_month_index = (month_number - 2) % 12
        previous_month_year = year - 1 if month_number == 1 else year

        existing_sheets = self.list_sheets()
        previous_sheet_name = _resolve_month_sheet_name(existing_sheets, previous_month_index + 1, previous_month_year)
        current_sheet_name = _resolve_month_sheet_name(existing_sheets, month_number, year)

        expected_current_sheet_name = f"{ENGLISH_MONTHS[month_number - 1]} {year}"
        if previous_sheet_name is None:
            previous_candidates = " or ".join(
                f"'{candidate}'" for candidate in _month_sheet_candidates(previous_month_index + 1, previous_month_year)
            )
            raise ValueError(
                f"Cannot update {expected_current_sheet_name}: previous month sheet {previous_candidates} does not exist."
            )
        if current_sheet_name is None:
            current_candidates = " or ".join(f"'{candidate}'" for candidate in _month_sheet_candidates(month_number, year))
            raise ValueError(f"Cannot update {expected_current_sheet_name}: sheet {current_candidates} does not exist.")

        previous_sheet = self.get_worksheet(previous_sheet_name)
        current_sheet = self.get_worksheet(current_sheet_name)

        previous_account_rows, balance_rows, account_rows = previous_sheet.batch_get(
            [PERSONAL_ACCOUNT_TABLE_RANGE, PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, PERSONAL_ACCOUNT_SHEET_ACCOUNT_CELL]
        )
        current_account_rows = current_sheet.batch_get([PERSONAL_ACCOUNT_TABLE_RANGE])[0]

        previous_balance_by_name = {}
        for index, row in enumerate(previous_account_rows):
            padded_row = row + [""] * 2
            name_key = _normalized_person_name(padded_row[1])
            if not name_key:
                continue
            balance_row = balance_rows[index] if index < len(balance_rows) else []
            previous_balance_by_name[name_key] = _parse_amount_value(balance_row[0] if balance_row else None)

        balances = []
        for row in current_account_rows:
            padded_row = row + [""] * 2
            current_name_key = _normalized_person_name(padded_row[1])
            balances.append(previous_balance_by_name.get(current_name_key, 0.0))

        account_value = _parse_amount_value(
            _required_first_cell_value(account_rows, previous_sheet_name, PERSONAL_ACCOUNT_SHEET_ACCOUNT_CELL)
        )
        account = f"{account_value:.2f}".replace(".", ",")
        account_formula = f"={account}+sum({PERSONAL_ACCOUNT_TRANSACTION_TOTAL_RANGE})"

        updates = [
            {"range": PERSONAL_ACCOUNT_SHEET_PREVIOUS_BALANCE_RANGE, "values": [[value] for value in balances]},
            {"range": MONTH_METADATA_RANGE, "values": [[month_number, year]]},
        ]
        current_sheet.batch_update(updates)
        current_sheet.update_acell(PERSONAL_ACCOUNT_SHEET_ACCOUNT_CELL, account_formula)
