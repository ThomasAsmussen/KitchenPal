from types import SimpleNamespace

import pytest

from kitchenpal import constants
from kitchenpal.sheets_service import PlanningEntry, RoomEntry, SheetsService


def set_room_directory(ws):
    ws.set_batch_get(
        constants.DAY_SHEET_SIGNUP_HEADER_RANGE,
        [["346", "347", "348", "349", "350", "351", "352", "353", "354", "355", "356", "357", "358", "359", "360", "FL1", "FL2", "FL3", "LUKKET"]],
    )
    ws.set_batch_get(
        constants.PERSONAL_ACCOUNT_TABLE_RANGE,
        [
            ["346", "Julia"],
            ["347", "Johannes"],
            ["348", "Alberte"],
            ["349", "Thomas Tams"],
            ["350", "Josefine"],
            ["351", "August"],
            ["352", "Asta"],
            ["353", "Frederik Bjerg"],
            ["354", "Philip"],
            ["355", "Sofie Andersen"],
            ["356", "Thomas Jerver"],
            ["357", "Lukas"],
            ["358", "Sofie Gregersen"],
            ["359", "Thor"],
            ["360", "Sylvester"],
            ["FL1", "Gustav"],
            ["FL2", "Astrid"],
            ["FL3", "Esther"],
            ["FL4", ""],
            ["FL5", ""],
            ["Spotify", "Daniel Vorting"],
        ],
    )


class FakeWorksheet:
    def __init__(self, title, worksheet_id=1):
        self.title = title
        self.id = worksheet_id
        self._cells = {}
        self._batch_get = {}
        self.batch_get_calls = []
        self.updated_cells = []
        self.batch_updates = []
        self.updated_acells = {}
        self.updated_ranges = []
        self.cleared = False
        self._all_values = []
        self.appended_rows = []

    def append_rows(self, rows, value_input_option=None):
        self.appended_rows.append(rows)
        self._all_values = self._all_values + [list(row) for row in rows]

    def set_cell(self, row, col, value):
        self._cells[(row, col)] = value

    def set_batch_get(self, range_name, value):
        self._batch_get[range_name] = value

    def set_batch_get_formulas(self, range_name, value):
        self._batch_get_formulas = getattr(self, "_batch_get_formulas", {})
        self._batch_get_formulas[range_name] = value

    def set_all_values(self, value):
        self._all_values = value

    def cell(self, row, col):
        return SimpleNamespace(value=self._cells.get((row, col)))

    def update_cell(self, row, col, value):
        self.updated_cells.append((row, col, value))
        self._cells[(row, col)] = value

    def batch_get(self, ranges, value_render_option=None):
        self.batch_get_calls.append(list(ranges))
        if value_render_option == "FORMULA":
            formulas = getattr(self, "_batch_get_formulas", {})
            # An unset range reads back empty, exactly like an untouched
            # region of a real sheet.
            return [formulas.get(r, []) for r in ranges]
        return [self._batch_get.get(r, []) for r in ranges]

    def batch_update(self, updates):
        self.batch_updates.append(updates)

    def update_acell(self, cell_ref, value):
        self.updated_acells[cell_ref] = value

    def get_all_values(self):
        return self._all_values

    def clear(self):
        self.cleared = True
        self._all_values = []

    def update(self, range_name, values):
        self.updated_ranges.append((range_name, values))


class FakeSpreadsheet:
    def __init__(self, worksheets):
        self._worksheets = {ws.title: ws for ws in worksheets}
        self.duplicate_calls = []

    def worksheets(self):
        return list(self._worksheets.values())

    def worksheet(self, name):
        return self._worksheets[name]

    def duplicate_sheet(self, sheet_id, new_sheet_name):
        self.duplicate_calls.append((sheet_id, new_sheet_name))
        template = next((ws for ws in self._worksheets.values() if ws.id == sheet_id), None)
        clone = FakeWorksheet(new_sheet_name, worksheet_id=sheet_id + 1)
        if template is not None:
            clone._batch_get = dict(template._batch_get)
            clone._cells = dict(template._cells)
            clone._all_values = [list(row) for row in template._all_values]
        self._worksheets[new_sheet_name] = clone


def build_service(fake_spreadsheet):
    service = SheetsService.__new__(SheetsService)
    service._spreadsheet = fake_spreadsheet
    service._template_sheet_name = "Template"
    return service


def test_add_drinks_accumulates_existing_values():
    ws = FakeWorksheet("October 2024")
    set_room_directory(ws)
    header_row = [None] * 52
    header_row[34] = "KØVS"
    ws.set_batch_get("A1:AZ1", [header_row])
    ws.set_batch_get("AI3:AI300", [["346"], ["347"], ["348"], ["349"], ["350"], ["351"], ["352"], ["353"], ["354"], ["355"], ["356"], ["357"], ["358"], ["359"], ["360"], ["FL1"]])
    ws.set_cell(18, 36, "4")
    ws.set_cell(18, 37, "2")

    service = build_service(FakeSpreadsheet([ws]))
    new_beer, new_wine = service.add_drinks("October 2024", "FL1", 3, 1)

    assert (18, 36, 7) in ws.updated_cells
    assert (18, 37, 3) in ws.updated_cells
    assert new_beer == 7
    assert new_wine == 3


def test_get_room_entries_reads_room_names_and_fl_rooms():
    ws = FakeWorksheet("October 2024")
    set_room_directory(ws)

    service = build_service(FakeSpreadsheet([ws]))
    entries = service.get_room_entries("October 2024")

    assert any(entry.label == "346" and entry.name == "Julia" and entry.signup_column == 9 for entry in entries)
    assert any(entry.label == "FL1" and entry.name == "Gustav" and entry.signup_column == 24 for entry in entries)
    assert any(entry.label == "FL4" and entry.signup_column is None for entry in entries)


def test_get_day_summary_and_signed_up_people_use_batched_reads():
    ws = FakeWorksheet("October 2024")
    set_room_directory(ws)
    ws.set_batch_get("C5:G5", [["Chef Name", "Menu Name", "", "", "8"]])
    ws.set_batch_get("I5", [["1"]])
    ws.set_batch_get("J5", [[""]])
    ws.set_batch_get("K5", [["2"]])

    service = build_service(FakeSpreadsheet([ws]))
    room_entries = service.get_room_entries("October 2024")[:3]

    chef, menu, signed_up = service.get_day_summary("October 2024", 3)
    signed_people = service.get_signed_up_people("October 2024", 3, room_entries)

    assert chef == "Chef Name"
    assert menu == "Menu Name"
    assert signed_up == "8"
    assert signed_people == ["Julia", "Alberte (2)"]
    assert ws.batch_get_calls[-1] == ["I5", "J5", "K5"]


def test_get_day_details_reads_price_and_menu_description():
    ws = FakeWorksheet("October 2024")
    ws.set_batch_get("C5:G5", [["357", "Lasagna", "", "35,50 kr", "8"]])
    ws.set_batch_get("AV5", [["Vegetarian option available."]])

    service = build_service(FakeSpreadsheet([ws]))
    details = service.get_day_details("October 2024", 3)

    assert details.chef == "357"
    assert details.menu == "Lasagna"
    assert details.signed_up == "8"
    assert details.meal_price == 35.5
    assert details.menu_description == "Vegetarian option available."
    assert ws.batch_get_calls[-1] == ["C5:G5", "AV5"]


def test_update_meal_details_writes_menu_price_and_description():
    ws = FakeWorksheet("October 2024")

    service = build_service(FakeSpreadsheet([ws]))
    service.update_meal_details("October 2024", 3, "Lasagna", "35,50", "With salad")

    assert len(ws.batch_updates) == 1
    updates = ws.batch_updates[0]
    assert updates[0]["range"] == "D5"
    assert updates[0]["values"] == [["Lasagna"]]
    assert updates[1]["range"] == "F5"
    assert updates[1]["values"] == [[35.5]]
    assert updates[2]["range"] == "AV5"
    assert updates[2]["values"] == [["With salad"]]


def test_update_meal_details_rejects_invalid_price():
    ws = FakeWorksheet("October 2024")

    service = build_service(FakeSpreadsheet([ws]))
    with pytest.raises(ValueError, match="valid meal price"):
        service.update_meal_details("October 2024", 3, "Lasagna", "free-ish", "")


