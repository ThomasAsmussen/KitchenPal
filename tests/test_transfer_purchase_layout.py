"""The one place the sheet's row/column layout is pinned to literal values.

Everything else reads these constants, so this file is what fails first if the
spreadsheet is rearranged again. Read against the live sheet on 2026-08-29,
after the Andet block grew from 9 rows to 20 and pushed the account table down
by 11 rows:

    rows  3-33   Indkøb (purchases) — the sheet sums SUMIF($AC$3:$AC$33, ...)
    row   34     empty
    rows 35-39   STATUS box (labels in AC, amounts in AG)
    rows 40-41   empty
    row   42     bank details
    row   43     payment table header
    rows 44-55   kitchen fund payments — SUMIF($AC$44:$AC$55, ...)
    rows 34-53   Andet (20 undated shared costs, columns A:AB)
    row   54     "Personlige Regnskaber"
    row   55     "Værelse | Navn" header
    rows 56-76   personal accounts: 346-360, FL1-FL5, Spotify
"""

from kitchenpal import constants


def test_transaction_constants_match_expected_sheet_layout():
    assert constants.TRANSACTION_LOOKUP_RANGE == "AC44:AC55", "Transaction lookup range mismatch"
    # The Indbetalt/udbetalt formula only sums AC44:AG55 — reading or writing
    # past row 55 silently misses a person's balance.
    assert constants.TRANSACTION_TABLE_RANGE == "AC44:AG55", "Transaction table range mismatch"
    assert constants.TRANSACTION_ROW_CAPACITY == 12
    assert constants.TRANSACTION_INSERT_START_COLUMN == "AC", "Transaction insert start column mismatch"
    assert constants.TRANSACTION_INSERT_END_COLUMN == "AE", "Transaction insert end column mismatch"
    assert constants.TRANSACTION_AMOUNT_COLUMN == "AG", "Transaction amount column mismatch"


def test_purchase_constants_stop_at_the_last_row_the_sheet_sums():
    # Row 34 and below belong to the STATUS box, and the Indkøb formula stops
    # at row 33: a purchase written below it never reaches a balance.
    assert constants.PURCHASE_LOOKUP_RANGE == "AC2:AC33"
    assert constants.PURCHASE_TABLE_RANGE == "AC3:AG33"
    assert constants.PURCHASE_ROW_CAPACITY == 31
    assert constants.PURCHASE_INSERT_START_COLUMN == "AC"
    assert constants.PURCHASE_INSERT_END_COLUMN == "AE"
    assert constants.PURCHASE_AMOUNT_COLUMN == "AG"


def test_month_carryover_constants_match_expected_sheet_layout():
    assert constants.PERSONAL_ACCOUNT_TABLE_RANGE == "A56:B76"
    assert constants.PERSONAL_ACCOUNT_TABLE_START_ROW == 56
    assert constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE == "Z56:Z76"
    assert constants.PERSONAL_ACCOUNT_SHEET_PREVIOUS_BALANCE_RANGE == "I56:I76"
    # These two sit above the Andet block, so the expansion left them alone.
    assert constants.PERSONAL_ACCOUNT_SHEET_ACCOUNT_CELL == "AG37"
    assert constants.PERSONAL_ACCOUNT_TRANSACTION_TOTAL_RANGE == "AG44:AG55"


def test_signup_header_covers_every_account_including_fl5():
    # LUKKET became FL4 and FL5 was added, so the header is 20 columns wide.
    assert constants.DAY_SHEET_SIGNUP_HEADER_RANGE == "I2:AB2"


def test_account_table_starts_one_row_below_its_header():
    assert constants.PERSONAL_ACCOUNT_HEADER_LABEL == "Navn"
    start = constants.PERSONAL_ACCOUNT_TABLE_START_ROW
    search = constants.PERSONAL_ACCOUNT_HEADER_SEARCH_RANGE
    assert search.startswith("A") and ":" in search
    first, last = search.split(":")
    assert int(first[1:]) < start <= int(last[1:]) + 1
