from dataclasses import dataclass, field

from ..constants import (
    DAY_SHEET_SIGNUP_HEADER_RANGE,
    ENGLISH_MONTHS,
    KITCHEN_FUND_BANK_RANGE,
    MONTH_METADATA_RANGE,
    PERSONAL_ACCOUNT_HEADER_LABEL,
    PERSONAL_ACCOUNT_HEADER_SEARCH_RANGE,
    NON_PERSON_ACCOUNT_LABELS,
    PERSONAL_ACCOUNT_SHEET_ACCOUNT_CELL,
    PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE,
    PERSONAL_ACCOUNT_SHEET_PREVIOUS_BALANCE_RANGE,
    PERSONAL_ACCOUNT_TABLE_RANGE,
    PERSONAL_ACCOUNT_TABLE_START_ROW,
    PERSONAL_ACCOUNT_TRANSACTION_TOTAL_RANGE,
)
from ..a1 import range_start_row as _range_start_row
from .models import BankDetails
from .utils import (
    find_bank_details as _find_bank_details,
    first_cell_value as _first_cell_value,
    format_room_label as _format_room_label,
    is_data_room_label as _is_data_room_label,
    parse_month_sheet_name as _parse_month_sheet_name,
    month_number as _month_number,
    month_sheet_candidates as _month_sheet_candidates,
    normalized_person_name as _normalized_person_name,
    parse_amount_value as _parse_amount_value,
    required_first_cell_value as _required_first_cell_value,
    resolve_month_sheet_name as _resolve_month_sheet_name,
)


@dataclass
class CopyBalancesReport:
    chased: list = field(default_factory=list)
    unplaced: list = field(default_factory=list)
    suspected_renames: list = field(default_factory=list)
    duplicate_names: list = field(default_factory=list)