def test_add_transaction_writes_first_empty_row():
    ws = FakeWorksheet("October 2024")
    ws.set_batch_get(constants.TRANSACTION_LOOKUP_RANGE, [["filled"], ["filled"], [], ["filled"]])

    service = build_service(FakeSpreadsheet([ws]))
    service.add_transaction("October 2024", 350, "Payment to kitchen fund", 125.5, __import__("datetime").date(2026, 4, 24))

    assert len(ws.batch_updates) == 1
    updates = ws.batch_updates[0]
    assert updates[0]["range"] == "AC46:AE46"
    assert updates[1]["range"] == "AG46"


def test_add_transaction_raises_when_no_empty_row():
    ws = FakeWorksheet("October 2024")
    ws.set_batch_get(constants.TRANSACTION_LOOKUP_RANGE, [["x"] for _ in range(12)])

    service = build_service(FakeSpreadsheet([ws]))
    with pytest.raises(ValueError):
        service.add_transaction("October 2024", 350, "Payment", 1.0, __import__("datetime").date(2026, 4, 24))


def test_get_drink_entries_returns_room_rows():
    ws = FakeWorksheet("October 2024")
    set_room_directory(ws)
    header_row = [None] * 52
    header_row[34] = "KØVS"
    ws.set_batch_get("A1:AZ1", [header_row])
    ws.set_batch_get(
        constants.DRINK_TABLE_RANGE,
        [
            [346, 46, None],
            [347, 40, None],
            ["FL1", None, None],
        ],
    )

    service = build_service(FakeSpreadsheet([ws]))
    entries = service.get_drink_entries("October 2024")

    assert [entry.row_number for entry in entries] == [3, 4, 5]
    assert [entry.room for entry in entries] == ["346", "347", "FL1"]
    assert [entry.name for entry in entries] == ["Julia", "Johannes", "Gustav"]
    assert [entry.beer_soda for entry in entries] == [46, 40, 0]
    assert [entry.wine for entry in entries] == [0, 0, 0]


def test_update_drinks_writes_existing_row():
    ws = FakeWorksheet("October 2024")

    service = build_service(FakeSpreadsheet([ws]))
    service.update_drinks("October 2024", 18, 7, 3)

    assert len(ws.batch_updates) == 1
    updates = ws.batch_updates[0]
    assert updates[0]["range"] == "AJ18"
    assert updates[0]["values"] == [[7]]
    assert updates[1]["range"] == "AK18"
    assert updates[1]["values"] == [[3]]


def test_get_purchase_entries_returns_rows():
    ws = FakeWorksheet("October 2024")
    ws.set_batch_get(
        constants.PURCHASE_TABLE_RANGE,
        [
            ["Værelse", "Dato", "Vare", None, "Beløb"],
            [352, __import__("datetime").datetime(2026, 5, 3), "Banankage til køkkenmøde", None, "42,00 kr"],
            [353, __import__("datetime").datetime(2026, 5, 1), "Grøn tuborg 18x2", None, 194.0],
            [None, None, None, None, None],
        ],
    )

    service = build_service(FakeSpreadsheet([ws]))
    entries = service.get_purchase_entries("October 2024")

    assert [entry.row_number for entry in entries] == [4, 5]
    assert [entry.room for entry in entries] == ["352", "353"]
    assert [entry.date for entry in entries] == ["2026-05-03", "2026-05-01"]
    assert [entry.item for entry in entries] == ["Banankage til køkkenmøde", "Grøn tuborg 18x2"]
    assert [entry.amount for entry in entries] == [42.0, 194.0]


def test_update_purchase_writes_existing_row():
    ws = FakeWorksheet("October 2024")

    service = build_service(FakeSpreadsheet([ws]))
    service.update_purchase("October 2024", 5, "353", __import__("datetime").date(2026, 5, 24), "Green Tuborg", 194.0)

    assert len(ws.batch_updates) == 1
    updates = ws.batch_updates[0]
    assert updates[0]["range"] == "AC5:AE5"
    assert updates[0]["values"] == [["353", "2026-05-24", "Green Tuborg"]]
    assert updates[1]["range"] == "AG5"
    assert updates[1]["values"] == [[194.0]]


def test_delete_purchase_clears_existing_row():
    ws = FakeWorksheet("October 2024")

    service = build_service(FakeSpreadsheet([ws]))
    service.delete_purchase("October 2024", 5)

    assert len(ws.batch_updates) == 1
    updates = ws.batch_updates[0]
    assert updates[0]["range"] == "AC5:AE5"
    assert updates[0]["values"] == [["", "", ""]]
    assert updates[1]["range"] == "AG5"
    assert updates[1]["values"] == [[""]]


def test_get_transaction_entries_returns_rows():
    ws = FakeWorksheet("October 2024")
    ws.set_batch_get(
        constants.TRANSACTION_TABLE_RANGE,
        [
            ["Spotify", "1/5", "Udbetaling", None, "-29,00 kr"],
            ["FL2", "4/5", "Indbetaling", None, "202,62 kr"],
            ["346", "24/05", "Payment to kitchen fund", None, 83.0],
            [None, None, None, None, None],
        ],
    )

    service = build_service(FakeSpreadsheet([ws]))
    entries = service.get_transaction_entries("October 2024")

    assert [entry.row_number for entry in entries] == [44, 45, 46]
    assert [entry.room for entry in entries] == ["Spotify", "FL2", "346"]
    assert [entry.date for entry in entries] == ["1/5", "4/5", "24/05"]
    assert [entry.transaction_type for entry in entries] == ["Udbetaling", "Indbetaling", "Payment to kitchen fund"]
    assert [entry.amount for entry in entries] == [-29.0, 202.62, 83.0]


def test_get_day_to_day_entries_reads_lists_in_one_batch():
    ws = FakeWorksheet("October 2024")
    ws.set_batch_get(
        constants.DRINK_TABLE_RANGE,
        [
            [346, 46, None],
            ["FL1", None, 1],
        ],
    )
    ws.set_batch_get(
        constants.PURCHASE_TABLE_RANGE,
        [
            ["Værelse", "Dato", "Vare", None, "Beløb"],
            [352, __import__("datetime").datetime(2026, 5, 3), "Banankage", None, "42,00 kr"],
        ],
    )
    ws.set_batch_get(
        constants.TRANSACTION_TABLE_RANGE,
        [
            ["FL2", "4/5", "Indbetaling", None, "202,62 kr"],
        ],
    )

    service = build_service(FakeSpreadsheet([ws]))
    entries = service.get_day_to_day_entries(
        "October 2024",
        [
            RoomEntry(label="346", name="Julia", account_row=45, signup_column=9),
            RoomEntry(label="FL1", name="Gustav", account_row=60, signup_column=24),
        ],
    )

    assert ws.batch_get_calls == [[constants.DRINK_TABLE_RANGE, constants.PURCHASE_TABLE_RANGE, constants.TRANSACTION_TABLE_RANGE]]
    assert [entry.name for entry in entries.drinks] == ["Julia", "Gustav"]
    assert [entry.item for entry in entries.purchases] == ["Banankage"]
    assert [entry.room for entry in entries.transactions] == ["FL2"]


def test_get_transaction_payout_marks_amount_negative():
    ws = FakeWorksheet("October 2024")
    # empty lookup so add_transaction writes to first lookup row
    ws.set_batch_get(constants.TRANSACTION_LOOKUP_RANGE, [[], ["x"], ["x"]])

    service = build_service(FakeSpreadsheet([ws]))
    service.add_transaction("October 2024", 346, "Udbetaling", 29.0, __import__("datetime").date(2026, 5, 24))

    assert len(ws.batch_updates) == 1
    updates = ws.batch_updates[0]
    assert updates[1]["values"] == [[-29.0]]


def test_update_transaction_writes_existing_row():
    ws = FakeWorksheet("October 2024")

    service = build_service(FakeSpreadsheet([ws]))
    service.update_transaction("October 2024", 46, "FL2", "Payout from kitchen fund", 202.62, __import__("datetime").date(2026, 5, 24))

    assert len(ws.batch_updates) == 1
    updates = ws.batch_updates[0]
    assert updates[0]["range"] == "AC46:AE46"
    assert updates[0]["values"] == [["FL2", "24/05", "Payout from kitchen fund"]]
    assert updates[1]["range"] == "AG46"
    assert updates[1]["values"] == [[-202.62]]


def test_delete_transaction_clears_existing_row():
    ws = FakeWorksheet("October 2024")

    service = build_service(FakeSpreadsheet([ws]))
    service.delete_transaction("October 2024", 46)

    assert len(ws.batch_updates) == 1
    updates = ws.batch_updates[0]
    assert updates[0]["range"] == "AC46:AE46"
    assert updates[0]["values"] == [["", "", ""]]
    assert updates[1]["range"] == "AG46"
    assert updates[1]["values"] == [[""]]


