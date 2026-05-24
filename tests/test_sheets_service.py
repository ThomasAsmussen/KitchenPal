from types import SimpleNamespace

import pytest

from kitchenpal.sheets_service import SheetsService


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

    def set_cell(self, row, col, value):
        self._cells[(row, col)] = value

    def set_batch_get(self, range_name, value):
        self._batch_get[range_name] = value

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
    ws.set_cell(60, 35, "4")
    ws.set_cell(60, 36, "2")

    service = build_service(FakeSpreadsheet([ws]))
    new_beer, new_wine = service.add_drinks("October 2024", "FL1", 3, 1)

    assert (60, 35, 7) in ws.updated_cells
    assert (60, 36, 3) in ws.updated_cells
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
    assert signed_people == ["Julia", "Alberte"]
    assert ws.batch_get_calls[-1] == ["I5", "J5", "K5"]


def test_add_transaction_writes_first_empty_row():
    ws = FakeWorksheet("October 2024")
    ws.set_batch_get("AB44:AB55", [["filled"], ["filled"], [], ["filled"]])

    service = build_service(FakeSpreadsheet([ws]))
    service.add_transaction("October 2024", 350, "Payment to kitchen fund", 125.5, __import__("datetime").date(2026, 4, 24))

    assert len(ws.batch_updates) == 1
    updates = ws.batch_updates[0]
    assert updates[0]["range"] == "AB46:AD46"
    assert updates[1]["range"] == "AF46"


def test_add_transaction_raises_when_no_empty_row():
    ws = FakeWorksheet("October 2024")
    ws.set_batch_get("AB44:AB55", [["x"] for _ in range(12)])

    service = build_service(FakeSpreadsheet([ws]))
    with pytest.raises(ValueError):
        service.add_transaction("October 2024", 350, "Payment", 1.0, __import__("datetime").date(2026, 4, 24))


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


def test_copy_balances_from_previous_month_updates_expected_ranges():
    previous = FakeWorksheet("April 2026")
    previous.set_batch_get("Y45:Y65", [["1.234,50 kr"], ["500,00 kr"], ["0,00 kr"]])
    previous.set_batch_get("AF37", [["2.000,00 kr"]])

    current = FakeWorksheet("May 2026")
    spreadsheet = FakeSpreadsheet([previous, current])
    service = build_service(spreadsheet)

    service.copy_balances_from_previous_month("May", 2026)

    assert len(current.batch_updates) == 1
    updates = current.batch_updates[0]

    assert updates[0]["range"] == "H45:H65"
    assert updates[0]["values"] == [[1234.5], [500.0], [0.0]]
    assert updates[1]["range"] == "AR3:AS3"
    assert updates[1]["values"] == [[5, 2026]]
    assert current.updated_acells["AF37"] == "=2000,00+sum(AF44:AF55)"


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
