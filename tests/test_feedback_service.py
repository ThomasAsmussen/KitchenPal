import pytest

from kitchenpal import constants

from test_sheets_service import FakeSpreadsheet, FakeWorksheet, build_service


def test_get_feedback_entries_initializes_blank_sheet():
    ws = FakeWorksheet(constants.NEW_FEATURES_SHEET_NAME)
    service = build_service(FakeSpreadsheet([ws]))

    entries = service.get_feedback_entries("feature")

    assert entries == []
    assert ws.updated_ranges == [(constants.FEEDBACK_HEADER_RANGE, [constants.FEEDBACK_HEADERS])]


def test_get_feedback_entries_reads_existing_rows():
    ws = FakeWorksheet(constants.BUGS_SHEET_NAME)
    ws.set_all_values(
        [
            constants.FEEDBACK_HEADERS,
            ["2026-05-25 14:30", "Julia", "Signup issue", "Cannot sign up for June 3"],
            ["", "", "", ""],
        ]
    )
    service = build_service(FakeSpreadsheet([ws]))

    entries = service.get_feedback_entries("bug")

    assert len(entries) == 1
    assert entries[0].row_number == 2
    assert entries[0].name == "Julia"
    assert entries[0].title == "Signup issue"
    assert entries[0].details == "Cannot sign up for June 3"
    assert entries[0].status == "Open"


def test_add_feedback_entry_adds_header_and_first_row_to_blank_sheet(monkeypatch):
    ws = FakeWorksheet(constants.NEW_FEATURES_SHEET_NAME)
    service = build_service(FakeSpreadsheet([ws]))

    class FixedDatetime:
        @classmethod
        def now(cls):
            return cls()

        def strftime(self, fmt):
            return "2026-05-25 14:30"

    monkeypatch.setattr("kitchenpal.sheets.feedback.datetime", FixedDatetime)

    entry = service.add_feedback_entry("feature", "", "Meal rating", "Let people rate meals")

    assert entry.name == "Anonymous"
    assert entry.status == "Open"
    assert ws.updated_ranges == [
        (constants.FEEDBACK_HEADER_RANGE, [constants.FEEDBACK_HEADERS]),
        ("A2:E2", [["2026-05-25 14:30", "Anonymous", "Meal rating", "Let people rate meals", "Open"]]),
    ]


def test_add_feedback_entry_requires_title_and_details():
    ws = FakeWorksheet(constants.BUGS_SHEET_NAME)
    service = build_service(FakeSpreadsheet([ws]))

    with pytest.raises(ValueError, match="short title"):
        service.add_feedback_entry("bug", "Julia", "", "Details")

    with pytest.raises(ValueError, match="details"):
        service.add_feedback_entry("bug", "Julia", "Title", "")


def test_get_feedback_entries_updates_old_four_column_header():
    ws = FakeWorksheet(constants.NEW_FEATURES_SHEET_NAME)
    ws.set_all_values(
        [
            ["Created At", "Name", "Title", "Details"],
            ["2026-05-25 14:30", "Julia", "Meal rating", "Let people rate meals"],
        ]
    )
    service = build_service(FakeSpreadsheet([ws]))

    entries = service.get_feedback_entries("feature")

    assert entries[0].status == "Open"
    assert ws.updated_ranges == [(constants.FEEDBACK_HEADER_RANGE, [constants.FEEDBACK_HEADERS])]


def test_mark_feedback_entry_done_updates_feature_status():
    ws = FakeWorksheet(constants.NEW_FEATURES_SHEET_NAME)
    service = build_service(FakeSpreadsheet([ws]))

    service.mark_feedback_entry_done("feature", 3)

    assert ws.updated_ranges == [("E3", [["Done"]])]


def test_mark_feedback_entry_done_updates_bug_status_as_fixed():
    ws = FakeWorksheet(constants.BUGS_SHEET_NAME)
    service = build_service(FakeSpreadsheet([ws]))

    service.mark_feedback_entry_done("bug", 4)

    assert ws.updated_ranges == [("E4", [["Fixed"]])]


def test_delete_feedback_entry_clears_row():
    ws = FakeWorksheet(constants.BUGS_SHEET_NAME)
    service = build_service(FakeSpreadsheet([ws]))

    service.delete_feedback_entry("bug", 4)

    assert ws.updated_ranges == [("A4:E4", [["", "", "", "", ""]])]