def test_get_drink_entries_skips_header_row():
    ws = FakeWorksheet("October 2024")
    set_room_directory(ws)
    header_row = [None] * 52
    header_row[34] = "KØVS"
    ws.set_batch_get("A1:AZ1", [header_row])
    ws.set_batch_get(
        constants.DRINK_TABLE_RANGE,
        [
            ["Værelse", "Øl/Sodavand", "Vin"],
            [346, 46, 1],
        ],
    )

    service = build_service(FakeSpreadsheet([ws]))
    entries = service.get_drink_entries("October 2024")

    assert [entry.room for entry in entries] == ["346"]
    assert [entry.name for entry in entries] == ["Julia"]
    assert [entry.beer_soda for entry in entries] == [46]
    assert [entry.wine for entry in entries] == [1]


def test_create_month_sheet_duplicates_template_and_blanks_person_names():
    # A new month sheet must arrive in a known state whatever the template
    # holds: person names blanked, non-person rows (Spotify) left untouched.
    template = FakeWorksheet("Template", worksheet_id=999)
    template.set_batch_get(
        constants.PERSONAL_ACCOUNT_TABLE_RANGE,
        [["346", "Stale Name"], ["FL1", "Old FL Person"], ["Spotify", "Daniel Vorting"]],
    )
    other = FakeWorksheet("October 2024")
    spreadsheet = FakeSpreadsheet([template, other])
    service = build_service(spreadsheet)

    service.create_month_sheet("November", 2026)

    assert spreadsheet.duplicate_calls == [(999, "November 2026")]
    new_sheet = spreadsheet.worksheet("November 2026")
    assert new_sheet.batch_updates == [
        [{"range": "B56:B58", "values": [[""], [""], ["Daniel Vorting"]]}]
    ]


def test_create_month_sheet_raises_if_exists():
    template = FakeWorksheet("Template", worksheet_id=999)
    existing = FakeWorksheet("November 2026")
    spreadsheet = FakeSpreadsheet([template, existing])
    service = build_service(spreadsheet)

    with pytest.raises(ValueError):
        service.create_month_sheet("November", 2026)


def test_save_planning_entries_updates_person_without_overwriting_others():
    ws = FakeWorksheet("Planning")
    ws.set_all_values(
        [
            ["Year", "Month", "Name", "Room", "Can", "Cannot", "Prefers", "Max 1 day"],
            ["2026", "May", "Julia", "357", "1, 2", "", "", "FALSE"],
            ["2026", "May", "Thomas", "359", "", "3", "", "TRUE"],
            ["2026", "June", "Julia", "357", "4", "", "", "FALSE"],
        ]
    )

    service = build_service(FakeSpreadsheet([ws]))
    service.save_planning_entries(
        "May",
        2026,
        [
            PlanningEntry(
                person="Julia",
                room_number="357",
                available_dates="5",
                unavailable_dates="",
                preferred_dates="5",
                limit_one_day=True,
            )
        ],
    )

    assert ws.cleared is True
    assert ws.updated_ranges[0] == ("A1:H1", [["Year", "Month", "Name", "Room", "Can", "Cannot", "Prefers", "Max 1 day"]])
    assert ws.updated_ranges[1] == (
        "A2:H4",
        [
            [2026, "May", "Julia", "357", "5", "", "5", "TRUE"],
            ["2026", "May", "Thomas", "359", "", "3", "", "TRUE"],
            ["2026", "June", "Julia", "357", "4", "", "", "FALSE"],
        ],
    )


def test_save_planning_entries_appends_person_when_no_request_exists():
    ws = FakeWorksheet("Planning")
    ws.set_all_values(
        [
            ["Year", "Month", "Name", "Room", "Can", "Cannot", "Prefers", "Max 1 day"],
            ["2026", "May", "Thomas", "359", "", "3", "", "TRUE"],
        ]
    )

    service = build_service(FakeSpreadsheet([ws]))
    service.save_planning_entries(
        "May",
        2026,
        [
            PlanningEntry(
                person="Julia",
                room_number="357",
                available_dates="5",
                unavailable_dates="",
                preferred_dates="",
                limit_one_day=False,
            )
        ],
    )

    assert ws.updated_ranges[1] == (
        "A2:H3",
        [
            ["2026", "May", "Thomas", "359", "", "3", "", "TRUE"],
            [2026, "May", "Julia", "357", "5", "", "", "FALSE"],
        ],
    )


def test_save_planning_entries_matches_the_room_not_the_stored_name():
    # The Planning row for a room may have been written while the month sheet
    # had no name for it (a fresh sheet blanks B45:B65), so column C holds the
    # room number. The next save must update that row, not append a second one.
    ws = FakeWorksheet("Planning")
    ws.set_all_values(
        [
            ["Year", "Month", "Name", "Room", "Can", "Cannot", "Prefers", "Max 1 day"],
            ["2026", "September", "348", "348", "16, 21", "", "", "FALSE"],
            ["2026", "September", "350", "350", "1, 2, 3, 8, 9, 10", "", "", "FALSE"],
        ]
    )

    service = build_service(FakeSpreadsheet([ws]))
    service.save_planning_entries(
        "September",
        2026,
        [
            PlanningEntry(
                person="Josefine",
                room_number="350",
                available_dates="1, 2, 3, 7, 8, 9, 10",
                unavailable_dates="",
                preferred_dates="",
                limit_one_day=False,
            )
        ],
    )

    assert ws.updated_ranges[1] == (
        "A2:H3",
        [
            ["2026", "September", "348", "348", "16, 21", "", "", "FALSE"],
            [2026, "September", "Josefine", "350", "1, 2, 3, 7, 8, 9, 10", "", "", "FALSE"],
        ],
    )


def test_save_planning_entries_collapses_duplicate_rows_for_one_room():
    # Rows the old name-keyed matching left behind: the same room twice, once
    # under the room number and once under the person's name.
    ws = FakeWorksheet("Planning")
    ws.set_all_values(
        [
            ["Year", "Month", "Name", "Room", "Can", "Cannot", "Prefers", "Max 1 day"],
            ["2026", "September", "350", "350", "1, 2, 3, 8, 9, 10", "", "", "FALSE"],
            ["2026", "September", "352", "352", "13, 23", "", "", "FALSE"],
            ["2026", "September", "Josefine", "350", "1, 2, 3, 7, 8, 9, 10", "", "", "FALSE"],
        ]
    )

    service = build_service(FakeSpreadsheet([ws]))
    service.save_planning_entries(
        "September",
        2026,
        [
            PlanningEntry(
                person="Josefine",
                room_number="350",
                available_dates="2, 3",
                unavailable_dates="",
                preferred_dates="3",
                limit_one_day=True,
            )
        ],
    )

    assert ws.updated_ranges[1] == (
        "A2:H3",
        [
            [2026, "September", "Josefine", "350", "2, 3", "", "3", "TRUE"],
            ["2026", "September", "352", "352", "13, 23", "", "", "FALSE"],
        ],
    )


def test_save_planning_entries_keeps_rows_without_a_room_apart():
    ws = FakeWorksheet("Planning")
    ws.set_all_values(
        [
            ["Year", "Month", "Name", "Room", "Can", "Cannot", "Prefers", "Max 1 day"],
            ["2026", "September", "Gustav", "", "1", "", "", "FALSE"],
            ["2026", "September", "Astrid", "", "2", "", "", "FALSE"],
        ]
    )

    service = build_service(FakeSpreadsheet([ws]))
    service.save_planning_entries(
        "September",
        2026,
        [
            PlanningEntry(
                person="Astrid",
                room_number="",
                available_dates="3",
                unavailable_dates="",
                preferred_dates="",
                limit_one_day=False,
            )
        ],
    )

    assert ws.updated_ranges[1] == (
        "A2:H3",
        [
            ["2026", "September", "Gustav", "", "1", "", "", "FALSE"],
            [2026, "September", "Astrid", "", "3", "", "", "FALSE"],
        ],
    )


def test_get_possible_days_limit_reads_saved_month_limit():
    ws = FakeWorksheet(constants.POSSIBLE_DAYS_SHEET_NAME)
    ws.set_all_values(
        [
            constants.POSSIBLE_DAYS_HEADERS,
            ["2026", "May", "1-10, Thursday"],
            ["2026", "June", "2, 4"],
        ]
    )
    service = build_service(FakeSpreadsheet([ws]))

    assert service.get_possible_days_limit("May", 2026) == "1-10, Thursday"
    assert service.get_possible_days_limit("July", 2026) == ""


