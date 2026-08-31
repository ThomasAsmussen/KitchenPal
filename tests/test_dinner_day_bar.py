"""Choosing a day on Dinner, without the page moving underneath you.

The house reported the picker "jumping around the page". It was an expander at
the BOTTOM, under everything it changes: a tap collapsed it, the card, the
controls and the two lists above it changed height, and the control slid out
from under the finger that had just used it. Nothing was slow — every read on
this page is cached.
"""
from datetime import datetime

import pytest
from streamlit.testing.v1 import AppTest

from kitchenpal.sheets.models import DayRow, RoomEntry


SHEETS = ["July 2026", "August 2026", "September 2026"]


def _rows(chef_days=None):
    chef_days = chef_days or {}
    return [
        DayRow(
            day=day,
            chef=chef_days.get(day, ""),
            menu="",
            menu_description="",
            signed_up=0,
            meal_price=0.0,
            signups={},
        )
        for day in range(1, 32)
    ]


def _dinner_script():
    def script():
        import streamlit as st

        from kitchenpal.sheets.models import DayRow, RoomEntry
        from kitchenpal.ui.day_to_day import render_dinner_view

        entries = [
            RoomEntry(label="346", name="Anna", account_row=56, signup_column=9),
            RoomEntry(label="347", name="Bo", account_row=57, signup_column=10),
        ]
        chef_days = st.session_state.get("chef_days", {})
        rows = [
            DayRow(
                day=day,
                chef=chef_days.get(day, ""),
                menu="",
                menu_description="",
                signed_up=0,
                meal_price=0.0,
                signups={},
            )
            for day in range(1, 32)
        ]

        class Stub:
            def list_sheets(self):
                return ["July 2026", "August 2026", "September 2026"]

            def get_room_entries(self, worksheet_name):
                return entries

            def get_day_rows(self, worksheet_name, room_entries):
                return rows if worksheet_name == "August 2026" else []

        render_dinner_view(Stub())

    return script


def _run(**state):
    at = AppTest.from_function(_dinner_script())
    at.session_state["kitchenpal_month"] = "August 2026"
    at.session_state["kitchenpal_room"] = "346"
    for key, value in state.items():
        at.session_state[key] = value
    at.run()
    assert not at.exception, at.exception
    return at


class TestTheBarSitsAboveEverythingItChanges:
    def test_the_first_thing_on_the_page_is_the_day_bar(self):
        """Above the title: nothing that can change height is over it, so it
        holds still while the page under it redraws."""
        at = _run(dinner_day=10)

        keys = [button.key for button in at.button]
        assert keys[:3] == ["kpal_day_prev", "kpal_day_open", "kpal_day_next"]
        assert at.title[0].value == "August 10th"

    def test_the_calendar_is_no_longer_in_the_page_flow(self):
        """It used to be an expander below the dinner card, which collapsed on
        every tap. There is nothing to collapse now."""
        at = _run(dinner_day=10)

        assert not [button.key for button in at.button if button.key.startswith("dinnerday_")]


class TestSteppingADay:
    def test_one_tap_moves_to_the_day_before(self):
        at = _run(dinner_day=10)

        at.button(key="kpal_day_prev").click().run()

        assert at.session_state["dinner_day"] == 9
        assert at.title[0].value == "August 9th"

    def test_one_tap_moves_to_the_day_after(self):
        at = _run(dinner_day=10)

        at.button(key="kpal_day_next").click().run()

        assert at.session_state["dinner_day"] == 11

    def test_the_first_of_the_month_has_nowhere_back_to_go(self):
        # AppTest's .click() fires a disabled button, so the guard has to be
        # asserted with .disabled and never by clicking it.
        at = _run(dinner_day=1)

        assert at.button(key="kpal_day_prev").disabled
        assert not at.button(key="kpal_day_next").disabled

    def test_the_last_day_has_nowhere_forward_to_go(self):
        at = _run(dinner_day=31)

        assert at.button(key="kpal_day_next").disabled

    def test_the_bar_says_which_day_you_are_on(self):
        at = _run(dinner_day=10)

        assert at.button(key="kpal_day_open").label == "Mon 10"


class TestTheDialog:
    def test_the_middle_button_opens_the_month(self):
        at = _run(dinner_day=10)

        at.button(key="kpal_day_open").click().run()

        # the calendar's day buttons, and the month picker beside them
        assert at.button(key="dinnerday_August 2026_day_12")
        assert at.selectbox(key="kitchenpal_month_picker")

    def test_picking_a_day_answers_and_closes(self):
        at = _run(dinner_day=10)
        at.button(key="kpal_day_open").click().run()

        at.button(key="dinnerday_August 2026_day_12").click().run()

        assert at.session_state["dinner_day"] == 12
        assert at.title[0].value == "August 12th"
        # the flag the dialog consumes to close itself is never left behind
        assert "kpal_day_picked" not in at.session_state


def _month_script():
    def script():
        import streamlit as st

        from kitchenpal.ui.month import current_month_sheet, render_month_picker

        class Stub:
            def list_sheets(self):
                return ["July 2026", "August 2026", "September 2026"]

        service = Stub()
        if st.session_state.get("show_picker", True):
            render_month_picker(service)
        st.session_state["seen"] = current_month_sheet(service)

    return script


class TestTheMonthOutlivesItsPicker:
    """Streamlit deletes the state of a widget a run did not draw. The month
    used to BE that widget's key, so it only survived while something kept
    drawing the picker — which is why every page carried one, and why House's
    Admin section, the one place that hides it, reset the month."""

    def test_choosing_a_month_is_remembered(self):
        at = AppTest.from_function(_month_script())
        at.run()

        at.selectbox(key="kitchenpal_month_picker").set_value("September 2026").run()

        assert at.session_state["seen"] == "September 2026"

    def test_it_survives_a_screen_that_does_not_draw_the_picker(self):
        at = AppTest.from_function(_month_script())
        at.run()
        at.selectbox(key="kitchenpal_month_picker").set_value("September 2026").run()

        at.session_state["show_picker"] = False
        at.run()

        assert at.session_state["seen"] == "September 2026"

    def test_and_comes_back_selected_when_the_picker_returns(self):
        at = AppTest.from_function(_month_script())
        at.run()
        at.selectbox(key="kitchenpal_month_picker").set_value("September 2026").run()
        at.session_state["show_picker"] = False
        at.run()

        at.session_state["show_picker"] = True
        at.run()

        assert at.selectbox(key="kitchenpal_month_picker").value == "September 2026"
