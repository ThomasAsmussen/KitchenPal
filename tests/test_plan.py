"""Plan: the day states, what gets saved, and how an answer reads back."""
from types import SimpleNamespace

from kitchenpal.ui import plan


def _stored(available="", unavailable="", preferred="", limit_one_day=False):
    return SimpleNamespace(
        available_dates=available,
        unavailable_dates=unavailable,
        preferred_dates=preferred,
        limit_one_day=limit_one_day,
    )


DAYS = [1, 2, 3, 6, 7]


def test_every_dinner_day_starts_as_one_you_can_cook():
    assert plan.day_states_from_entry(None, DAYS, 2026, 9) == {day: "can" for day in DAYS}


def test_an_answer_is_read_back_as_its_exceptions():
    states = plan.day_states_from_entry(
        _stored(available="1, 2, 3, 6, 7", unavailable="3, 6", preferred="7"), DAYS, 2026, 9
    )

    assert states == {1: "can", 2: "can", 3: "cant", 6: "cant", 7: "pref"}


def test_an_old_whitelist_answer_keeps_its_meaning():
    # Saved under the old UI: days listed were the yes, everything else the no.
    # Reading those as "can" would silently turn a narrow answer into a wide one.
    states = plan.day_states_from_entry(_stored(available="2, 7"), DAYS, 2026, 9)

    assert states == {1: "cant", 2: "can", 3: "cant", 6: "cant", 7: "can"}


def test_someone_without_a_room_starts_as_not_cooking():
    # They are not on the rota, so they must never end up with a night they did
    # not ask for — but every day is one tap away if they want it.
    states = plan.day_states_from_entry(None, DAYS, 2026, 9, default=plan.CANT)

    assert states == {day: "cant" for day in DAYS}


def test_a_preferred_day_is_still_a_day_you_can_cook():
    # The solver picks from available; a preference outside it is unusable.
    days = plan.entry_days({1: "can", 2: "pref", 3: "cant"}, [1, 2, 3])

    assert days == {"available": [1, 2], "unavailable": [3], "preferred": [2]}


def test_tapping_a_day_cycles_can_to_cant_to_prefer(monkeypatch):
    import streamlit as st

    state = {"k": {5: "can"}}
    monkeypatch.setattr(st, "session_state", state)

    plan._cycle_day("k", 5)
    assert state["k"][5] == "cant"
    plan._cycle_day("k", 5)
    assert state["k"][5] == "pref"
    plan._cycle_day("k", 5)
    assert state["k"][5] == "can"


def test_has_answered_is_false_until_something_is_stored():
    assert plan.has_answered(None, DAYS, 2026, 9) is False
    assert plan.has_answered(_stored(), DAYS, 2026, 9) is False
    assert plan.has_answered(_stored(unavailable="3"), DAYS, 2026, 9) is True


def test_days_read_as_people_say_them():
    assert plan.day_list([3]) == "the 3rd"
    assert plan.day_list([3, 4, 17]) == "the 3rd, 4th and 17th"
    assert plan.day_list([]) == ""
    assert "and 2 more" in plan.day_list(list(range(1, 11)))


def test_the_grid_styles_ride_with_every_page():
    # The first calendar's stylesheet was written, tested against its own
    # string, and never put on a page. Now it is part of page_styles, which
    # _chrome emits on every screen, so a calendar cannot outrun its styles.
    from kitchenpal.ui.calendar_grid import grid_styles
    from kitchenpal.ui.nav import page_styles

    styles = grid_styles(dark=False)
    assert "grid-template-columns: repeat(7, minmax(0, 1fr))" in styles
    assert '[class*="st-key-kpalcal_"]' in styles
    assert "min-height: 2.4rem" in styles
    assert "@media" not in styles

    on_the_page = page_styles("plan")
    assert '[class*="st-key-kpalcal_"]' in on_the_page
    assert '[class*="st-key-kpalday_mine_"]' in on_the_page


def test_plan_asks_nobody_which_month_they_meant():
    """Reported from production: the month picker offered 36 combinations against
    the two sheets that exist, and choosing one of the other 34 replaced the page
    with "create the sheet first" — taking the picker with it, because it was
    drawn below that early return. The tab was then dead for the whole session;
    Refresh clears the data caches, not the choice. There is one right answer to
    "which month", so the tab no longer asks."""
    from streamlit.testing.v1 import AppTest

    def script():
        from kitchenpal.ui.plan import render_planning_view

        class Stub:
            def list_sheets(self):
                return ["August 2019"]

        render_planning_view(Stub())

    at = AppTest.from_function(script).run()

    assert not at.exception
    assert any("before planning" in block.value for block in at.info)
    assert len(at.selectbox) == 0


