from datetime import date

import pytest

from kitchenpal import constants
from test_sheets_service import FakeSpreadsheet, FakeWorksheet, build_service


def _meeting_rows(subject=None, author=None):
    rows = [[""] for _ in range(20)]
    if subject is not None:
        rows[9] = ["", subject, "", author or ""]
    return rows


def test_meeting_subjects_use_the_existing_table_columns():
    ws = FakeWorksheet(constants.KITCHEN_MEETINGS_SHEET_NAME)
    ws.set_all_values(_meeting_rows("Repair the freezer", "346"))
    service = build_service(FakeSpreadsheet([ws]))

    subjects = service.get_kitchen_meeting_subjects(today=date(2026, 11, 5))

    assert len(subjects) == 1
    assert subjects[0].row_number == 10
    assert subjects[0].subject == "Repair the freezer"
    assert subjects[0].submitted_by == "346"


def test_meeting_tab_name_lookup_is_case_insensitive():
    ws = FakeWorksheet("Emner Køkkenmøde")
    ws.set_all_values(_meeting_rows("Discuss cleaning", "356"))
    service = build_service(FakeSpreadsheet([ws]))

    subjects = service.get_kitchen_meeting_subjects()

    assert subjects[0].subject == "Discuss cleaning"


def test_add_meeting_subject_writes_subject_and_author_to_the_same_row():
    ws = FakeWorksheet(constants.KITCHEN_MEETINGS_SHEET_NAME)
    ws.set_all_values(_meeting_rows())
    service = build_service(FakeSpreadsheet([ws]))

    entry = service.add_kitchen_meeting_subject("Buy new shelves", "354")

    assert entry.row_number == 10
    assert ws.updated_ranges == [("B10", [["Buy new shelves"]]), ("D10", [["354"]])]


def test_cleanup_clears_only_the_existing_subject_and_author_ranges():
    ws = FakeWorksheet(constants.KITCHEN_MEETINGS_SHEET_NAME)
    ws.set_all_values(_meeting_rows("Old subject", "346"))
    service = build_service(FakeSpreadsheet([ws]))

    service.clear_kitchen_meeting_subjects()

    assert ws.updated_ranges == [
        ("B10:B20", [[""]] * 11),
        ("D10:D20", [[""]] * 11),
    ]


def test_subject_validation_is_explicit():
    ws = FakeWorksheet(constants.KITCHEN_MEETINGS_SHEET_NAME)
    service = build_service(FakeSpreadsheet([ws]))

    with pytest.raises(ValueError, match="subject"):
        service.add_kitchen_meeting_subject("", "346")
    with pytest.raises(ValueError, match="submitted"):
        service.add_kitchen_meeting_subject("Topic", "")
