"""Failing tests for the append-only Log sheet (schema approved 2026-08-05).

The Log service does not exist yet; these tests define its contract. See the
"Log sheet schema (append-only)" section in CLAUDE.md.
"""
import pytest

from kitchenpal import constants

from test_sheets_service import FakeSpreadsheet, FakeWorksheet, build_service


EXPECTED_HEADERS = [
    "Timestamp",
    "Event",
    "Summary",
    "Action id",
    "Month sheet",
    "By",
    "Person",
    "From",
    "To",
    "Balance",
    "Room intent",
]


class FixedDatetime:
    @classmethod
    def now(cls, tz=None):
        return cls()

    def strftime(self, fmt):
        return "2026-08-05 21:15:00"


def test_log_constants_pin_sheet_name_and_headers():
    assert constants.LOG_SHEET_NAME == "Log"
    assert constants.LOG_HEADERS == EXPECTED_HEADERS


def test_append_log_entries_appends_rows_at_bottom_in_header_order(monkeypatch):
    from kitchenpal.sheets.log import LogEntry

    monkeypatch.setattr("kitchenpal.sheets.log.datetime", FixedDatetime)

    ws = FakeWorksheet("Log")
    ws.set_all_values([EXPECTED_HEADERS])
    service = build_service(FakeSpreadsheet([ws]))

    service.append_log_entries(
        [
            LogEntry(
                event="moved",
                summary="Julia moved from 346 to 347.",
                action_id="a1b2c3",
                month_sheet="June 2026",
                by="Thomas",
                person="Julia",
                from_label="346",
                to_label="347",
                balance=-75.0,
            ),
            LogEntry(
                event="moved",
                summary="Johannes moved from 347 to 346.",
                action_id="a1b2c3",
                month_sheet="June 2026",
                by="Thomas",
                person="Johannes",
                from_label="347",
                to_label="346",
                balance=100.0,
            ),
        ]
    )

    assert len(ws.appended_rows) == 1
    rows = ws.appended_rows[0]
    assert rows == [
        ["2026-08-05 21:15:00", "moved", "Julia moved from 346 to 347.", "a1b2c3", "June 2026", "Thomas", "Julia", "346", "347", -75.0, ""],
        ["2026-08-05 21:15:00", "moved", "Johannes moved from 347 to 346.", "a1b2c3", "June 2026", "Thomas", "Johannes", "347", "346", 100.0, ""],
    ]


def test_append_log_entries_writes_header_first_when_sheet_is_empty(monkeypatch):
    from kitchenpal.sheets.log import LogEntry

    monkeypatch.setattr("kitchenpal.sheets.log.datetime", FixedDatetime)

    ws = FakeWorksheet("Log")
    service = build_service(FakeSpreadsheet([ws]))

    service.append_log_entries(
        [
            LogEntry(
                event="parked_fl",
                summary="Kasper parked in FL1, waiting for room 348.",
                action_id="d4e5f6",
                month_sheet="June 2026",
                person="Kasper",
                to_label="FL1",
                balance=0.0,
                room_intent="348",
            )
        ]
    )

    all_rows = [row for batch in ws.appended_rows for row in batch]
    assert all_rows[0] == EXPECTED_HEADERS
    assert all_rows[1][:5] == ["2026-08-05 21:15:00", "parked_fl", "Kasper parked in FL1, waiting for room 348.", "d4e5f6", "June 2026"]
    assert all_rows[1][10] == "348"


def test_get_log_entries_returns_newest_first_and_reads_by_header_name():
    ws = FakeWorksheet("Log")
    # A column appended on the right and an unknown event type must not break
    # readers: columns are matched by header name, never by index.
    ws.set_all_values(
        [
            EXPECTED_HEADERS + ["Extra"],
            ["2026-08-01 10:00:00", "moved_out", "Julia moved out of 346.", "x1", "June 2026", "", "Julia", "346", "FL5", "-75", "", "ignored"],
            ["2026-08-02 11:00:00", "future_event", "Something new happened.", "x2", "June 2026", "Gustav", "", "", "", "", "", "ignored"],
        ]
    )
    service = build_service(FakeSpreadsheet([ws]))

    entries = service.get_log_entries()

    assert [entry.event for entry in entries] == ["future_event", "moved_out"]
    assert entries[1].person == "Julia"
    assert entries[1].from_label == "346"
    assert entries[1].to_label == "FL5"
    assert entries[1].month_sheet == "June 2026"
    assert entries[0].by == "Gustav"
    assert entries[0].summary == "Something new happened."
