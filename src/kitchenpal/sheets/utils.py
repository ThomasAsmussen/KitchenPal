from ..constants import DANISH_MONTHS, ENGLISH_MONTHS


def format_room_label(value) -> str:
    if value is None:
        return ""
    try:
        numeric = float(value)
        if numeric.is_integer():
            return str(int(numeric))
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def format_date_value(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)


def is_data_room_label(value) -> bool:
    label = format_room_label(value)
    if not label:
        return False
    if label.isdigit():
        return True
    return label.upper().startswith("FL") and label[2:].isdigit()


def parse_amount_value(value) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().lower()
    if not text:
        return 0.0

    text = text.replace("kr", "").replace("dkk", "").replace(" ", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return 0.0


def is_payout_type(tx_type: str) -> bool:
    if not tx_type:
        return False
    t = str(tx_type).strip().lower()
    return any(k in t for k in ("payout", "udbet", "udbetaling", "udbetaling", "udbetalt"))


def row_has_content(row) -> bool:
    return any(cell not in (None, "") for cell in row)


def first_cell_value(value_rows, default=""):
    if not value_rows or not value_rows[0]:
        return default
    return value_rows[0][0]


def required_first_cell_value(value_rows, sheet_name: str, cell_ref: str):
    value = first_cell_value(value_rows)
    if value in (None, ""):
        raise ValueError(f"Expected a value in {sheet_name}!{cell_ref}, but the cell was empty.")
    return value


def normalized_person_name(name: str) -> str:
    return " ".join(str(name or "").strip().lower().split())


def month_number(month_name: str) -> int:
    normalized = str(month_name).strip().lower()
    for index, name in enumerate(ENGLISH_MONTHS, start=1):
        if normalized == name.lower():
            return index
    for index, name in enumerate(DANISH_MONTHS, start=1):
        if normalized == name.lower():
            return index
    raise ValueError(f"Unknown month name '{month_name}'")


def month_sheet_candidates(month_number: int, year: int) -> list[str]:
    english = ENGLISH_MONTHS[month_number - 1]
    danish = DANISH_MONTHS[month_number - 1]
    candidates = [f"{english} {year}"]
    danish_candidate = f"{danish} {year}"
    if danish_candidate not in candidates:
        candidates.append(danish_candidate)
    return candidates


def resolve_month_sheet_name(existing_sheets: list[str], month_number: int, year: int) -> str | None:
    candidates = month_sheet_candidates(month_number, year)
    existing_set = set(existing_sheets)
    for candidate in candidates:
        if candidate in existing_set:
            return candidate

    existing_by_lower = {sheet.lower(): sheet for sheet in existing_sheets}
    for candidate in candidates:
        match = existing_by_lower.get(candidate.lower())
        if match:
            return match
    return None


def parse_month_sheet_name(worksheet_name: str) -> tuple[int, int] | None:
    parts = str(worksheet_name or "").split()
    if len(parts) < 2:
        return None
    if len(parts[-1]) != 4 or not parts[-1].isdigit():
        return None
    try:
        year = int(parts[-1])
        parsed_month_number = month_number(parts[0])
    except ValueError:
        return None
    return parsed_month_number, year
