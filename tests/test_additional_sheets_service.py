from datetime import date

import pytest

from kitchenpal import constants

from kitchenpal.sheets_service import RoomEntry

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
    # Every row of the table is taken, so the next purchase would land past the
    # last row the sheet's Indkøb formula sums — that must raise, not spill.
    ws.set_batch_get(
        constants.PURCHASE_LOOKUP_RANGE,
        [["header"]] + [["x"] for _ in range(constants.PURCHASE_ROW_CAPACITY)],
    )

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
    ws.set_batch_get(constants.DAY_SHEET_SIGNUP_HEADER_RANGE, [[]])
    ws.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, [])
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


def test_add_purchase_writes_to_the_first_free_row():
    ws = FakeWorksheet("October 2024")
    ws.set_batch_get(constants.PURCHASE_LOOKUP_RANGE, [["Værelse"], ["346"], ["347"]])

    service = build_service(FakeSpreadsheet([ws]))
    service.add_purchase("October 2024", 352, date(2026, 5, 24), "Banankage", 42.0)

    assert ws.batch_updates == [
        [
            {"range": "AC5:AE5", "values": [[352, "2026-05-24", "Banankage"]]},
            {"range": "AG5", "values": [[42.0]]},
        ]
    ]


def test_add_transaction_raises_when_the_payment_table_is_full():
    ws = FakeWorksheet("October 2024")
    ws.set_batch_get(
        constants.TRANSACTION_LOOKUP_RANGE,
        [["346"] for _ in range(constants.TRANSACTION_ROW_CAPACITY)],
    )

    service = build_service(FakeSpreadsheet([ws]))

    with pytest.raises(ValueError, match="full"):
        service.add_transaction("October 2024", 346, "Payment to kitchen fund", 100.0, date(2026, 5, 24))

    assert ws.batch_updates == []


def _day_row(day, chef="", menu="", count="", price="", signups=()):
    row = [f"{day}.", "Mandag", chef, menu, "", price, count] + [""] * 21
    for column, value in signups:
        row[column - 1] = value
    return row


def test_get_day_rows_reads_the_month_in_one_call():
    ws = FakeWorksheet("June 2026")
    ws.set_batch_get("AV3:AV33", [["with a green salad"], [], []])
    ws.set_batch_get(
        "A3:AB33",
        [
            _day_row(1, chef="352", menu="Lasagne", count="4", price="180,00 kr", signups=[(9, "1"), (13, "3")]),
            _day_row(2),
            [],  # a trimmed, empty row beyond the end of the month
        ],
    )
    rooms = [
        RoomEntry(label="346", name="Julia", account_row=56, signup_column=9),
        RoomEntry(label="350", name="Josefine", account_row=60, signup_column=13),
        RoomEntry(label="Spotify", name="", account_row=76, signup_column=None),
    ]

    service = build_service(FakeSpreadsheet([ws]))
    rows = service.get_day_rows("June 2026", rooms)

    assert [row.day for row in rows] == [1, 2]
    first = rows[0]
    assert (first.chef, first.menu, first.signed_up, first.meal_price) == ("352", "Lasagne", 4, 180.0)
    assert first.menu_description == "with a green salad"
    assert rows[1].menu_description == ""
    assert first.signups == {"346": 1, "350": 3}
    assert rows[1].signed_up == 0 and rows[1].chef == ""
    # both ranges arrive in a single round trip
    assert ws.batch_get_calls == [["A3:AB33", "AV3:AV33"]]


def test_get_account_statement_reads_the_parts_behind_a_balance():
    ws = FakeWorksheet("August 2026")
    row = [""] * 26
    row[0], row[1] = "351", "August"
    row[8] = "1.165,85 kr"    # I  carried in
    row[13] = "-102,00 kr"    # N  drinks
    row[15] = "116,80 kr"     # P  cooked
    row[17] = "-29,20 kr"     # R  dinners eaten
    row[19] = "38,00 kr"      # T  purchases
    row[21] = "-75,00 kr"     # V  dues
    row[25] = "1.114,45 kr"   # Z  balance
    ws.set_batch_get("A56:Z56", [row])

    service = build_service(FakeSpreadsheet([ws]))
    statement = service.get_account_statement(
        "August 2026", RoomEntry(label="351", name="August", account_row=56, signup_column=14)
    )

    assert (statement.label, statement.name, statement.balance) == ("351", "August", 1114.45)
    assert statement.components == {
        "carried_in": 1165.85,
        "interest": 0.0,
        "drinks": -102.0,
        "cooked": 116.8,
        "dinners": -29.2,
        "purchases": 38.0,
        "dues": -75.0,
        "payments": 0.0,
    }
    # the sheet does the arithmetic; the app only names the parts
    assert round(sum(statement.components.values()), 2) == statement.balance
    assert ws.batch_get_calls == [["A56:Z56"]]


