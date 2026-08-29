"""Admin: the two questions, the parked-FL suggestion, and opening by hand."""
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from kitchenpal.ui.admin import parked_fl_suggestions


def _account(label, name="", balance=0.0, row_number=56):
    return SimpleNamespace(label=label, name=name, balance=balance, row_number=row_number)


def _log(event, person="", room_intent="", month_sheet="August 2026"):
    return SimpleNamespace(
        event=event, person=person, room_intent=room_intent, month_sheet=month_sheet,
        summary="", action_id="", by="", from_label="", to_label="", balance="", timestamp="",
    )


def test_parked_person_is_suggested_when_the_room_they_wait_for_is_free():
    accounts = [_account("352"), _account("FL1", "Gustav", -178.79)]
    log = [_log("parked_fl", person="Gustav", room_intent="352")]

    suggestions = parked_fl_suggestions(log, accounts)

    assert len(suggestions) == 1
    assert (suggestions[0].person, suggestions[0].fl_label, suggestions[0].room_label) == ("Gustav", "FL1", "352")


def test_the_newest_parking_row_wins():
    # get_log_entries hands back newest first; changing your mind must not be
    # undone by the older row underneath it.
    log = [
        _log("parked_fl", person="Gustav", room_intent="352"),
        _log("parked_fl", person="Gustav", room_intent="347"),
    ]
    accounts = [_account("347"), _account("352"), _account("FL1", "Gustav")]

    suggestions = parked_fl_suggestions(log, accounts)

    assert [item.room_label for item in suggestions] == ["352"]


def test_no_suggestion_once_the_room_is_taken_or_the_person_moved_in():
    log = [_log("parked_fl", person="Gustav", room_intent="352")]

    taken = parked_fl_suggestions(log, [_account("352", "Someone else"), _account("FL1", "Gustav")])
    already_moved = parked_fl_suggestions(log, [_account("352", "Gustav"), _account("FL1")])

    assert taken == []
    assert already_moved == []


# --------------------------------------------------------------- the UI

def _admin_app():
    from types import SimpleNamespace

    import streamlit as st

    from kitchenpal.ui import data
    from kitchenpal.ui.admin import render_admin_view

    # A stub service is hidden from the cache key (the argument is underscored),
    # so each run starts from an empty cache instead of another test's reads.
    data.clear_everything()

    def account(label, name="", balance=0.0):
        return SimpleNamespace(label=label, name=name, balance=balance, row_number=56)

    class StubService:
        def list_sheets(self):
            return st.session_state.get("stub_sheets", ["August 2026", "September 2026"])

        def get_personal_account_entries(self, worksheet_name):
            override = st.session_state.get("stub_accounts", {}).get(worksheet_name)
            if override is not None:
                return [account(*row) for row in override]
            if worksheet_name in st.session_state.get("stub_named_sheets", ["August 2026"]):
                return [account("346", "Julia", -100.0), account("352")]
            return [account("346"), account("352")]

        def get_room_entries(self, worksheet_name):
            return self.get_personal_account_entries(worksheet_name)

        def get_possible_days_limit(self, month_name, year):
            return ""

        def get_planning_entries(self, month_name, year):
            return []

        def get_day_rows(self, worksheet_name, room_entries):
            if st.session_state.get("stub_cooks"):
                return [SimpleNamespace(day=1, chef="346")]
            return []

        def get_log_entries(self):
            return st.session_state.get("stub_log", [])

        def create_month_sheet(self, month_name, year):
            st.session_state["stub_created"] = (month_name, year)

        def append_log_entries(self, entries):
            st.session_state["stub_logged"] = [entry.event for entry in entries]

        def copy_balances_from_previous_month(self, month_name, year):
            st.session_state["stub_copied"] = (month_name, year)
            return SimpleNamespace(
                chased=st.session_state.get("stub_chased", []),
                unplaced=st.session_state.get("stub_unplaced", []),
                suspected_renames=st.session_state.get("stub_renames", []),
                duplicate_names=st.session_state.get("stub_duplicates", []),
            )

    render_admin_view(StubService())


