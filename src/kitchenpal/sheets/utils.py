import re
from ..constants import DANISH_MONTHS, ENGLISH_MONTHS, NON_PERSON_ACCOUNT_LABELS


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


def is_room_label(value) -> bool:
    """A room in the house: 346-360. FL slots are not rooms."""
    label = format_room_label(value)
    return bool(label) and label.isdigit()


def ordinal(number) -> str:
    """1st, 2nd, 3rd, 4th — "the 31th" is how a summary looks unwritten."""
    value = int(number)
    if 10 <= (value % 100) <= 20:
        return f"{value}th"
    return f"{value}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(value % 10, 'th') }".replace(" ", "")


def is_person_account_label(value) -> bool:
    """A row that belongs to a person: a room, or an FL slot. Never Spotify."""
    normalized = str(value or "").strip().upper()
    return normalized.isdigit() or (normalized.startswith("FL") and normalized[2:].isdigit())


def is_occupied_account(label, name) -> bool:
    """An account that is a person right now.

    A room counts when someone lives in it; an FL slot counts only when it holds
    a name — an empty FL is a placeholder, not a housemate. Accounting rows like
    Spotify are never people.
    """
    text = format_room_label(label)
    if not text or text in NON_PERSON_ACCOUNT_LABELS:
        return False
    if not is_data_room_label(text):
        return False
    return bool(str(name or "").strip())


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


# "REG.NR: 0400 KONTONR.: 4032345684" is what the sheet holds today, but the
# cell is free text a treasurer maintains, so the labels are matched loosely.
_ACCOUNT_LABEL = re.compile(
    r"(?:konto\.?\s*nr|kontonr|account\s*(?:nr|no|number))\.?\s*:?", re.IGNORECASE
)
_NUMBER_RUN = re.compile(r"\d[\d\s.\-]*")


def _digits_in(text: str) -> str:
    match = _NUMBER_RUN.search(text or "")
    return "".join(ch for ch in match.group(0) if ch.isdigit()) if match else ""


def parse_bank_details(text) -> tuple[str, str, str] | None:
    """(reg number, account number, the line as written) — or None if there is none.

    Both numbers come back empty unless the account label was found AND there is
    a number on each side of it. Half a guess is worse than none here: the app
    shows the raw line instead, which is still correct and still copyable, and a
    resident typing a wrong account number into a bank app is not recoverable.
    """
    raw = str(text or "").strip()
    if not raw:
        return None
    label = _ACCOUNT_LABEL.search(raw)
    if label is None:
        return "", "", raw
    reg = _digits_in(raw[: label.start()])
    account = _digits_in(raw[label.end() :])
    if not reg or not account:
        return "", "", raw
    return reg, account, raw


def find_bank_details(cells) -> tuple[str, str, str] | None:
    """Pick the bank line out of the STATUS block.

    The block also holds "Bankkonto" and "Kontantbeholdning", which are labels
    for the fund's own figures and not somewhere to send money — and "Bankkonto"
    would happily match a looser account-label pattern. What separates the real
    line is that it carries an account number: eight digits or more, counted
    across the whole line so that "4032 34 56 84" still qualifies. No STATUS
    label has any digits at all.
    """
    for text in cells or []:
        raw = str(text or "").strip()
        if sum(character.isdigit() for character in raw) < 8:
            continue
        parsed = parse_bank_details(raw)
        if parsed:
            return parsed
    return None


# The STATUS box's four figures, matched on what the label says. The house wrote
# these labels and may reword them; the most specific match is tried first so
# that "Køkkenkassen I alt" cannot be taken for the bank row.
_FUND_ROW_MARKERS = (
    ("residents", ("samlede saldo", "brugernes")),
    ("cash", ("kontantbeholdning", "kontant")),
    ("total", ("i alt",)),
    ("bank", ("bankkonto", "bank")),
)


def find_fund_status(rows) -> dict[str, float] | None:
    """{bank, cash, residents, total} from the STATUS block, or None.

    None when the two figures the overview cannot be drawn without — the bank
    balance and the total — are not both there. A house that has reworded its
    sheet should see the rest of the app work rather than a wrong number.
    """
    found: dict[str, float] = {}
    for row in rows or []:
        label = str(row[0] if row else "").strip().lower()
        if not label:
            continue
        amount = row[4] if len(row) > 4 else ""
        for name, markers in _FUND_ROW_MARKERS:
            if name in found:
                continue
            if any(marker in label for marker in markers):
                found[name] = parse_amount_value(amount)
                break
    if "bank" not in found or "total" not in found:
        return None
    return {
        "bank": found["bank"],
        "cash": found.get("cash", 0.0),
        "residents": found.get("residents", 0.0),
        "total": found["total"],
    }