def test_get_possible_days_limit_initializes_blank_sheet():
    ws = FakeWorksheet(constants.POSSIBLE_DAYS_SHEET_NAME)
    service = build_service(FakeSpreadsheet([ws]))

    assert service.get_possible_days_limit("May", 2026) == ""
    assert ws.updated_ranges == [(constants.POSSIBLE_DAYS_HEADER_RANGE, [constants.POSSIBLE_DAYS_HEADERS])]


def test_save_possible_days_limit_updates_existing_month_without_overwriting_others():
    ws = FakeWorksheet(constants.POSSIBLE_DAYS_SHEET_NAME)
    ws.set_all_values(
        [
            constants.POSSIBLE_DAYS_HEADERS,
            ["2026", "May", "1-10"],
            ["2026", "June", "2, 4"],
        ]
    )
    service = build_service(FakeSpreadsheet([ws]))

    service.save_possible_days_limit("May", 2026, "Thursday")

    assert ws.cleared is True
    assert ws.updated_ranges[0] == (constants.POSSIBLE_DAYS_HEADER_RANGE, [constants.POSSIBLE_DAYS_HEADERS])
    assert ws.updated_ranges[1] == (
        "A2:C3",
        [
            [2026, "May", "Thursday"],
            ["2026", "June", "2, 4"],
        ],
    )


def test_save_possible_days_limit_appends_new_month():
    ws = FakeWorksheet(constants.POSSIBLE_DAYS_SHEET_NAME)
    ws.set_all_values([constants.POSSIBLE_DAYS_HEADERS, ["2026", "May", "1-10"]])
    service = build_service(FakeSpreadsheet([ws]))

    service.save_possible_days_limit("June", 2026, "2, 4")

    assert ws.updated_ranges[1] == (
        "A2:C3",
        [
            ["2026", "May", "1-10"],
            [2026, "June", "2, 4"],
        ],
    )


def test_copy_balances_from_previous_month_updates_expected_ranges():
    previous = FakeWorksheet("April 2026")
    previous.set_batch_get(
        constants.PERSONAL_ACCOUNT_TABLE_RANGE,
        [
            ["346", "Julia"],
            ["347", "Johannes"],
            ["348", "Alberte"],
            ["349", "Thomas"],
        ],
    )
    previous.set_batch_get(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, [["1.234,50 kr"], ["Beløb"], [500], ["0,00 kr"]])
    previous.set_batch_get("AG37", [["2.000,00 kr"]])

    current = FakeWorksheet("May 2026")
    current.set_batch_get(
        constants.PERSONAL_ACCOUNT_TABLE_RANGE,
        [
            ["346", "Julia"],
            ["347", "Johannes"],
            ["348", "Alberte"],
            ["349", "Thomas"],
        ],
    )
    spreadsheet = FakeSpreadsheet([previous, current])
    service = build_service(spreadsheet)

    service.copy_balances_from_previous_month("May", 2026)

    assert len(current.batch_updates) == 1
    updates = current.batch_updates[0]

    assert updates[0]["range"] == "B56:B59"
    assert updates[0]["values"] == [["Julia"], ["Johannes"], ["Alberte"], ["Thomas"]]
    assert updates[1]["range"] == constants.PERSONAL_ACCOUNT_SHEET_PREVIOUS_BALANCE_RANGE
    assert updates[1]["values"] == [[1234.5], [0.0], [500.0], [0.0]]
    assert updates[2]["range"] == "AS3:AT3"
    assert updates[2]["values"] == [[5, 2026]]
    assert current.updated_acells["AG37"] == "=2000,00+sum(AG44:AG55)"


def test_copy_balances_from_previous_month_requires_previous_sheet():
    current = FakeWorksheet("June 2026")
    service = build_service(FakeSpreadsheet([current]))

    with pytest.raises(ValueError, match="previous month sheet 'May 2026' or 'Maj 2026' does not exist"):
        service.copy_balances_from_previous_month("June", 2026)


def test_copy_balances_from_previous_month_requires_current_sheet():
    previous = FakeWorksheet("May 2026")
    service = build_service(FakeSpreadsheet([previous]))

    with pytest.raises(ValueError, match="sheet 'June 2026' or 'Juni 2026' does not exist"):
        service.copy_balances_from_previous_month("June", 2026)


def test_copy_balances_from_previous_month_accepts_danish_sheet_names():
    previous = FakeWorksheet("Maj 2026")
    previous.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, [["346", "Julia"], ["347", "Johannes"]])
    previous.set_batch_get(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, [["1.234,50 kr"], ["0,00 kr"]])
    previous.set_batch_get("AG37", [["2.000,00 kr"]])

    current = FakeWorksheet("Juni 2026")
    current.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, [["346", "Julia"], ["347", "Johannes"]])
    service = build_service(FakeSpreadsheet([previous, current]))

    service.copy_balances_from_previous_month("Juni", 2026)

    assert len(current.batch_updates) == 1
    updates = current.batch_updates[0]
    assert updates[0]["range"] == "B56:B57"
    assert updates[0]["values"] == [["Julia"], ["Johannes"]]
    assert updates[1]["range"] == constants.PERSONAL_ACCOUNT_SHEET_PREVIOUS_BALANCE_RANGE
    assert updates[1]["values"] == [[1234.5], [0.0]]
    assert updates[2]["range"] == "AS3:AT3"
    assert updates[2]["values"] == [[6, 2026]]
    assert current.updated_acells["AG37"] == "=2000,00+sum(AG44:AG55)"


def test_copy_balances_fills_blank_names_and_keeps_typed_names():
    # v2 contract: blank current names are filled from the previous occupant of
    # the label; a non-blank current name is KEPT (never overwritten) and gets
    # that person's previous balance (0.0 for someone new to the house).
    previous = FakeWorksheet("May 2026")
    previous.set_batch_get(
        constants.PERSONAL_ACCOUNT_TABLE_RANGE,
        [
            ["346", "Julia"],
            ["347", "Johannes"],
            ["FL1", "Gustav"],
        ],
    )
    previous.set_batch_get(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, [[100.0], [200.0], [300.0]])
    previous.set_batch_get("AG37", [["2.000,00 kr"]])

    current = FakeWorksheet("June 2026")
    current.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, [["346", ""], ["347", ""], ["FL1", ""], ["FL2", "Template Person"]])
    service = build_service(FakeSpreadsheet([previous, current]))

    report = service.copy_balances_from_previous_month("June", 2026)

    updates = current.batch_updates[0]
    assert updates[0]["range"] == "B56:B59"
    assert updates[0]["values"] == [["Julia"], ["Johannes"], ["Gustav"], ["Template Person"]]
    assert updates[1]["range"] == constants.PERSONAL_ACCOUNT_SHEET_PREVIOUS_BALANCE_RANGE
    assert updates[1]["values"] == [[100.0], [200.0], [300.0], [0.0]]
    assert report.chased == []
    assert report.unplaced == []


def test_copy_balances_from_previous_month_requires_account_value():
    previous = FakeWorksheet("May 2026")
    previous.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, [["346", "Julia"]])
    previous.set_batch_get(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, [["100,00 kr"]])
    previous.set_batch_get("AG37", [])

    current = FakeWorksheet("June 2026")
    current.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, [["346", "Julia"]])
    service = build_service(FakeSpreadsheet([previous, current]))

    with pytest.raises(ValueError, match=r"Expected a value in May 2026!AG37"):
        service.copy_balances_from_previous_month("June", 2026)

    assert current.batch_updates == []
    assert current.updated_acells == {}


def test_add_person_as_fl_uses_first_available_fl_spot():
    ws = FakeWorksheet("June 2026")
    ws.set_batch_get(
        constants.PERSONAL_ACCOUNT_TABLE_RANGE,
        [["346", "Julia"], ["FL1", "Gustav"], ["FL2", ""], ["FL3", ""]],
    )
    ws.set_batch_get(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, [[100.0], [0.0], [0.0], [0.0]])
    ws.set_batch_get(constants.DAY_SHEET_SIGNUP_HEADER_RANGE, [["346", "347", "348", "349", "350", "351", "352", "353", "354", "355", "356", "357", "358", "359", "360", "FL1", "FL2", "FL3", "LUKKET"]])
    service = build_service(FakeSpreadsheet([ws]))

    fl_label = service.add_person_as_fl("June 2026", "New Person")

    assert fl_label == "FL2"
    assert ws.batch_updates == [[{"range": "B58", "values": [["New Person"]]}, {"range": "I58", "values": [[0.0]]}]]