def _plan_stub_script(sheets):
    def script():
        import streamlit as st

        from kitchenpal.ui.plan import render_planning_view

        class Stub:
            def list_sheets(self):
                return st.session_state["sheets"]

            def get_room_entries(self, worksheet_name):
                return []

            def get_planning_entries(self, month_name, year):
                return []

            def get_possible_days_limit(self, month_name, year):
                return ""

        render_planning_view(Stub())

    return script


def test_plan_says_why_it_is_showing_the_month_you_are_in():
    """Falling back is right, but an unexplained heading reads as the app's mistake."""
    from datetime import datetime

    from streamlit.testing.v1 import AppTest

    from kitchenpal.ui.month_setup import upcoming_month

    this_month = datetime.now().strftime("%B %Y")
    at = AppTest.from_function(_plan_stub_script(None))
    at.session_state["sheets"] = [this_month]
    at.run()

    assert not at.exception
    assert any(f"{upcoming_month()[0]} is not ready to plan yet" in c.value for c in at.caption)


def test_plan_says_nothing_extra_when_it_is_on_the_month_you_came_for():
    from datetime import datetime

    from streamlit.testing.v1 import AppTest

    from kitchenpal.ui.month_setup import upcoming_month

    ahead = upcoming_month()
    at = AppTest.from_function(_plan_stub_script(None))
    at.session_state["sheets"] = [datetime.now().strftime("%B %Y"), f"{ahead[0]} {ahead[1]}"]
    at.run()

    assert not at.exception
    assert not any("not ready to plan yet" in c.value for c in at.caption)


def _schedule_card_script():
    def script():
        import streamlit as st

        from kitchenpal.sheets.models import DayRow, RoomEntry
        from kitchenpal.ui.month_setup import PlanningContext
        from kitchenpal.ui.plan import render_schedule_card

        entries = [
            RoomEntry(label="346", name="Anna", account_row=56, signup_column=9),
            RoomEntry(label="347", name="Bo", account_row=57, signup_column=10),
        ]
        rows = [
            DayRow(
                day=day,
                chef={4: "346", 11: "347", 18: "346"}.get(day, ""),
                menu="",
                menu_description="",
                signed_up=0,
                meal_price=0.0,
                signups={},
            )
            for day in range(1, 31)
        ]

        class Stub:
            def get_room_entries(self, worksheet_name):
                return entries

            def get_day_rows(self, worksheet_name, room_entries):
                return rows

        context = PlanningContext(
            year=2026,
            month=9,
            month_name="September",
            sheet_name="September 2026",
            room_entries=entries,
            stored_entries={},
            possible_days=list(range(1, 31)),
            limit_days="",
        )
        st.session_state["drew"] = render_schedule_card(Stub(), context, entries[0], {})

    return script


def _run_schedule_card():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_function(_schedule_card_script()).run()
    assert not at.exception, at.exception
    return at


class TestSwappingFromPlan:
    """Plan is where you look at next month's nights, and it used to answer
    "ask an admin". Dinner opens on the month you are living in, so sending
    people there to trade a night in the month they had just answered for was
    a tab change and a month change to reach a control that fits here."""

    def test_each_of_your_nights_can_be_swapped_where_it_is_shown(self):
        at = _run_schedule_card()

        keys = [button.key for button in at.button]
        assert "edit_plannight_September 2026_4" in keys
        assert "edit_plannight_September 2026_18" in keys
        assert "edit_plannight_September 2026_11" not in keys  # that one is Bo's

    def test_nobody_is_told_to_ask_an_admin(self):
        at = _run_schedule_card()

        captions = " ".join(block.value for block in at.caption)
        assert "admin" not in captions.lower()
        assert "hand a night over" in captions.lower()
        helps = [button.help for button in at.button if button.help]
        assert any("swap" in text.lower() for text in helps)

    def test_the_swap_opens_on_the_month_being_planned(self):
        at = _run_schedule_card()

        at.button(key="edit_plannight_September 2026_4").click().run()

        assert not at.exception
        assert any("September 4th" in block.value for block in at.markdown)