def test_get_account_statement_survives_an_empty_row():
    ws = FakeWorksheet("August 2026")
    ws.set_batch_get("A71:Z71", [[]])

    service = build_service(FakeSpreadsheet([ws]))
    statement = service.get_account_statement(
        "August 2026", RoomEntry(label="FL1", name="", account_row=71, signup_column=24)
    )

    assert statement.balance == 0.0
    assert set(statement.components.values()) == {0.0}



def _andet_room_entries():
    return [
        RoomEntry(label="346", name="Julia", account_row=56, signup_column=9),
        RoomEntry(label="350", name="Josefine", account_row=60, signup_column=13),
        RoomEntry(label="Spotify", name="", account_row=76, signup_column=None),
    ]


def _andet_sheet(rows):
    ws = FakeWorksheet("August 2026")
    ws.set_batch_get("A34:AB53", rows)
    return ws


def test_get_andet_rows_skips_the_empty_slots():
    row = [""] * 28
    row[2] = "350"          # C  who paid
    row[3] = "Birthday cake"  # D  what it was
    row[5] = "240,00 kr"    # F  total
    row[8] = "1"            # I  346 was in on it
    row[12] = "1"           # M  350 was in on it
    service = build_service(FakeSpreadsheet([_andet_sheet([row, [""] * 28, []])]))

    rows = service.get_andet_rows("August 2026", _andet_room_entries())

    assert len(rows) == 1
    entry = rows[0]
    assert (entry.row_number, entry.payer, entry.description, entry.amount) == (34, "350", "Birthday cake", 240.0)
    assert entry.participants == {"346": 1, "350": 1}
    assert entry.head_count == 2
    assert entry.share == 120.0


def test_save_andet_takes_the_first_free_slot_and_marks_who_was_in():
    ws = _andet_sheet([])
    service = build_service(FakeSpreadsheet([ws]))

    row_number = service.save_andet(
        "August 2026",
        payer="350",
        description="Birthday cake",
        amount=240.0,
        participants=["346", "350"],
        room_entries=_andet_room_entries(),
    )

    assert row_number == 34
    assert ws.batch_updates == [
        [
            {"range": "C34", "values": [["350"]]},
            {"range": "D34", "values": [["Birthday cake"]]},
            {"range": "F34", "values": [[240.0]]},
            {"range": "I34", "values": [[1]]},
            {"range": "M34", "values": [[1]]},
        ]
    ]


def test_save_andet_refuses_an_empty_participant_list():
    service = build_service(FakeSpreadsheet([_andet_sheet([])]))

    with pytest.raises(ValueError, match="at least one person"):
        service.save_andet(
            "August 2026",
            payer="350",
            description="Cake",
            amount=100.0,
            participants=[],
            room_entries=_andet_room_entries(),
        )


def test_save_andet_reports_when_every_slot_is_taken():
    taken = []
    for index in range(constants.ANDET_ROW_CAPACITY):
        row = [""] * 28
        row[3] = f"Cost {index}"
        taken.append(row)
    service = build_service(FakeSpreadsheet([_andet_sheet(taken)]))

    with pytest.raises(ValueError, match="in use"):
        service.save_andet(
            "August 2026",
            payer="350",
            description="One too many",
            amount=10.0,
            participants=["350"],
            room_entries=_andet_room_entries(),
        )


def test_clear_andet_empties_the_row_including_the_marks():
    ws = _andet_sheet([])
    service = build_service(FakeSpreadsheet([ws]))

    service.clear_andet("August 2026", 35, _andet_room_entries())

    assert ws.batch_updates == [
        [
            {"range": "C35", "values": [[""]]},
            {"range": "D35", "values": [[""]]},
            {"range": "F35", "values": [[""]]},
            {"range": "I35", "values": [[""]]},
            {"range": "M35", "values": [[""]]},
        ]
    ]


def test_get_worksheet_asks_the_spreadsheet_once_per_name():
    # gspread re-fetches the sheet list on every worksheet() call, so holding the
    # handle removes a round trip from every single service method.
    ws = FakeWorksheet("August 2026")
    spreadsheet = FakeSpreadsheet([ws])
    calls = []
    original = spreadsheet.worksheet

    def counting(name):
        calls.append(name)
        return original(name)

    spreadsheet.worksheet = counting
    service = build_service(spreadsheet)

    assert service.get_worksheet("August 2026") is ws
    assert service.get_worksheet("August 2026") is ws
    assert calls == ["August 2026"]

    service.forget_worksheets()
    assert service.get_worksheet("August 2026") is ws
    assert calls == ["August 2026", "August 2026"]
