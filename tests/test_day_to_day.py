from datetime import date

from kitchenpal import constants
from kitchenpal.ui.day_to_day import (
    _delete_confirmation_key,
    _english_month,
    _display_chef,
    _format_optional_amount_dkk,
    _meal_budget,
    _meal_price_for_edit,
    _meal_price_per_person_display,
    _month_sheet_names,
    _next_available_row,
    _purchase_date_for_edit,
    _range_end_row,
    _range_start_row,
    _selected_day_display,
    _transaction_date_for_edit,
    _valid_days_for_sheet,
)
from kitchenpal.ui import day_to_day


def test_display_chef_includes_name_when_available():
    assert _display_chef("357", {"357": "Lukas"}) == "357 — Lukas"


def test_display_chef_falls_back_to_label_when_name_missing():
    assert _display_chef("357", {}) == "357"


def test_display_chef_returns_not_assigned_for_blank_value():
    assert _display_chef("", {}) == "Not assigned"


def test_meal_price_helpers_format_missing_and_present_prices():
    assert _format_optional_amount_dkk(0) == "Not set"
    assert _format_optional_amount_dkk(35.5) == "35.50 DKK"
    assert _meal_price_for_edit(0) == ""
    assert _meal_price_for_edit(35.5) == "35.50"
    assert _meal_budget("8") == 280
    assert _meal_price_per_person_display("8", 35.5) == "4.44 DKK"


def test_selected_day_display_uses_plain_ordinal_format():
    assert _selected_day_display("May", 25) == "May 25th"


def test_english_month_normalizes_danish_sheet_month():
    assert _english_month("Maj") == "May"


def test_transaction_date_for_edit_infers_sheet_year():
    assert _transaction_date_for_edit("24/05", "May 2026") == date(2026, 5, 24)


def test_purchase_date_for_edit_reads_iso_date():
    assert _purchase_date_for_edit("2026-05-24", "May 2026") == date(2026, 5, 24)


def test_range_row_helpers_read_a1_bounds():
    assert _range_start_row(constants.PURCHASE_LOOKUP_RANGE) == 2
    assert _range_end_row(constants.PURCHASE_LOOKUP_RANGE) == 33


def test_next_available_row_finds_gap():
    class Entry:
        def __init__(self, row_number):
            self.row_number = row_number

    assert _next_available_row([Entry(44), Entry(46)], 44) == 45


def test_delete_confirmation_key_is_scoped_to_kind_and_sheet():
    assert _delete_confirmation_key("purchase", "May 2026") == "day_to_day_confirm_delete_purchase:May 2026"


def test_month_reads_are_cached_for_the_whole_house_not_per_session():
    # session_state caching meant twenty residents fetched the same sheet twenty
    # times, against one shared API budget.
    from kitchenpal.ui import data

    for reader in (data.room_entries, data.day_rows, data.month_entries, data.andet_rows):
        assert hasattr(reader, "clear"), f"{reader} should be an st.cache_data reader"


def test_month_sheet_names_keeps_only_english_or_danish_month_year_names():
    sheet_names = ["Planning", "May 2026", "Maj 2026", "Bugs", "May", "2026 May", "May 26"]

    assert _month_sheet_names(sheet_names) == ["May 2026", "Maj 2026"]


def test_valid_days_for_sheet_uses_actual_month_length():
    assert _valid_days_for_sheet("February 2026") == list(range(1, 29))
    assert _valid_days_for_sheet("Maj 2026") == list(range(1, 32))
