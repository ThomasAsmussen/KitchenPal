from dataclasses import dataclass, field

from ..constants import (
    ENGLISH_MONTHS,
    MONTH_METADATA_RANGE,
    NON_PERSON_ACCOUNT_LABELS,
    PERSONAL_ACCOUNT_SHEET_ACCOUNT_CELL,
    PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE,
    PERSONAL_ACCOUNT_SHEET_PREVIOUS_BALANCE_RANGE,
    PERSONAL_ACCOUNT_TABLE_RANGE,
    PERSONAL_ACCOUNT_TABLE_START_ROW,
    PERSONAL_ACCOUNT_TRANSACTION_TOTAL_RANGE,
)
from .utils import (
    is_data_room_label as _is_data_room_label,
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
        self._blank_person_names(new_sheet_name)

    def _blank_person_names(self, worksheet_name: str) -> None:
        # A freshly created month sheet must arrive in a known state whatever
        # names the template holds: person rows blank, non-person rows kept.
        worksheet = self.get_worksheet(worksheet_name)
        rows = worksheet.batch_get([PERSONAL_ACCOUNT_TABLE_RANGE])[0]
        if not rows:
            return
        values = []
        for row in rows:
            padded = row + [""] * 2
            label = str(padded[0] or "").strip()
            name = str(padded[1] or "")
            values.append([""] if _is_data_room_label(label) else [name])
        end_row = PERSONAL_ACCOUNT_TABLE_START_ROW + len(values) - 1
        worksheet.batch_update(
            [{"range": f"B{PERSONAL_ACCOUNT_TABLE_START_ROW}:B{end_row}", "values": values}]
        )

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
