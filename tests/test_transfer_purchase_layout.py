from kitchenpal import constants


def test_transaction_constants_match_expected_sheet_layout():
    # Expected layout in the spreadsheet: lookup in AC44:AC55, values in AC:AE, amount in AG
    assert constants.TRANSACTION_LOOKUP_RANGE == "AC44:AC55", "Transaction lookup range mismatch"
    assert constants.TRANSACTION_INSERT_START_COLUMN == "AC", "Transaction insert start column mismatch"
    assert constants.TRANSACTION_INSERT_END_COLUMN == "AE", "Transaction insert end column mismatch"
    assert constants.TRANSACTION_AMOUNT_COLUMN == "AG", "Transaction amount column mismatch"


def test_purchase_constants_present():
    assert constants.PURCHASE_LOOKUP_RANGE == "AC2:AC43"
    assert constants.PURCHASE_INSERT_START_COLUMN == "AC"
    assert constants.PURCHASE_INSERT_END_COLUMN == "AE"
    assert constants.PURCHASE_AMOUNT_COLUMN == "AG"


def test_month_carryover_constants_match_expected_sheet_layout():
    assert constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE == "Z45:Z65"
    assert constants.PERSONAL_ACCOUNT_SHEET_PREVIOUS_BALANCE_RANGE == "I45:I65"
    assert constants.PERSONAL_ACCOUNT_SHEET_ACCOUNT_CELL == "AG37"