def test_replace_room_person_moves_replaced_person_to_first_available_fl():
    ws = FakeWorksheet("June 2026")
    ws.set_batch_get(
        constants.PERSONAL_ACCOUNT_TABLE_RANGE,
        [["346", "Julia"], ["347", "Johannes"], ["FL1", ""], ["FL2", "Gustav"]],
    )
    ws.set_batch_get(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, [[100.0], [200.0], [0.0], [300.0]])
    ws.set_cell(56, 9, 100.0)
    ws.set_cell(58, 9, "")
    service = build_service(FakeSpreadsheet([ws]))

    fl_label = service.replace_room_person("June 2026", "346", "New Person")

    assert fl_label == "FL1"
    assert ws.batch_updates == [
        [
            {"range": "B56", "values": [["New Person"]]},
            {"range": "I56", "values": [[0.0]]},
            {"range": "B58", "values": [["Julia"]]},
            {"range": "I58", "values": [[100.0]]},
        ]
    ]


def test_replace_room_person_moves_existing_fl_person_into_room():
    ws = FakeWorksheet("June 2026")
    ws.set_batch_get(
        constants.PERSONAL_ACCOUNT_TABLE_RANGE,
        [["346", "Julia"], ["347", "Johannes"], ["FL1", "Gustav"], ["FL2", ""]],
    )
    ws.set_batch_get(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, [[100.0], [200.0], [300.0], [0.0]])
    ws.set_cell(56, 9, 100.0)
    ws.set_cell(58, 9, 300.0)
    service = build_service(FakeSpreadsheet([ws]))

    fl_label = service.replace_room_person("June 2026", "346", "Gustav")

    assert fl_label == "FL1"
    assert ws.batch_updates == [
        [
            {"range": "B56", "values": [["Gustav"]]},
            {"range": "I56", "values": [[300.0]]},
            {"range": "B58", "values": [["Julia"]]},
            {"range": "I58", "values": [[100.0]]},
        ]
    ]


def test_replace_room_person_allows_empty_room():
    ws = FakeWorksheet("June 2026")
    ws.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, [["346", ""], ["FL1", "Gustav"]])
    ws.set_batch_get(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, [[0.0], [300.0]])
    service = build_service(FakeSpreadsheet([ws]))

    label = service.replace_room_person("June 2026", "346", "New Person")

    assert label == "346"
    assert ws.batch_updates == [
        [
            {"range": "B56", "values": [["New Person"]]},
            {"range": "I56", "values": [[0.0]]},
        ]
    ]


def test_move_person_between_accounts_moves_to_empty_account():
    ws = FakeWorksheet("June 2026")
    ws.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, [["346", "Julia"], ["FL1", ""]])
    ws.set_batch_get(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, [[100.0], [0.0]])
    ws.set_cell(56, 9, 100.0)
    ws.set_cell(57, 9, "")
    service = build_service(FakeSpreadsheet([ws]))

    service.move_person_between_accounts("June 2026", "346", "FL1")

    assert ws.batch_updates == [
        [
            {"range": "B57", "values": [["Julia"]]},
            {"range": "I57", "values": [[100.0]]},
            {"range": "B56", "values": [[""]]},
            {"range": "I56", "values": [[0.0]]},
        ]
    ]


def test_move_person_between_accounts_swaps_occupied_accounts():
    ws = FakeWorksheet("June 2026")
    ws.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, [["346", "Julia"], ["347", "Johannes"]])
    ws.set_batch_get(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, [[100.0], [200.0]])
    ws.set_cell(56, 9, 100.0)
    ws.set_cell(57, 9, 200.0)
    service = build_service(FakeSpreadsheet([ws]))

    service.move_person_between_accounts("June 2026", "346", "347")

    assert ws.batch_updates == [
        [
            {"range": "B57", "values": [["Julia"]]},
            {"range": "I57", "values": [[100.0]]},
            {"range": "B56", "values": [["Johannes"]]},
            {"range": "I56", "values": [[200.0]]},
        ]
    ]


def test_delete_fl_person_requires_zero_balance():
    ws = FakeWorksheet("June 2026")
    ws.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, [["346", "Julia"], ["FL1", "Gustav"]])
    ws.set_batch_get(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, [[0.0], [50.0]])
    service = build_service(FakeSpreadsheet([ws]))

    with pytest.raises(ValueError, match="balance is 50.00 DKK"):
        service.delete_fl_person("June 2026", "Gustav")

    assert ws.updated_cells == []


def test_delete_fl_person_clears_name_when_balance_is_zero():
    ws = FakeWorksheet("June 2026")
    ws.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, [["346", "Julia"], ["FL1", "Gustav"]])
    ws.set_batch_get(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, [[0.0], [0.0]])
    service = build_service(FakeSpreadsheet([ws]))

    service.delete_fl_person("June 2026", "Gustav")

    assert ws.batch_updates == [[{"range": "B57", "values": [[""]]}, {"range": "I57", "values": [[0.0]]}]]


def test_delete_fl_person_checks_previous_month_balance_when_provided():
    previous = FakeWorksheet("May 2026")
    previous.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, [["FL1", "Gustav"]])
    previous.set_batch_get(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, [[50.0]])

    current = FakeWorksheet("June 2026")
    current.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, [["FL1", "Gustav"]])
    current.set_batch_get(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, [[0.0]])

    service = build_service(FakeSpreadsheet([previous, current]))

    with pytest.raises(ValueError, match="balance is 50.00 DKK"):
        service.delete_fl_person("June 2026", "Gustav", balance_source_worksheet_name="May 2026")

    assert current.updated_cells == []


def test_previous_month_sheet_name_accepts_danish_and_english_names():
    previous = FakeWorksheet("Maj 2026")
    current = FakeWorksheet("June 2026")
    service = build_service(FakeSpreadsheet([previous, current]))

    assert service.previous_month_sheet_name("June 2026") == "Maj 2026"


def test_populate_cooks_for_month_writes_room_numbers_to_day_rows():
    ws = FakeWorksheet("May 2026")
    service = build_service(FakeSpreadsheet([ws]))

    service.populate_cooks_for_month("May 2026", {1: "Philip", 3: "Thomas"}, {"Philip": 346, "Thomas": 359})

    assert ws.batch_updates == [
        [
            {"range": "C3", "values": [[346]]},
            {"range": "C5", "values": [[359]]},
        ]
    ]


def test_copy_balances_from_previous_month_january_reads_december_of_previous_year():
    previous = FakeWorksheet("December 2026")
    previous.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, [["346", "Julia"], ["347", "Johannes"]])
    previous.set_batch_get(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, [["100,00 kr"], ["-50,00 kr"]])
    previous.set_batch_get("AG37", [["2.000,00 kr"]])

    current = FakeWorksheet("January 2027")
    current.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, [["346", "Julia"], ["347", "Johannes"]])
    service = build_service(FakeSpreadsheet([previous, current]))

    service.copy_balances_from_previous_month("January", 2027)

    updates = current.batch_updates[0]
    assert updates[0]["values"] == [["Julia"], ["Johannes"]]
    assert updates[1]["values"] == [[100.0], [-50.0]]
    assert updates[2]["values"] == [[1, 2027]]


# --- Characterization tests: pin the copy-balances contract as it behaves today ---


def _copy_balances_sheets(previous_rows, previous_balances, current_rows, previous_name="May 2026", current_name="June 2026"):
    previous = FakeWorksheet(previous_name)
    previous.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, previous_rows)
    previous.set_batch_get(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, previous_balances)
    previous.set_batch_get("AG37", [["2.000,00 kr"]])
    current = FakeWorksheet(current_name)
    current.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, current_rows)
    return previous, current


def test_copy_balances_writes_exactly_three_ranges_plus_account_formula():
    previous, current = _copy_balances_sheets([["346", "Julia"]], [[100.0]], [["346", "Julia"]])
    service = build_service(FakeSpreadsheet([previous, current]))

    service.copy_balances_from_previous_month("June", 2026)

    assert len(current.batch_updates) == 1
    updates = current.batch_updates[0]
    assert len(updates) == 3
    assert [u["range"] for u in updates] == ["B56:B56", constants.PERSONAL_ACCOUNT_SHEET_PREVIOUS_BALANCE_RANGE, "AS3:AT3"]
    assert list(current.updated_acells) == ["AG37"]
    assert previous.batch_updates == []


