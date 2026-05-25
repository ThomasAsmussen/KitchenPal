from datetime import date

import pytest

from kitchenpal import constants

from test_sheets_service import FakeWorksheet, set_room_directory, build_service, FakeSpreadsheet


def test_add_purchase_writes_first_empty_row():
    ws = FakeWorksheet("October 2024")
    # Simulate lookup rows: first filled, second empty -> target should be row 3
    ws.set_batch_get(constants.PURCHASE_LOOKUP_RANGE, [["filled"], []])

    service = build_service(FakeSpreadsheet([ws]))
    service.add_purchase("October 2024", 352, date(2026, 5, 24), "Banankage", 42.0)

    assert len(ws.batch_updates) == 1
    updates = ws.batch_updates[0]
    # target_row should be 3 (start=2 + index 1)
    assert updates[0]["range"] == f"{constants.PURCHASE_INSERT_START_COLUMN}3:{constants.PURCHASE_INSERT_END_COLUMN}3"
    assert updates[0]["values"] == [[352, "2026-05-24", "Banankage"]]
    assert updates[1]["range"] == f"{constants.PURCHASE_AMOUNT_COLUMN}3"
    assert updates[1]["values"] == [[42.0]]


def test_add_purchase_raises_when_no_empty_row():
    ws = FakeWorksheet("October 2024")
    # No empty rows in lookup -> should raise (mock doesn't support resizing)
    ws.set_batch_get(constants.PURCHASE_LOOKUP_RANGE, [["x"] for _ in range(3)])

    service = build_service(FakeSpreadsheet([ws]))
    with pytest.raises(ValueError):
        service.add_purchase("October 2024", 352, date(2026, 5, 24), "Item", 10.0)


def test_update_dish_name_and_signup_write_cells():
    ws = FakeWorksheet("October 2024")
    set_room_directory(ws)

    service = build_service(FakeSpreadsheet([ws]))
    # update dish name for day 3
    service.update_dish_name("October 2024", 3, "Spaghetti")
    assert (3 + constants.DAY_SHEET_DAY_OFFSET, constants.DAY_SHEET_MENU_COLUMN, "Spaghetti") in ws.updated_cells

    # update signup for room 346 (signup column mapped to 9 in set_room_directory)
    service.update_dish_signup("October 2024", 3, 346, 2)
    assert (3 + constants.DAY_SHEET_DAY_OFFSET, 9, 2) in ws.updated_cells


def test_add_drinks_raises_when_no_account_row():
    ws = FakeWorksheet("October 2024")
    # Provide empty signup header and account table so get_room_entries returns no rows
    ws.set_batch_get("I2:AA2", [[]])
    ws.set_batch_get("A45:B65", [])
    service = build_service(FakeSpreadsheet([ws]))
    with pytest.raises(ValueError):
        service.add_drinks("October 2024", 999, 1, 0)


def test_add_transaction_writes_values():
    ws = FakeWorksheet("October 2024")
    # First two entries filled, third empty -> target row = start_row + 2
    ws.set_batch_get(constants.TRANSACTION_LOOKUP_RANGE, [["filled"], ["filled"], []])

    service = build_service(FakeSpreadsheet([ws]))
    service.add_transaction("October 2024", 350, "Payment", 15.5, date(2026, 4, 24))

    assert len(ws.batch_updates) == 1
    updates = ws.batch_updates[0]
    # check values: room_number, formatted date dd/mm, transaction_type and amount
    assert updates[0]["values"][0][0] == 350
    assert updates[0]["values"][0][1] == "24/04"
    assert updates[0]["values"][0][2] == "Payment"
    assert updates[1]["values"] == [[15.5]]

