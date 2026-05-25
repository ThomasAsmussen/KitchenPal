from types import SimpleNamespace

import pytest

from kitchenpal import constants
from kitchenpal.sheets_service import PlanningEntry, RoomEntry, SheetsService


def set_room_directory(ws):
    ws.set_batch_get(
        "I2:AA2",
        [["346", "347", "348", "349", "350", "351", "352", "353", "354", "355", "356", "357", "358", "359", "360", "FL1", "FL2", "FL3", "LUKKET"]],
    )
    ws.set_batch_get(
        "A45:B65",
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

    def set_cell(self, row, col, value):
        self._cells[(row, col)] = value

    def set_batch_get(self, range_name, value):
        self._batch_get[range_name] = value

    def set_all_values(self, value):
        self._all_values = value

    def cell(self, row, col):
        return SimpleNamespace(value=self._cells.get((row, col)))

    def update_cell(self, row, col, value):
        self.updated_cells.append((row, col, value))
        self._cells[(row, col)] = value

    def batch_get(self, ranges):
        self.batch_get_calls.append(list(ranges))
        return [self._batch_get[r] for r in ranges]

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


def test_add_transaction_writes_first_empty_row():
    ws = FakeWorksheet("October 2024")
    ws.set_batch_get("AC44:AC55", [["filled"], ["filled"], [], ["filled"]])

    service = build_service(FakeSpreadsheet([ws]))
    service.add_transaction("October 2024", 350, "Payment to kitchen fund", 125.5, __import__("datetime").date(2026, 4, 24))

    assert len(ws.batch_updates) == 1
    updates = ws.batch_updates[0]
    assert updates[0]["range"] == "AC46:AE46"
    assert updates[1]["range"] == "AG46"


def test_add_transaction_raises_when_no_empty_row():
    ws = FakeWorksheet("October 2024")
    ws.set_batch_get("AC44:AC55", [["x"] for _ in range(12)])

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
        "AI3:AK21",
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
        "AC3:AG43",
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
        "AC44:AG200",
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
        "AI3:AK21",
        [
            [346, 46, None],
            ["FL1", None, 1],
        ],
    )
    ws.set_batch_get(
        "AC3:AG43",
        [
            ["Værelse", "Dato", "Vare", None, "Beløb"],
            [352, __import__("datetime").datetime(2026, 5, 3), "Banankage", None, "42,00 kr"],
        ],
    )
    ws.set_batch_get(
        "AC44:AG200",
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

    assert ws.batch_get_calls == [["AI3:AK21", "AC3:AG43", "AC44:AG200"]]
    assert [entry.name for entry in entries.drinks] == ["Julia", "Gustav"]
    assert [entry.item for entry in entries.purchases] == ["Banankage"]
    assert [entry.room for entry in entries.transactions] == ["FL2"]


def test_get_transaction_payout_marks_amount_negative():
    ws = FakeWorksheet("October 2024")
    # empty lookup so add_transaction writes to first lookup row
    ws.set_batch_get("AC44:AC55", [[], ["x"], ["x"]])

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
        "AI3:AK21",
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


def test_create_month_sheet_duplicates_template_sheet():
    template = FakeWorksheet("Template", worksheet_id=999)
    other = FakeWorksheet("October 2024")
    spreadsheet = FakeSpreadsheet([template, other])
    service = build_service(spreadsheet)

    service.create_month_sheet("November", 2026)
    assert spreadsheet.duplicate_calls == [(999, "November 2026")]


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
        "A45:B65",
        [
            ["346", "Julia"],
            ["347", "Johannes"],
            ["348", "Alberte"],
            ["349", "Thomas"],
        ],
    )
    previous.set_batch_get("Z45:Z65", [["1.234,50 kr"], ["Beløb"], [500], ["0,00 kr"]])
    previous.set_batch_get("AG37", [["2.000,00 kr"]])

    current = FakeWorksheet("May 2026")
    current.set_batch_get(
        "A45:B65",
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

    assert updates[0]["range"] == "I45:I65"
    assert updates[0]["values"] == [[1234.5], [0.0], [500.0], [0.0]]
    assert updates[1]["range"] == "AR3:AS3"
    assert updates[1]["values"] == [[5, 2026]]
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
    previous.set_batch_get("A45:B65", [["346", "Julia"], ["347", "Johannes"]])
    previous.set_batch_get("Z45:Z65", [["1.234,50 kr"], ["0,00 kr"]])
    previous.set_batch_get("AG37", [["2.000,00 kr"]])

    current = FakeWorksheet("Juni 2026")
    current.set_batch_get("A45:B65", [["346", "Julia"], ["347", "Johannes"]])
    service = build_service(FakeSpreadsheet([previous, current]))

    service.copy_balances_from_previous_month("Juni", 2026)

    assert len(current.batch_updates) == 1
    updates = current.batch_updates[0]
    assert updates[0]["range"] == "I45:I65"
    assert updates[0]["values"] == [[1234.5], [0.0]]
    assert updates[1]["range"] == "AR3:AS3"
    assert updates[1]["values"] == [[6, 2026]]
    assert current.updated_acells["AG37"] == "=2000,00+sum(AG44:AG55)"


def test_copy_balances_from_previous_month_moves_balances_by_person_name():
    previous = FakeWorksheet("May 2026")
    previous.set_batch_get(
        "A45:B65",
        [
            ["346", "Julia"],
            ["347", "Johannes"],
            ["FL1", "Gustav"],
        ],
    )
    previous.set_batch_get("Z45:Z65", [[100.0], [200.0], [300.0]])
    previous.set_batch_get("AG37", [["2.000,00 kr"]])

    current = FakeWorksheet("June 2026")
    current.set_batch_get(
        "A45:B65",
        [
            ["346", "Gustav"],
            ["347", "Johannes"],
            ["FL1", "Julia"],
            ["FL2", "New Person"],
        ],
    )
    service = build_service(FakeSpreadsheet([previous, current]))

    service.copy_balances_from_previous_month("June", 2026)

    updates = current.batch_updates[0]
    assert updates[0]["range"] == "I45:I65"
    assert updates[0]["values"] == [[300.0], [200.0], [100.0], [0.0]]


def test_copy_balances_from_previous_month_requires_account_value():
    previous = FakeWorksheet("May 2026")
    previous.set_batch_get("A45:B65", [["346", "Julia"]])
    previous.set_batch_get("Z45:Z65", [["100,00 kr"]])
    previous.set_batch_get("AG37", [])

    current = FakeWorksheet("June 2026")
    current.set_batch_get("A45:B65", [["346", "Julia"]])
    service = build_service(FakeSpreadsheet([previous, current]))

    with pytest.raises(ValueError, match=r"Expected a value in May 2026!AG37"):
        service.copy_balances_from_previous_month("June", 2026)

    assert current.batch_updates == []
    assert current.updated_acells == {}


def test_add_person_as_fl_uses_first_available_fl_spot():
    ws = FakeWorksheet("June 2026")
    ws.set_batch_get(
        "A45:B65",
        [["346", "Julia"], ["FL1", "Gustav"], ["FL2", ""], ["FL3", ""]],
    )
    ws.set_batch_get("Z45:Z65", [[100.0], [0.0], [0.0], [0.0]])
    service = build_service(FakeSpreadsheet([ws]))

    fl_label = service.add_person_as_fl("June 2026", "New Person")

    assert fl_label == "FL2"
    assert ws.batch_updates == [[{"range": "B47", "values": [["New Person"]]}, {"range": "I47", "values": [[0.0]]}]]


def test_replace_room_person_moves_replaced_person_to_first_available_fl():
    ws = FakeWorksheet("June 2026")
    ws.set_batch_get(
        "A45:B65",
        [["346", "Julia"], ["347", "Johannes"], ["FL1", ""], ["FL2", "Gustav"]],
    )
    ws.set_batch_get("Z45:Z65", [[100.0], [200.0], [0.0], [300.0]])
    ws.set_cell(45, 9, 100.0)
    ws.set_cell(47, 9, "")
    service = build_service(FakeSpreadsheet([ws]))

    fl_label = service.replace_room_person("June 2026", "346", "New Person")

    assert fl_label == "FL1"
    assert ws.batch_updates == [
        [
            {"range": "B45", "values": [["New Person"]]},
            {"range": "I45", "values": [[0.0]]},
            {"range": "B47", "values": [["Julia"]]},
            {"range": "I47", "values": [[100.0]]},
        ]
    ]


def test_replace_room_person_moves_existing_fl_person_into_room():
    ws = FakeWorksheet("June 2026")
    ws.set_batch_get(
        "A45:B65",
        [["346", "Julia"], ["347", "Johannes"], ["FL1", "Gustav"], ["FL2", ""]],
    )
    ws.set_batch_get("Z45:Z65", [[100.0], [200.0], [300.0], [0.0]])
    ws.set_cell(45, 9, 100.0)
    ws.set_cell(47, 9, 300.0)
    service = build_service(FakeSpreadsheet([ws]))

    fl_label = service.replace_room_person("June 2026", "346", "Gustav")

    assert fl_label == "FL1"
    assert ws.batch_updates == [
        [
            {"range": "B45", "values": [["Gustav"]]},
            {"range": "I45", "values": [[300.0]]},
            {"range": "B47", "values": [["Julia"]]},
            {"range": "I47", "values": [[100.0]]},
        ]
    ]


def test_delete_fl_person_requires_zero_balance():
    ws = FakeWorksheet("June 2026")
    ws.set_batch_get("A45:B65", [["346", "Julia"], ["FL1", "Gustav"]])
    ws.set_batch_get("Z45:Z65", [[0.0], [50.0]])
    service = build_service(FakeSpreadsheet([ws]))

    with pytest.raises(ValueError, match="balance is 50.00 DKK"):
        service.delete_fl_person("June 2026", "Gustav")

    assert ws.updated_cells == []


def test_delete_fl_person_clears_name_when_balance_is_zero():
    ws = FakeWorksheet("June 2026")
    ws.set_batch_get("A45:B65", [["346", "Julia"], ["FL1", "Gustav"]])
    ws.set_batch_get("Z45:Z65", [[0.0], [0.0]])
    service = build_service(FakeSpreadsheet([ws]))

    service.delete_fl_person("June 2026", "Gustav")

    assert ws.batch_updates == [[{"range": "B46", "values": [[""]]}, {"range": "I46", "values": [[0.0]]}]]


def test_delete_fl_person_checks_previous_month_balance_when_provided():
    previous = FakeWorksheet("May 2026")
    previous.set_batch_get("A45:B65", [["FL1", "Gustav"]])
    previous.set_batch_get("Z45:Z65", [[50.0]])

    current = FakeWorksheet("June 2026")
    current.set_batch_get("A45:B65", [["FL1", "Gustav"]])
    current.set_batch_get("Z45:Z65", [[0.0]])

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