def test_copy_balances_reports_unplaced_person_when_no_fl_slot_is_free():
    # v2 contract: a departed person with a non-zero balance is chased to an FL
    # slot; when none is free the copy still completes and reports them as
    # unplaced instead of silently dropping the balance.
    previous, current = _copy_balances_sheets(
        [["346", "Julia"], ["347", "Johannes"]], [[100.0], [200.0]], [["346", "Julia"]]
    )
    service = build_service(FakeSpreadsheet([previous, current]))

    report = service.copy_balances_from_previous_month("June", 2026)

    updates = current.batch_updates[0]
    assert updates[0] == {"range": "B56:B56", "values": [["Julia"]]}
    assert updates[1]["values"] == [[100.0]]
    assert report.unplaced == [("Johannes", 200.0)]
    assert report.chased == []


def test_copy_balances_does_not_duplicate_a_person_when_filling_blanks():
    # v2 contract: the fill step never places the same person twice — the first
    # blank row (top-down) gets them, later rows whose previous occupant is
    # already on the sheet stay empty. Duplicate previous rows: last balance wins.
    previous, current = _copy_balances_sheets(
        [["346", "Julia"], ["347", "Julia"]], [[100.0], [200.0]], [["346", ""], ["347", ""]]
    )
    service = build_service(FakeSpreadsheet([previous, current]))

    service.copy_balances_from_previous_month("June", 2026)

    updates = current.batch_updates[0]
    assert updates[0]["values"] == [["Julia"], [""]]
    assert updates[1]["values"] == [[200.0], [0.0]]


def test_copy_balances_matches_balances_by_normalized_name_but_writes_raw_name():
    previous, current = _copy_balances_sheets([["346", "  Julia  Marie "]], [[150.0]], [["346", ""]])
    service = build_service(FakeSpreadsheet([previous, current]))

    service.copy_balances_from_previous_month("June", 2026)

    updates = current.batch_updates[0]
    assert updates[0]["values"] == [["Julia  Marie"]]
    assert updates[1]["values"] == [[150.0]]


def test_copy_balances_resolves_sheet_names_case_insensitively():
    previous, current = _copy_balances_sheets(
        [["346", "Julia"]], [[100.0]], [["346", "Julia"]], previous_name="MAY 2026", current_name="JUNE 2026"
    )
    service = build_service(FakeSpreadsheet([previous, current]))

    service.copy_balances_from_previous_month("June", 2026)

    assert current.batch_updates, "case-insensitive sheet resolution should find 'JUNE 2026'"


def test_copy_balances_formats_negative_account_value_without_thousands_separator():
    previous, current = _copy_balances_sheets([["346", "Julia"]], [[100.0]], [["346", "Julia"]])
    previous.set_batch_get("AG37", [["-1.234,56 kr"]])
    service = build_service(FakeSpreadsheet([previous, current]))

    service.copy_balances_from_previous_month("June", 2026)

    assert current.updated_acells["AG37"] == "=-1234,56+sum(AG44:AG55)"


def test_copy_balances_blank_current_labels_get_blank_name_and_zero_balance():
    previous, current = _copy_balances_sheets([["346", "Julia"]], [[100.0]], [["346", ""], ["", ""]])
    service = build_service(FakeSpreadsheet([previous, current]))

    service.copy_balances_from_previous_month("June", 2026)

    updates = current.batch_updates[0]
    assert updates[0]["values"] == [["Julia"], [""]]
    assert updates[1]["values"] == [[100.0], [0.0]]


def test_copy_balances_rejects_unknown_month_name():
    service = build_service(FakeSpreadsheet([]))

    with pytest.raises(ValueError, match="Unknown month name"):
        service.copy_balances_from_previous_month("Notamonth", 2026)


# --- v2 copy-balances contract (approved 2026-08-05): failing until implemented ---


def test_copy_balances_chases_departed_balance_into_highest_free_fl():
    previous, current = _copy_balances_sheets(
        [["346", "Julia"]], [[100.0]], [["346", "Kasper"], ["FL4", ""], ["FL5", ""]]
    )
    service = build_service(FakeSpreadsheet([previous, current]))

    report = service.copy_balances_from_previous_month("June", 2026)

    updates = current.batch_updates[0]
    assert updates[0]["values"] == [["Kasper"], [""], ["Julia"]]
    assert updates[1]["values"] == [[0.0], [0.0], [100.0]]
    assert report.chased == [("Julia", 100.0, "FL5")]
    assert report.unplaced == []


def test_copy_balances_chase_fills_fl5_then_fl4_in_previous_row_order():
    previous, current = _copy_balances_sheets(
        [["346", "Julia"], ["347", "Johannes"]],
        [[100.0], [200.0]],
        [["346", "New1"], ["347", "New2"], ["FL4", ""], ["FL5", ""]],
    )
    service = build_service(FakeSpreadsheet([previous, current]))

    report = service.copy_balances_from_previous_month("June", 2026)

    updates = current.batch_updates[0]
    assert updates[0]["values"] == [["New1"], ["New2"], ["Johannes"], ["Julia"]]
    assert updates[1]["values"] == [[0.0], [0.0], [200.0], [100.0]]
    assert report.chased == [("Julia", 100.0, "FL5"), ("Johannes", 200.0, "FL4")]


def test_copy_balances_does_not_chase_zero_balance_departures():
    previous, current = _copy_balances_sheets(
        [["346", "Julia"]], [[0.0]], [["346", "Kasper"], ["FL5", ""]]
    )
    service = build_service(FakeSpreadsheet([previous, current]))

    report = service.copy_balances_from_previous_month("June", 2026)

    updates = current.batch_updates[0]
    assert updates[0]["values"] == [["Kasper"], [""]]
    assert updates[1]["values"] == [[0.0], [0.0]]
    assert report.chased == []
    assert report.unplaced == []


def test_copy_balances_respects_deliberate_moves_and_does_not_refill_old_room():
    # Julia was deliberately moved to 347 on the new sheet before the copy ran.
    # Her old room must NOT be refilled with her, and her balance follows her.
    previous, current = _copy_balances_sheets(
        [["346", "Julia"], ["347", ""]], [[100.0], [0.0]], [["346", ""], ["347", "Julia"]]
    )
    service = build_service(FakeSpreadsheet([previous, current]))

    report = service.copy_balances_from_previous_month("June", 2026)

    updates = current.batch_updates[0]
    assert updates[0]["values"] == [[""], ["Julia"]]
    assert updates[1]["values"] == [[0.0], [100.0]]
    assert report.chased == []
    assert report.unplaced == []


def test_copy_balances_flags_suspected_rename_when_departed_occupant_left_a_balance():
    previous, current = _copy_balances_sheets(
        [["346", "Julia"]], [["-75,00 kr"]], [["346", "Juliaa"], ["FL5", ""]]
    )
    service = build_service(FakeSpreadsheet([previous, current]))

    report = service.copy_balances_from_previous_month("June", 2026)

    updates = current.batch_updates[0]
    assert updates[0]["values"] == [["Juliaa"], ["Julia"]]
    assert updates[1]["values"] == [[0.0], [-75.0]]
    assert report.suspected_renames == [("346", "Julia", "Juliaa")]
    assert report.chased == [("Julia", -75.0, "FL5")]


def test_copy_balances_flags_duplicate_current_names_and_gives_each_row_the_balance():
    previous, current = _copy_balances_sheets(
        [["346", "Julia"]], [[100.0]], [["346", "Julia"], ["347", "Julia"]]
    )
    service = build_service(FakeSpreadsheet([previous, current]))

    report = service.copy_balances_from_previous_month("June", 2026)

    updates = current.batch_updates[0]
    assert updates[0]["values"] == [["Julia"], ["Julia"]]
    assert updates[1]["values"] == [[100.0], [100.0]]
    assert report.duplicate_names == ["Julia"]


def test_copy_balances_returns_empty_report_when_nothing_needs_attention():
    previous, current = _copy_balances_sheets(
        [["346", "Julia"]], [[100.0]], [["346", "Julia"]]
    )
    service = build_service(FakeSpreadsheet([previous, current]))

    report = service.copy_balances_from_previous_month("June", 2026)

    assert report.chased == []
    assert report.unplaced == []
    assert report.suspected_renames == []
    assert report.duplicate_names == []


