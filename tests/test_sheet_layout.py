from kitchenpal import constants


def test_layout_object_matches_legacy_constant_aliases():
    layout = constants.SHEET_LAYOUT

    assert constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE == layout.personal_account.balance_range
    assert constants.PURCHASE_LOOKUP_RANGE == layout.purchases.lookup_range
    assert constants.TRANSACTION_AMOUNT_COLUMN == layout.transactions.amount_column
    assert constants.MONTH_METADATA_RANGE == "AR3:AS3"
    assert constants.PLANNING_HEADER_RANGE == layout.planning.header_range
    assert constants.PLANNING_HEADERS == layout.planning.headers


def test_table_ranges_are_grouped_by_workflow():
    layout = constants.SHEET_LAYOUT

    assert layout.day.drink_table_range == "AI3:AK21"
    assert layout.purchases.table_range == "AC3:AG43"
    assert layout.transactions.table_range == "AC44:AG200"
    assert layout.personal_account.kovs_header_range == "A1:AZ1"
    assert layout.personal_account.transaction_total_range == "AG44:AG55"