def test_admin_asks_two_questions():
    at = AppTest.from_function(_admin_app).run()

    assert not at.exception
    assert at.button(key="admin_question_moving")
    assert at.button(key="admin_question_cooking")


def test_thats_everyone_prepares_the_month_and_records_the_answer():
    at = AppTest.from_function(_admin_app).run()

    at.button(key="admin_question_moving").click().run()
    at.button(key="admin_confirm_occupancy").click().run()

    assert not at.exception
    # Saying "this is right" is what fills the sheet: it is never a step of its own.
    assert at.session_state["stub_copied"] == ("September", 2026)
    assert at.session_state["stub_logged"] == ["occupancy_confirmed"]


def test_both_questions_answered_says_there_is_nothing_left():
    at = AppTest.from_function(_admin_app)
    at.session_state["stub_accounts"] = {"September 2026": [("346", "Julia", 0.0)]}
    at.session_state["stub_log"] = [
        _log("prepared", month_sheet="September 2026"),
        _log("occupancy_confirmed", month_sheet="September 2026"),
    ]
    at.session_state["stub_cooks"] = True
    at.run()

    assert not at.exception
    assert any("Nothing left to do" in block.value for block in at.success)


def test_only_people_with_a_room_count_as_needing_to_answer():
    # Someone parked without a room may answer on Plan and is scheduled if they
    # do, but they are not on the rota, so "everyone has answered" ignores them.
    from kitchenpal.ui.admin import _answer_counts

    class Stub:
        def list_sheets(self):
            return ["August 2026", "September 2026"]

        def get_room_entries(self, worksheet_name):
            return [
                SimpleNamespace(label="346", name="Julia", signup_column=9),
                SimpleNamespace(label="347", name="", signup_column=10),
                SimpleNamespace(label="FL1", name="Gustav", signup_column=24),
            ]

        def get_planning_entries(self, month_name, year):
            return []

    from kitchenpal.ui import data

    data.clear_everything()
    assert _answer_counts(Stub(), "September", 2026, "September 2026") == (0, 1)


def test_the_question_is_a_roster_once_the_month_has_one():
    at = AppTest.from_function(_admin_app)
    at.session_state["stub_accounts"] = {
        "September 2026": [("346", "Julia", -100.0), ("352", "", 0.0), ("FL1", "", 0.0)]
    }
    at.session_state["stub_log"] = [_log("prepared", month_sheet="September 2026")]
    at.run()

    at.button(key="admin_question_moving").click().run()

    assert not at.exception
    text = " ".join(block.value for block in at.markdown)
    assert "Julia" in text
    assert "352 — empty" in text


def test_opening_by_hand_carries_the_balances_and_logs_it():
    at = AppTest.from_function(_admin_app).run()

    at.button(key="admin_open_month").click().run()

    assert not at.exception
    assert at.session_state["stub_copied"] == ("September", 2026)
    assert at.session_state["stub_logged"] == ["rolled_over"]


def test_the_copy_report_is_surfaced():
    at = AppTest.from_function(_admin_app)
    at.session_state["stub_chased"] = [("Alberte", -150.0, "FL5")]
    at.session_state["stub_unplaced"] = [("Asta", -201.0)]
    at.session_state["stub_renames"] = [("352", "Asta", "Astaa")]
    at.run()

    at.button(key="admin_open_month").click().run()

    assert not at.exception
    info_text = " ".join(block.value for block in at.info)
    warning_text = " ".join(block.value for block in at.warning)
    assert "Alberte" in info_text and "FL5" in info_text
    assert "Asta" in warning_text and "-201.00" in warning_text
    assert "Astaa" in warning_text


def test_money_left_behind_last_month_shows_as_a_to_do():
    at = AppTest.from_function(_admin_app)
    # September has a roster of its own, and Julia is not on it.
    at.session_state["stub_accounts"] = {"September 2026": [("346", "Mikkel", 0.0), ("352", "", 0.0)]}
    at.session_state["stub_log"] = [_log("prepared", month_sheet="September 2026")]
    at.run()

    assert not at.exception
    text = " ".join(block.value for block in at.markdown)
    assert "Julia has no row in September" in text
    assert "-100.00 DKK" in text