def test_copy_balances_carries_spotify_by_label_outside_person_logic():
    # Spotify is accounting-only: its name and balance carry forward by label
    # exactly as v1 did — overwritten from the previous sheet's Spotify row —
    # and it never participates in chasing, rename or duplicate detection.
    previous, current = _copy_balances_sheets(
        [["346", "Julia"], ["Spotify", "Daniel Vorting"]],
        [[100.0], [50.0]],
        [["346", "Kasper"], ["FL5", ""], ["Spotify", "Edited By Hand"]],
    )
    service = build_service(FakeSpreadsheet([previous, current]))

    report = service.copy_balances_from_previous_month("June", 2026)

    updates = current.batch_updates[0]
    assert updates[0]["values"] == [["Kasper"], ["Julia"], ["Daniel Vorting"]]
    assert updates[1]["values"] == [[0.0], [100.0], [50.0]]
    # Daniel Vorting is not chased, not a rename suspect, not a duplicate.
    assert report.chased == [("Julia", 100.0, "FL5")]
    assert report.unplaced == []
    assert report.suspected_renames == [("346", "Julia", "Kasper")]
    assert report.duplicate_names == []


def test_copy_balances_never_chases_into_or_blanks_the_spotify_row():
    # Even with no free FL slot, a departed balance must not land on Spotify,
    # and a Spotify row with no previous counterpart is left blank, not chased.
    previous, current = _copy_balances_sheets(
        [["346", "Julia"]],
        [[100.0]],
        [["346", "Kasper"], ["Spotify", "Daniel Vorting"]],
    )
    service = build_service(FakeSpreadsheet([previous, current]))

    report = service.copy_balances_from_previous_month("June", 2026)

    updates = current.batch_updates[0]
    assert updates[0]["values"] == [["Kasper"], [""]]
    assert updates[1]["values"] == [[0.0], [0.0]]
    assert report.unplaced == [("Julia", 100.0)]


def test_delete_fl_person_auto_checks_previous_month_and_refuses_leftover_tab():
    previous = FakeWorksheet("May 2026")
    previous.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, [["FL1", "Gustav"]])
    previous.set_batch_get(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, [[-50.0]])

    current = FakeWorksheet("June 2026")
    current.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, [["FL1", "Gustav"]])
    current.set_batch_get(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, [[0.0]])
    service = build_service(FakeSpreadsheet([previous, current]))

    with pytest.raises(ValueError, match=r"May 2026 balance is -50.00 DKK"):
        service.delete_fl_person("June 2026", "Gustav")

    assert current.batch_updates == []


def test_delete_fl_person_allows_when_both_months_are_zero():
    previous = FakeWorksheet("May 2026")
    previous.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, [["FL1", "Gustav"]])
    previous.set_batch_get(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, [[0.0]])

    current = FakeWorksheet("June 2026")
    current.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, [["FL1", "Gustav"]])
    current.set_batch_get(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, [[0.0]])
    service = build_service(FakeSpreadsheet([previous, current]))

    service.delete_fl_person("June 2026", "Gustav")

    assert current.batch_updates == [[{"range": "B56", "values": [[""]]}, {"range": "I56", "values": [[0.0]]}]]


def test_delete_fl_person_allows_when_person_absent_from_previous_month():
    previous = FakeWorksheet("May 2026")
    previous.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, [["346", "Julia"]])
    previous.set_batch_get(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, [[999.0]])

    current = FakeWorksheet("June 2026")
    current.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, [["FL1", "Gustav"]])
    current.set_batch_get(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, [[0.0]])
    service = build_service(FakeSpreadsheet([previous, current]))

    service.delete_fl_person("June 2026", "Gustav")

    assert len(current.batch_updates) == 1


# --- Sheet integrity check (3b prep): failing until implemented ---


# The signup header as the sheet has it now: LUKKET became FL4 and FL5 was added.
SIGNUP_HEADER = [[
    "346", "347", "348", "349", "350", "351", "352", "353", "354", "355",
    "356", "357", "358", "359", "360", "FL1", "FL2", "FL3", "FL4", "FL5",
]]


def _integrity_worksheet(
    labels,
    formulas,
    *,
    title="June 2026",
    header_row=constants.PERSONAL_ACCOUNT_TABLE_START_ROW - 1,
    signup=None,
    account_formula="=100,00+SUM(AG44:AG55)",
    metadata=None,
):
    """A month sheet that passes every integrity check unless a caller breaks one."""
    ws = FakeWorksheet(title)
    ws.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, labels)
    ws.set_batch_get_formulas(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, formulas)

    search_start = int(constants.PERSONAL_ACCOUNT_HEADER_SEARCH_RANGE.split(":")[0][1:])
    header_rows = [["", ""] for _ in range(header_row - search_start)] + [["Værelse", "Navn"]]
    ws.set_batch_get(constants.PERSONAL_ACCOUNT_HEADER_SEARCH_RANGE, header_rows)

    if signup is None:
        signup = [str(row[0]) for row in labels if str(row[0]).strip()]
    ws.set_batch_get(constants.DAY_SHEET_SIGNUP_HEADER_RANGE, [signup])
    ws.set_batch_get_formulas(constants.PERSONAL_ACCOUNT_SHEET_ACCOUNT_CELL, [[account_formula]])
    ws.set_batch_get(constants.MONTH_METADATA_RANGE, metadata if metadata is not None else [[6, 2026]])
    return ws


def test_check_month_sheet_integrity_flags_account_rows_without_closing_formula():
    ws = _integrity_worksheet(
        [["346", "Julia"], ["FL4", ""], ["Spotify", "Daniel"]],
        [["=sum(F56:X56)"], [""], ["=sum(F58:X58)"]],
    )
    service = build_service(FakeSpreadsheet([ws]))

    problems = service.check_month_sheet_integrity("June 2026")

    assert problems == [
        "June 2026: account row FL4 has no closing-balance formula in Z57 — "
        "balances on this row read as 0 and vanish at the next rollover."
    ]


def test_check_month_sheet_integrity_passes_clean_sheet_and_skips_blank_labels():
    ws = _integrity_worksheet(
        [["346", "Julia"], ["", ""], ["FL5", ""]],
        [["=sum(F56:X56)"], [""], ["=sum(F58:X58)"]],
        signup=["346", "", "FL5"],
    )
    service = build_service(FakeSpreadsheet([ws]))

    assert service.check_month_sheet_integrity("June 2026") == []


def test_check_month_sheet_integrity_flags_a_moved_account_table():
    # The Andet block growing by eleven rows is exactly this failure.
    ws = _integrity_worksheet(
        [["346", "Julia"]],
        [["=sum(F56:X56)"]],
        header_row=constants.PERSONAL_ACCOUNT_TABLE_START_ROW + 4,
    )
    service = build_service(FakeSpreadsheet([ws]))

    problems = service.check_month_sheet_integrity("June 2026")

    assert len(problems) == 1
    assert "the account table starts at row" in problems[0]
    assert constants.PERSONAL_ACCOUNT_TABLE_RANGE in problems[0]


def test_check_month_sheet_integrity_flags_a_missing_account_header():
    ws = _integrity_worksheet([["346", "Julia"]], [["=sum(F56:X56)"]])
    ws.set_batch_get(constants.PERSONAL_ACCOUNT_HEADER_SEARCH_RANGE, [["", ""]])
    service = build_service(FakeSpreadsheet([ws]))

    problems = service.check_month_sheet_integrity("June 2026")

    assert len(problems) == 1
    assert "was not found" in problems[0]


def test_check_month_sheet_integrity_flags_signup_columns_out_of_order():
    ws = _integrity_worksheet(
        [["346", "Julia"], ["347", "Johannes"]],
        [["=sum(F56:X56)"], ["=sum(F57:X57)"]],
        signup=["346", "348"],
    )
    service = build_service(FakeSpreadsheet([ws]))

    problems = service.check_month_sheet_integrity("June 2026")

    assert len(problems) == 1
    assert "signup column 2 is '348'" in problems[0]
    assert "meal costs land on the wrong person" in problems[0]


def test_check_month_sheet_integrity_flags_typed_account_total():
    ws = _integrity_worksheet([["346", "Julia"]], [["=sum(F56:X56)"]], account_formula="11407,72")
    service = build_service(FakeSpreadsheet([ws]))

    problems = service.check_month_sheet_integrity("June 2026")

    assert len(problems) == 1
    assert constants.PERSONAL_ACCOUNT_SHEET_ACCOUNT_CELL in problems[0]


def test_check_month_sheet_integrity_flags_month_metadata_from_the_template():
    # A sheet duplicated from Skabelon keeps the template's month until someone
    # copies balances into it, and then every weekday in column B is wrong.
    ws = _integrity_worksheet([["346", "Julia"]], [["=sum(F56:X56)"]], metadata=[[2, 2025]])
    service = build_service(FakeSpreadsheet([ws]))

    problems = service.check_month_sheet_integrity("June 2026")

    assert len(problems) == 1
    assert "month 2 of 2025" in problems[0]


