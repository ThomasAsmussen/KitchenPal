"""The month turning by itself: what counts as open, and what the turn does."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from kitchenpal.ui import rollover


def _account(label, name="", balance=0.0):
    return SimpleNamespace(label=label, name=name, balance=balance, row_number=56)


def _log(event, month_sheet="", timestamp="2026-09-01 08:00:00", person="", room_intent=""):
    return SimpleNamespace(
        event=event, month_sheet=month_sheet, timestamp=timestamp, person=person,
        room_intent=room_intent, summary="", action_id="", by="", from_label="", to_label="", balance="",
    )


class _Stub:
    def __init__(self, sheets=None, accounts=None, log=None, fail_copy=None):
        self.sheets = list(sheets if sheets is not None else ["August 2026", "September 2026"])
        self.accounts = accounts or {}
        self.log = list(log or [])
        self.fail_copy = fail_copy
        self.created = []
        self.copied = []
        self.logged = []

    def list_sheets(self):
        return list(self.sheets)

    def get_personal_account_entries(self, worksheet_name):
        return list(self.accounts.get(worksheet_name, []))

    def get_room_entries(self, worksheet_name):
        return list(self.accounts.get(worksheet_name, []))

    def get_day_rows(self, worksheet_name, room_entries):
        return []

    def get_log_entries(self):
        return list(self.log)

    def create_month_sheet(self, month_name, year):
        name = f"{month_name} {year}"
        if name in self.sheets:
            raise ValueError(f"A sheet named '{name}' already exists")
        self.created.append(name)
        self.sheets.append(name)

    def copy_balances_from_previous_month(self, month_name, year):
        if self.fail_copy:
            raise ValueError(self.fail_copy)
        self.copied.append((month_name, year))
        return SimpleNamespace(chased=[], unplaced=[], suspected_renames=[], duplicate_names=[])

    def append_log_entries(self, entries):
        self.logged.extend(entries)
        for entry in entries:
            self.log.insert(0, entry)


@pytest.fixture(autouse=True)
def _reset_turn_state():
    rollover._turn_attempts.clear()
    rollover._turn_errors.clear()
    yield
    rollover._turn_attempts.clear()
    rollover._turn_errors.clear()


AUGUST = datetime(2026, 8, 29)
SEPTEMBER = datetime(2026, 9, 2)


def test_a_month_is_open_only_once_the_balances_have_been_carried():
    # A name on the sheet is not proof: a move-in recorded early puts one there
    # weeks before the copy runs.
    service = _Stub(accounts={"September 2026": [_account("352", "Mikkel")]})

    assert rollover.month_status(service, "September", 2026).is_open is False


def test_the_log_row_is_what_makes_it_open():
    service = _Stub(log=[_log("rolled_over", month_sheet="September 2026")])

    status = rollover.month_status(service, "September", 2026)

    assert status.is_open is True
    assert status.turned_at == "2026-09-01 08:00:00"


def test_a_month_opened_before_it_started_is_refreshed_on_the_1st():
    # The copy reads the previous month's LIVE closing column, so opening on the
    # 30th freezes figures August had not finished moving. Two more days of
    # dinners would be lost from the carry if that counted as open.
    service = _Stub(log=[_log("rolled_over", month_sheet="September 2026", timestamp="2026-08-30 09:00:00")])

    status = rollover.month_status(service, "September", 2026)
    assert status.turned_early is True
    assert status.is_open is False

    assert rollover.turn_if_due(service, today=SEPTEMBER) is not None
    assert service.copied == [("September", 2026)]


def test_a_month_opened_on_the_day_it_started_is_open():
    service = _Stub(log=[_log("rolled_over", month_sheet="September 2026", timestamp="2026-09-01 06:12:00")])

    status = rollover.month_status(service, "September", 2026)

    assert status.turned_early is False
    assert status.is_open is True


def test_an_undated_turn_is_taken_at_its_word():
    # A row with no timestamp cannot be judged, and re-copying on every page
    # load would be worse than trusting it.
    service = _Stub(log=[_log("rolled_over", month_sheet="September 2026", timestamp="")])

    assert rollover.month_status(service, "September", 2026).is_open is True


def test_the_first_month_of_all_has_nothing_to_carry():
    service = _Stub(sheets=["August 2026"])

    status = rollover.month_status(service, "August", 2026)

    assert status.nothing_to_carry is True
    assert status.is_open is True


def test_the_turn_creates_nothing_when_the_sheet_is_already_there():
    service = _Stub()

    result = rollover.turn_if_due(service, today=SEPTEMBER)

    assert result is not None
    assert service.created == []
    assert service.copied == [("September", 2026)]
    assert [entry.event for entry in service.logged] == ["rolled_over"]
    assert service.logged[0].by == "automatic"


def test_the_turn_makes_the_sheet_when_it_is_missing():
    service = _Stub(sheets=["August 2026"])

    rollover.turn_if_due(service, today=SEPTEMBER)

    assert service.created == ["September 2026"]
    assert service.copied == [("September", 2026)]


def test_the_turn_does_nothing_once_the_month_is_open():
    service = _Stub(log=[_log("rolled_over", month_sheet="September 2026")])

    assert rollover.turn_if_due(service, today=SEPTEMBER) is None
    assert service.copied == []


class _BrokenLog(_Stub):
    def get_log_entries(self):
        raise RuntimeError("Quota exceeded for reads")


def test_an_unreadable_log_never_triggers_a_turn():
    # This is how one month gets opened five times: a read fails, the app reads
    # "no rolled_over row" as "not open yet", and carries the balances again.
    service = _BrokenLog()

    assert rollover.turn_if_due(service, today=SEPTEMBER) is None
    assert service.copied == []
    assert rollover.month_status(service, "September", 2026).log_unreadable is True


def test_the_automatic_turn_runs_at_most_once_per_month():
    service = _Stub()

    assert rollover.turn_if_due(service, today=SEPTEMBER) is not None
    assert service.copied == [("September", 2026)]

    # Even if the Log write did not take, the app must not keep carrying.
    service.log = []
    assert rollover.turn_if_due(service, today=SEPTEMBER) is None
    assert service.copied == [("September", 2026)]


def test_a_failed_turn_is_remembered_and_not_retried_at_once():
    service = _Stub(fail_copy="Cannot update September 2026: previous month sheet does not exist.")

    assert rollover.turn_if_due(service, today=SEPTEMBER) is None
    assert "previous month sheet" in rollover.month_status(service, "September", 2026).error

    # A second page load a moment later must not hammer the API.
    rollover.turn_if_due(service, today=SEPTEMBER)
    assert rollover._turn_attempts


def test_strays_are_people_who_left_money_behind():
    service = _Stub(
        accounts={
            "August 2026": [
                _account("346", "Julia", -201.0),
                _account("347", "Settled Sam", 0.0),
                _account("348", "Stayer", -50.0),
            ],
            "September 2026": [_account("346", "Mikkel"), _account("348", "Stayer", -50.0)],
        }
    )

    strays = rollover.outstanding_strays(service, "September 2026", "August 2026")

    assert [(item.name, item.balance) for item in strays] == [("Julia", -201.0)]


def test_duplicates_are_named_once_each():
    service = _Stub(accounts={"September 2026": [_account("346", "Julia"), _account("FL1", "julia ")]})

    assert rollover.duplicate_people(service, "September 2026") == ["Julia"]


def test_preparing_and_opening_are_the_same_two_calls_with_different_meanings():
    service = _Stub(sheets=["August 2026"])

    rollover.prepare_month(service, "September", 2026, by="346")

    assert service.created == ["September 2026"]
    assert service.copied == [("September", 2026)]
    assert [entry.event for entry in service.logged] == ["prepared"]
    # Preparing must not make the month look open, or the turn would never run.
    assert rollover.month_status(service, "September", 2026).is_open is False

    rollover.open_month(service, "September", 2026)

    assert service.created == ["September 2026"]
    assert [entry.event for entry in service.logged] == ["prepared", "rolled_over"]
    assert rollover.month_status(service, "September", 2026).is_open is True


def test_only_a_copy_makes_a_sheet_prepared():
    # One name and fourteen empty rooms is the state that needs repairing, so a
    # name can never be the proof — the copy's own Log row is.
    service = _Stub(
        accounts={"September 2026": [_account("346", "William")]},
        log=[_log("prepared", month_sheet="October 2026")],
    )

    assert rollover.is_prepared(service, "September 2026") is False
    assert rollover.is_prepared(service, "October 2026") is True
    assert rollover.is_prepared(service, None) is False


def test_a_settled_leaver_the_copy_put_back_is_flagged():
    service = _Stub(log=[_log("moved_out", month_sheet="September 2026", person="Julia")])

    assert rollover.reverted_move_outs(service, "September 2026", [_account("346", "Julia")]) == ["Julia"]


def test_someone_moved_back_in_on_purpose_is_not_flagged():
    # Newest first: the move back in is the newer row, so it stands.
    service = _Stub(
        log=[
            _log("moved_in", month_sheet="September 2026", person="Julia"),
            _log("moved_out", month_sheet="September 2026", person="Julia"),
        ]
    )

    assert rollover.reverted_move_outs(service, "September 2026", [_account("346", "Julia")]) == []


def test_a_leaver_who_stayed_gone_is_not_flagged():
    service = _Stub(log=[_log("moved_out", month_sheet="September 2026", person="Julia")])

    assert rollover.reverted_move_outs(service, "September 2026", [_account("346", "Mikkel")]) == []


def test_a_month_sheet_name_matches_whatever_case_the_log_holds():
    # Rows written before the Log switched to RAW came back lowercased, because
    # a Danish-locale sheet read "September 2026" as a date.
    service = _Stub(log=[_log("rolled_over", month_sheet="september 2026")])

    assert rollover.month_status(service, "September", 2026).is_open is True


def test_days_until_the_first():
    assert rollover.days_until_the_first("September", 2026, AUGUST) == 3
    assert rollover.days_until_the_first("September", 2026, SEPTEMBER) == -1


def _banner_app():
    from types import SimpleNamespace

    import streamlit as st

    from kitchenpal.ui import data, rollover as roll

    data.clear_everything()

    class StubService:
        def list_sheets(self):
            return st.session_state.get("stub_sheets", ["August 2026", "September 2026"])

        def get_log_entries(self):
            return st.session_state.get("stub_log", [])

        def get_personal_account_entries(self, worksheet_name):
            return []

        def get_room_entries(self, worksheet_name):
            return []

        def get_day_rows(self, worksheet_name, room_entries):
            return []

        def create_month_sheet(self, month_name, year):
            st.session_state["stub_created"] = (month_name, year)

        def copy_balances_from_previous_month(self, month_name, year):
            st.session_state["stub_copied"] = (month_name, year)
            return SimpleNamespace(chased=[], unplaced=[], suspected_renames=[], duplicate_names=[])

        def append_log_entries(self, entries):
            st.session_state["stub_logged"] = [entry.event for entry in entries]

    roll.render_status_banner(StubService(), room="346")


def test_the_banner_shouts_when_the_month_has_not_opened(monkeypatch):
    from streamlit.testing.v1 import AppTest

    from kitchenpal.ui import rollover as roll

    monkeypatch.setattr(roll, "this_month", lambda today=None: ("September", 2026))
    at = AppTest.from_function(_banner_app).run()

    assert not at.exception
    assert any("has not opened yet" in block.value for block in at.error)
    assert at.button(key="banner_open_month")


def test_the_banner_button_opens_the_month(monkeypatch):
    from streamlit.testing.v1 import AppTest

    from kitchenpal.ui import rollover as roll

    monkeypatch.setattr(roll, "this_month", lambda today=None: ("September", 2026))
    at = AppTest.from_function(_banner_app).run()

    at.button(key="banner_open_month").click().run()

    assert at.session_state["stub_copied"] == ("September", 2026)
    assert at.session_state["stub_logged"] == ["rolled_over"]


# ---------------------------------------------- the reminder to answer Plan

class _PlanStub:
    def __init__(self, rooms=None, planning=None, log=None, boom=False):
        self.rooms = rooms or {}
        self.planning = list(planning or [])
        self.log = list(log or [])
        self.boom = boom

    def list_sheets(self):
        return ["August 2026", "September 2026"]

    def get_log_entries(self):
        return list(self.log)

    def get_room_entries(self, worksheet_name):
        if self.boom:
            raise RuntimeError("the sheet is not answering")
        return list(self.rooms.get(worksheet_name, []))

    def get_planning_entries(self, month_name, year):
        return list(self.planning)


def _room(label, name=""):
    return SimpleNamespace(label=label, name=name, account_row=56, signup_column=9)


def _planning(room_number, available="", unavailable="", preferred=""):
    return SimpleNamespace(
        person="", room_number=room_number, available_dates=available,
        unavailable_dates=unavailable, preferred_dates=preferred, limit_one_day=False,
    )


def _prepared(sheet="September 2026"):
    return [_log("prepared", month_sheet=sheet, timestamp="2026-08-25 10:00:00")]


@pytest.fixture
def _september(monkeypatch):
    """Frederik is in 353 in August and in 353 in September, and it is prepared."""
    from kitchenpal.ui import day_to_day, rollover as roll

    monkeypatch.setattr(roll, "next_month", lambda today=None: ("September", 2026))
    monkeypatch.setattr(
        day_to_day, "identity_room_entries", lambda service: [_room("353", "Frederik Bjerg")]
    )
    return roll


def test_no_reminder_before_next_month_is_prepared(_september):
    """A sheet with one typed name is not a roster: there is nothing to answer for."""
    service = _PlanStub(rooms={"September 2026": [_room("353", "Frederik Bjerg")]}, log=[])
    assert _september.unanswered_planning_month(service, "353") is None


def test_the_reminder_appears_once_the_sheet_is_prepared_and_unanswered(_september):
    service = _PlanStub(
        rooms={"September 2026": [_room("353", "Frederik Bjerg")]}, log=_prepared()
    )
    assert _september.unanswered_planning_month(service, "353") == ("September", 2026)


def test_the_reminder_stops_once_they_have_answered(_september):
    service = _PlanStub(
        rooms={"September 2026": [_room("353", "Frederik Bjerg")]},
        planning=[_planning("353", unavailable="3, 4")],
        log=_prepared(),
    )
    assert _september.unanswered_planning_month(service, "353") is None


def test_somebody_without_a_room_next_month_is_never_asked(_september):
    """They are not on the rota, and the default that keeps them off it is the
    whole reason they must not be nudged onto it."""
    service = _PlanStub(
        rooms={"September 2026": [_room("FL2", "Frederik Bjerg")]}, log=_prepared()
    )
    assert _september.unanswered_planning_month(service, "353") is None


def test_somebody_who_is_not_on_next_months_sheet_is_never_asked(_september):
    service = _PlanStub(rooms={"September 2026": [_room("353", "Someone Else")]}, log=_prepared())
    assert _september.unanswered_planning_month(service, "353") is None


def _moved_rooms(planning):
    """353 in August, 350 in September, with the new occupant of 353 behind them."""
    return _PlanStub(
        rooms={"September 2026": [_room("350", "Frederik Bjerg"), _room("353", "Someone Else")]},
        planning=planning,
        log=_prepared(),
    )


def test_the_new_occupants_answer_does_not_silence_your_reminder(_september):
    """Rooms change hands at a rollover, so the room you claim in August says
    nothing about the row you are answering for in September."""
    assert _september.unanswered_planning_month(
        _moved_rooms([_planning("353", unavailable="3, 4")]), "353"
    ) == ("September", 2026)


def test_the_answer_that_silences_it_is_the_one_on_next_months_room(_september):
    assert _september.unanswered_planning_month(
        _moved_rooms([_planning("350", unavailable="3, 4")]), "353"
    ) is None


def test_a_read_that_fails_costs_the_reminder_and_nothing_else(_september):
    service = _PlanStub(log=_prepared(), boom=True)
    assert _september.unanswered_planning_month(service, "353") is None


def test_nobody_is_asked_before_they_have_said_who_they_are(_september):
    service = _PlanStub(
        rooms={"September 2026": [_room("353", "Frederik Bjerg")]}, log=_prepared()
    )
    assert _september.unanswered_planning_month(service, "") is None