class MonthSheetsMixin:
    def create_month_sheet(self, month_name: str, year: int):
        new_sheet_name = f"{month_name} {year}"
        existing = self.list_sheets()
        if new_sheet_name in existing:
            raise ValueError(f"A sheet named '{new_sheet_name}' already exists")

        template_sheet = self.get_worksheet(self._template_sheet_name)
        self._spreadsheet.duplicate_sheet(template_sheet.id, new_sheet_name=new_sheet_name)
        self.forget_worksheets()
        self._prepare_new_month_sheet(new_sheet_name, _month_number(month_name), year)

    def _prepare_new_month_sheet(self, worksheet_name: str, month_number: int, year: int) -> None:
        # A freshly created month sheet must arrive in a known state whatever the
        # template holds: person rows blank, non-person rows kept, and the month
        # it is actually for. Without the month, the sheet computes its weekdays
        # and dates from whatever the template was last used for.
        worksheet = self.get_worksheet(worksheet_name)
        rows = worksheet.batch_get([PERSONAL_ACCOUNT_TABLE_RANGE])[0]
        updates = [{"range": MONTH_METADATA_RANGE, "values": [[month_number, year]]}]
        if rows:
            values = []
            for row in rows:
                padded = row + [""] * 2
                label = str(padded[0] or "").strip()
                name = str(padded[1] or "")
                values.append([""] if _is_data_room_label(label) else [name])
            end_row = PERSONAL_ACCOUNT_TABLE_START_ROW + len(values) - 1
            updates.append({"range": f"B{PERSONAL_ACCOUNT_TABLE_START_ROW}:B{end_row}", "values": values})
        worksheet.batch_update(updates)

    def get_kitchen_fund_bank_details(self, worksheet_name: str) -> BankDetails | None:
        """Where to transfer money to the fund, as the sheet has it.

        None when the cell is empty: a house that has not filled it in should
        see the app work, not an error.
        """
        worksheet = self.get_worksheet(worksheet_name)
        rows = worksheet.batch_get([KITCHEN_FUND_BANK_RANGE])[0]
        found = _find_bank_details(row[0] if row else "" for row in rows)
        if found is None:
            return None
        reg, account, text = found
        return BankDetails(reg_number=reg, account_number=account, text=text)

    def check_month_sheet_integrity(self, worksheet_name: str) -> list[str]:
        # Month sheets are made by hand, and every range the app reads is a row
        # number. These checks are what turn a silent misread into a sentence.
        worksheet = self.get_worksheet(worksheet_name)
        label_rows, header_rows, signup_rows, metadata_rows = worksheet.batch_get(
            [
                PERSONAL_ACCOUNT_TABLE_RANGE,
                PERSONAL_ACCOUNT_HEADER_SEARCH_RANGE,
                DAY_SHEET_SIGNUP_HEADER_RANGE,
                MONTH_METADATA_RANGE,
            ]
        )
        formula_rows, account_cell_rows = worksheet.batch_get(
            [PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, PERSONAL_ACCOUNT_SHEET_ACCOUNT_CELL],
            value_render_option="FORMULA",
        )

        problems = []
        problems.extend(self._check_account_table_anchor(worksheet_name, header_rows))
        problems.extend(self._check_closing_formulas(worksheet_name, label_rows, formula_rows))
        problems.extend(self._check_signup_columns_line_up(worksheet_name, label_rows, signup_rows))
        problems.extend(self._check_account_formula(worksheet_name, account_cell_rows))
        problems.extend(self._check_month_metadata(worksheet_name, metadata_rows))
        return problems

    def _check_account_table_anchor(self, worksheet_name: str, header_rows) -> list[str]:
        # Everything the app reads about people is anchored on this one row.
        search_start = _range_start_row(PERSONAL_ACCOUNT_HEADER_SEARCH_RANGE, 1)
        expected_row = PERSONAL_ACCOUNT_TABLE_START_ROW - 1
        found_row = None
        for index, row in enumerate(header_rows):
            padded = list(row) + ["", ""]
            if str(padded[1] or "").strip().casefold() == PERSONAL_ACCOUNT_HEADER_LABEL.casefold():
                found_row = search_start + index
                break

        if found_row is None:
            return [
                f"{worksheet_name}: the '{PERSONAL_ACCOUNT_HEADER_LABEL}' header above the account table was not found "
                f"in {PERSONAL_ACCOUNT_HEADER_SEARCH_RANGE} — the app is reading names and balances from "
                f"{PERSONAL_ACCOUNT_TABLE_RANGE} and may be reading the wrong rows."
            ]
        if found_row != expected_row:
            return [
                f"{worksheet_name}: the account table starts at row {found_row + 1}, but the app reads "
                f"{PERSONAL_ACCOUNT_TABLE_RANGE}. Rows have been inserted or removed — update the sheet layout "
                "in constants.py before using this sheet."
            ]
        return []

    def _check_closing_formulas(self, worksheet_name: str, label_rows, formula_rows) -> list[str]:
        problems = []
        for index, row in enumerate(label_rows):
            padded = list(row) + ["", ""]
            label = str(padded[0] or "").strip()
            if not label:
                continue
            formula_row = formula_rows[index] if index < len(formula_rows) else []
            formula = str(formula_row[0]) if formula_row and formula_row[0] is not None else ""
            if not formula.startswith("="):
                row_number = PERSONAL_ACCOUNT_TABLE_START_ROW + index
                problems.append(
                    f"{worksheet_name}: account row {label} has no closing-balance formula in Z{row_number} — "
                    "balances on this row read as 0 and vanish at the next rollover."
                )
        return problems

    def _check_signup_columns_line_up(self, worksheet_name: str, label_rows, signup_rows) -> list[str]:
        # The sheet's own "Mad forbrug" formula is INDEX($I$3:$AB$53, 0, ROW(A1)):
        # it charges the nth account row using the nth signup column. If the two
        # orders drift apart, everyone is billed for someone else's dinners.
        signup_header = list(signup_rows[0]) if signup_rows else []
        problems = []
        for index, header_label in enumerate(signup_header):
            header = str(header_label or "").strip()
            if not header:
                continue
            account_row = list(label_rows[index]) + ["", ""] if index < len(label_rows) else ["", ""]
            account_label = str(account_row[0] or "").strip()
            if _format_room_label(account_label) != _format_room_label(header):
                problems.append(
                    f"{worksheet_name}: signup column {index + 1} is '{header}' but account row "
                    f"{PERSONAL_ACCOUNT_TABLE_START_ROW + index} is '{account_label or 'blank'}' — the two lists must "
                    "be in the same order or meal costs land on the wrong person."
                )
        return problems

    def _check_account_formula(self, worksheet_name: str, account_cell_rows) -> list[str]:
        value = _first_cell_value(account_cell_rows, "")
        if not str(value or "").strip().startswith("="):
            return [
                f"{worksheet_name}: {PERSONAL_ACCOUNT_SHEET_ACCOUNT_CELL} holds a typed number instead of a formula — "
                "the kitchen fund total will not follow this month's payments."
            ]
        return []

    def _check_month_metadata(self, worksheet_name: str, metadata_rows) -> list[str]:
        parsed = _parse_month_sheet_name(worksheet_name)
        if parsed is None:
            return []
        month_number, year = parsed
        row = list(metadata_rows[0]) + ["", ""] if metadata_rows else ["", ""]
        sheet_month = _parse_amount_value(row[0])
        sheet_year = _parse_amount_value(row[1])
        if not row[0] or not row[1]:
            return [
                f"{worksheet_name}: {MONTH_METADATA_RANGE} is empty — the weekday column cannot know which month "
                "this sheet is."
            ]
        if int(sheet_month) != month_number or int(sheet_year) != year:
            return [
                f"{worksheet_name}: {MONTH_METADATA_RANGE} says month {int(sheet_month)} of {int(sheet_year)} — "
                "the weekday column and the day dates are for the wrong month."
            ]
        return []

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

        report = CopyBalancesReport()

        previous_name_by_label = {}
        previous_balance_by_label = {}
        previous_balance_by_name = {}
        previous_people = []
        for index, row in enumerate(previous_account_rows):
            padded_row = row + [""] * 2
            label = str(padded_row[0] or "").strip()
            name = str(padded_row[1] or "").strip()
            balance_row = balance_rows[index] if index < len(balance_rows) else []
            balance = _parse_amount_value(balance_row[0] if balance_row else None)
            if label:
                previous_name_by_label[label] = name
                previous_balance_by_label[label] = balance
            if label and _is_data_room_label(label) and name:
                previous_balance_by_name[_normalized_person_name(name)] = balance
                previous_people.append((name, balance))

        current_rows = []
        for row in current_account_rows:
            padded_row = row + [""] * 2
            current_rows.append((str(padded_row[0] or "").strip(), str(padded_row[1] or "").strip()))

        names = [""] * len(current_rows)
        balances = [0.0] * len(current_rows)
        placed = set()
        kept_names = []

        # Pass 1: non-person rows carry forward by label; typed names are KEPT
        # and get that person's previous balance (0.0 for someone new).
        for index, (label, typed_name) in enumerate(current_rows):
            if label in NON_PERSON_ACCOUNT_LABELS:
                names[index] = previous_name_by_label.get(label, "")
                balances[index] = previous_balance_by_label.get(label, 0.0)
                continue
            if _is_data_room_label(label) and typed_name:
                names[index] = typed_name
                balances[index] = previous_balance_by_name.get(_normalized_person_name(typed_name), 0.0)
                kept_names.append(typed_name)
                placed.add(_normalized_person_name(typed_name))

        seen_names = set()
        flagged_names = set()
        for typed_name in kept_names:
            key = _normalized_person_name(typed_name)
            if key in seen_names and key not in flagged_names:
                report.duplicate_names.append(typed_name)
                flagged_names.add(key)
            seen_names.add(key)

        # Pass 2: fill blank person rows with the previous occupant of the
        # label, top-down, never placing anyone twice.
        for index, (label, typed_name) in enumerate(current_rows):
            if typed_name or label in NON_PERSON_ACCOUNT_LABELS or not _is_data_room_label(label):
                continue
            candidate = previous_name_by_label.get(label, "")
            key = _normalized_person_name(candidate)
            if candidate and key not in placed:
                names[index] = candidate
                balances[index] = previous_balance_by_name.get(key, 0.0)
                placed.add(key)

        # Pass 3: chase departed non-zero balances into the highest free FL
        # slots; when none is free, report them as unplaced.
        free_fl_slots = [
            (index, label)
            for index, (label, _) in enumerate(current_rows)
            if _is_data_room_label(label) and label.upper().startswith("FL") and not names[index]
        ]
        free_fl_slots.sort(key=lambda slot: int(slot[1][2:]), reverse=True)
        departed = set()
        for name, balance in previous_people:
            key = _normalized_person_name(name)
            if key in placed or key in departed or balance == 0:
                continue
            if free_fl_slots:
                slot_index, slot_label = free_fl_slots.pop(0)
                names[slot_index] = name
                balances[slot_index] = balance
                placed.add(key)
                report.chased.append((name, balance, slot_label))
            else:
                report.unplaced.append((name, balance))
            departed.add(key)

        # Pass 4: a room whose name changed while its previous occupant left a
        # non-zero balance and is not deliberately on the sheet looks like a
        # typo/rename — flag it for the UI.
        for label, typed_name in current_rows:
            if not typed_name or label in NON_PERSON_ACCOUNT_LABELS or not _is_data_room_label(label):
                continue
            previous_occupant = previous_name_by_label.get(label, "")
            if not previous_occupant:
                continue
            if _normalized_person_name(previous_occupant) == _normalized_person_name(typed_name):
                continue
            if _normalized_person_name(previous_occupant) in departed:
                report.suspected_renames.append((label, previous_occupant, typed_name))

        account_value = _parse_amount_value(
            _required_first_cell_value(account_rows, previous_sheet_name, PERSONAL_ACCOUNT_SHEET_ACCOUNT_CELL)
        )
        account = f"{account_value:.2f}".replace(".", ",")
        account_formula = f"={account}+sum({PERSONAL_ACCOUNT_TRANSACTION_TOTAL_RANGE})"

        updates = [
            {
                "range": f"B{PERSONAL_ACCOUNT_TABLE_START_ROW}:B{PERSONAL_ACCOUNT_TABLE_START_ROW + len(names) - 1}",
                "values": [[name] for name in names],
            },
            {"range": PERSONAL_ACCOUNT_SHEET_PREVIOUS_BALANCE_RANGE, "values": [[value] for value in balances]},
            {"range": MONTH_METADATA_RANGE, "values": [[month_number, year]]},
        ]
        current_sheet.batch_update(updates)
        current_sheet.update_acell(PERSONAL_ACCOUNT_SHEET_ACCOUNT_CELL, account_formula)
        return report