def test_check_month_sheet_integrity_flags_empty_month_metadata():
    ws = _integrity_worksheet([["346", "Julia"]], [["=sum(F56:X56)"]], metadata=[["", ""]])
    service = build_service(FakeSpreadsheet([ws]))

    problems = service.check_month_sheet_integrity("June 2026")

    assert len(problems) == 1
    assert constants.MONTH_METADATA_RANGE in problems[0]


def _occupancy_sheet(rows, balances, cells=(), with_log=True):
    ws = FakeWorksheet("June 2026")
    ws.set_batch_get(constants.PERSONAL_ACCOUNT_TABLE_RANGE, rows)
    ws.set_batch_get(constants.PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE, balances)
    ws.set_batch_get(constants.DAY_SHEET_SIGNUP_HEADER_RANGE, SIGNUP_HEADER)
    for row, col, value in cells:
        ws.set_cell(row, col, value)
    sheets = [ws]
    log_ws = None
    if with_log:
        log_ws = FakeWorksheet("Log")
        log_ws.set_all_values([list(constants.LOG_HEADERS)])
        sheets.append(log_ws)
    return ws, log_ws, build_service(FakeSpreadsheet(sheets))


def _logged_rows(log_ws):
    return [row for batch in log_ws.appended_rows for row in batch]


def test_add_person_as_fl_parks_arrival_in_lowest_signup_capable_slot_and_logs():
    ws, log_ws, service = _occupancy_sheet(
        [["FL1", "Gustav"], ["FL2", ""], ["FL3", ""], ["FL4", ""], ["FL5", ""]],
        [[0.0], [0.0], [0.0], [0.0], [0.0]],
    )

    fl_label = service.add_person_as_fl("June 2026", "Kasper", intended_room="348")

    assert fl_label == "FL2"
    assert ws.batch_updates == [[{"range": "B57", "values": [["Kasper"]]}, {"range": "I57", "values": [[0.0]]}]]
    rows = _logged_rows(log_ws)
    assert len(rows) == 1
    assert rows[0][1] == "parked_fl"
    assert rows[0][3] != ""  # action id
    assert rows[0][4] == "June 2026"
    assert rows[0][6] == "Kasper"
    assert rows[0][8] == "FL2"
    assert rows[0][10] == "348"


def test_add_person_as_fl_uses_fl4_now_that_it_can_sign_up():
    # FL4 and FL5 gained signup columns when LUKKET was replaced, so an arrival
    # no longer runs out of room once FL1-FL3 are taken.
    ws, log_ws, service = _occupancy_sheet(
        [["FL1", "Gustav"], ["FL2", "Astrid"], ["FL3", "Esther"], ["FL4", ""], ["FL5", ""]],
        [[0.0], [0.0], [0.0], [0.0], [0.0]],
    )

    assert service.add_person_as_fl("June 2026", "Kasper") == "FL4"


def test_add_person_as_fl_distinguishes_missing_signup_capable_slot():
    # A sheet whose signup header does not reach the free slot: the person
    # would have an account but no way to sign up for dinner.
    ws, log_ws, service = _occupancy_sheet(
        [["FL1", "Gustav"], ["FL2", "Astrid"], ["FL3", "Esther"], ["FL4", ""], ["FL5", ""]],
        [[0.0], [0.0], [0.0], [0.0], [0.0]],
    )
    ws.set_batch_get(constants.DAY_SHEET_SIGNUP_HEADER_RANGE, [["FL1", "FL2", "FL3"]])

    with pytest.raises(ValueError, match="signup-capable"):
        service.add_person_as_fl("June 2026", "Kasper")

    assert ws.batch_updates == []


def test_add_person_as_fl_reports_when_no_slot_free_at_all():
    ws, log_ws, service = _occupancy_sheet(
        [["FL1", "A"], ["FL2", "B"], ["FL3", "C"], ["FL4", "D"], ["FL5", "E"]],
        [[0.0]] * 5,
    )

    with pytest.raises(ValueError, match="No FL slot is free at all"):
        service.add_person_as_fl("June 2026", "Kasper")


def test_move_person_out_parks_debtor_in_highest_free_fl_and_logs():
    ws, log_ws, service = _occupancy_sheet(
        [["346", "Julia"], ["FL4", ""], ["FL5", ""]],
        [[-150.0], [0.0], [0.0]],
        cells=[(56, 9, "-75,00 kr")],
    )

    fl_label = service.move_person_out("June 2026", "346")

    assert fl_label == "FL5"
    assert ws.batch_updates == [
        [
            {"range": "B56", "values": [[""]]},
            {"range": "I56", "values": [[0.0]]},
            {"range": "B58", "values": [["Julia"]]},
            {"range": "I58", "values": [[-75.0]]},
        ]
    ]
    rows = _logged_rows(log_ws)
    assert len(rows) == 1
    assert rows[0][1] == "moved_out"
    assert rows[0][6] == "Julia"
    assert rows[0][7] == "346"
    assert rows[0][8] == "FL5"
    assert rows[0][9] == -75.0


def test_move_person_out_with_zero_tab_just_clears_the_room():
    ws, log_ws, service = _occupancy_sheet(
        [["346", "Julia"], ["FL5", ""]],
        [[0.0], [0.0]],
        cells=[(56, 9, 0.0)],
    )

    fl_label = service.move_person_out("June 2026", "346")

    assert fl_label == ""
    assert ws.batch_updates == [[{"range": "B56", "values": [[""]]}, {"range": "I56", "values": [[0.0]]}]]
    rows = _logged_rows(log_ws)
    assert rows[0][1] == "moved_out"
    assert rows[0][8] == ""


def test_move_person_out_raises_when_no_fl_slot_free():
    ws, log_ws, service = _occupancy_sheet(
        [["346", "Julia"], ["FL5", "Gustav"]],
        [[-150.0], [0.0]],
        cells=[(56, 9, "-75,00 kr")],
    )

    with pytest.raises(ValueError, match="No FL slot is free at all"):
        service.move_person_out("June 2026", "346")

    assert ws.batch_updates == []


def test_move_person_between_accounts_logs_swap_rows_with_shared_action_id():
    ws, log_ws, service = _occupancy_sheet(
        [["346", "Julia"], ["347", "Johannes"]],
        [[0.0], [0.0]],
        cells=[(56, 9, -75.0), (57, 9, 100.0)],
    )

    service.move_person_between_accounts("June 2026", "346", "347")

    rows = _logged_rows(log_ws)
    assert [row[1] for row in rows] == ["moved", "moved"]
    assert rows[0][3] == rows[1][3] != ""
    assert rows[0][4] == rows[1][4] == "June 2026"
    assert {rows[0][6], rows[1][6]} == {"Julia", "Johannes"}


def test_delete_fl_person_logs_deleted_row():
    ws, log_ws, service = _occupancy_sheet(
        [["FL1", "Gustav"]],
        [[0.0]],
    )

    service.delete_fl_person("June 2026", "Gustav")

    rows = _logged_rows(log_ws)
    assert len(rows) == 1
    assert rows[0][1] == "deleted"
    assert rows[0][6] == "Gustav"
    assert rows[0][7] == "FL1"


def test_replace_room_person_logs_moved_in_and_moved_out_pair():
    ws, log_ws, service = _occupancy_sheet(
        [["346", "Julia"], ["FL4", ""], ["FL5", ""]],
        [[100.0], [0.0], [0.0]],
        cells=[(56, 9, 100.0)],
    )

    fl_label = service.replace_room_person("June 2026", "346", "Kasper")

    assert fl_label == "FL5"  # departing person goes to the HIGHEST free slot
    rows = _logged_rows(log_ws)
    assert [row[1] for row in rows] == ["moved_in", "moved_out"]
    assert rows[0][3] == rows[1][3] != ""
    assert rows[0][6] == "Kasper" and rows[0][8] == "346"
    assert rows[1][6] == "Julia" and rows[1][7] == "346" and rows[1][8] == "FL5"


def test_occupancy_actions_succeed_when_log_sheet_is_missing():
    ws, _, service = _occupancy_sheet(
        [["346", "Julia"], ["FL5", ""]],
        [[-150.0], [0.0]],
        cells=[(56, 9, -75.0)],
        with_log=False,
    )

    fl_label = service.move_person_out("June 2026", "346")

    assert fl_label == "FL5"
    assert len(ws.batch_updates) == 1
