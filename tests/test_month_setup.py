from types import SimpleNamespace

from kitchenpal.sheets_service import PlanningEntry
from kitchenpal.ui import month_setup


def test_month_sheet_names_keeps_only_english_or_danish_month_year_names():
    sheet_names = ["Planning", "May 2026", "Maj 2026", "Bugs", "New Features", "May", "2026 May", "May 26"]

    assert month_setup._month_sheet_names(sheet_names) == ["May 2026", "Maj 2026"]


def test_month_sheet_for_accepts_english_and_danish_month_names():
    sheet_names = ["May 2026", "Juni 2026", "Planning"]

    assert month_setup._month_sheet_for(5, 2026, sheet_names) == "May 2026"
    assert month_setup._month_sheet_for(6, 2026, sheet_names) == "Juni 2026"
    assert month_setup._month_sheet_for(7, 2026, sheet_names) is None


def test_unassigned_people_with_room_numbers_filters_non_room_accounts():
    people = month_setup._unassigned_people_with_room_numbers(
        ["Julia", "Gustav", "Missing"],
        {
            "Julia": "357",
            "Gustav": "FL1",
        },
    )

    assert people == ["Julia (357)"]


def test_set_category_days_updates_backing_state_without_touching_widgets(monkeypatch):
    state = {
        "planning_dates_2026_May_Julia_available_v0_1": True,
        "planning_dates_2026_May_Julia_available_v0_2": False,
    }
    monkeypatch.setattr(month_setup, "st", SimpleNamespace(session_state=state))

    month_setup._set_category_days("planning_dates_2026_May_Julia", "available", [2])

    assert state["planning_dates_2026_May_Julia_available"] == [2]
    assert state["planning_dates_2026_May_Julia_available_v0_1"] is True
    assert state["planning_dates_2026_May_Julia_available_v0_2"] is False


def test_set_category_days_can_reset_calendar_widget_version(monkeypatch):
    state = {"planning_dates_2026_May_Julia_available_widget_version": 2}
    monkeypatch.setattr(month_setup, "st", SimpleNamespace(session_state=state))

    month_setup._set_category_days("planning_dates_2026_May_Julia", "available", [2], reset_widgets=True)

    assert state["planning_dates_2026_May_Julia_available"] == [2]
    assert state["planning_dates_2026_May_Julia_available_widget_version"] == 3


def test_initialize_planning_day_state_reloads_when_cache_version_changes(monkeypatch):
    state = {
        "planning_dates_2026_May_Julia_available": [1],
        "planning_dates_2026_May_Julia_source_version": 1,
        "planning_dates_2026_May_Julia_available_widget_version": 0,
    }
    monkeypatch.setattr(month_setup, "st", SimpleNamespace(session_state=state))

    month_setup._initialize_planning_day_state(
        key_prefix="planning_dates_2026_May_Julia",
        stored_days={"available": {3}, "unavailable": {4}, "preferred": {5}},
        possible_day_set={3, 4, 5},
        source_version=2,
    )

    assert state["planning_dates_2026_May_Julia_available"] == [3]
    assert state["planning_dates_2026_May_Julia_unavailable"] == [4]
    assert state["planning_dates_2026_May_Julia_preferred"] == [5]
    assert state["planning_dates_2026_May_Julia_source_version"] == 2
    assert state["planning_dates_2026_May_Julia_available_widget_version"] == 1


def test_initialize_planning_day_state_keeps_unsaved_state_with_same_cache_version(monkeypatch):
    state = {
        "planning_dates_2026_May_Julia_available": [1],
        "planning_dates_2026_May_Julia_source_version": 2,
    }
    monkeypatch.setattr(month_setup, "st", SimpleNamespace(session_state=state))

    month_setup._initialize_planning_day_state(
        key_prefix="planning_dates_2026_May_Julia",
        stored_days={"available": {3}, "unavailable": set(), "preferred": set()},
        possible_day_set={1, 3},
        source_version=2,
    )

    assert state["planning_dates_2026_May_Julia_available"] == [1]


def test_normalize_planning_days_saving_available_clears_unavailable():
    selected_days = {
        "available": [4, 5],
        "unavailable": [6],
        "preferred": [5],
    }

    assert month_setup.normalize_planning_days(selected_days, "available", False, [4, 5, 6]) == {
        "available": [4, 5],
        "unavailable": [],
        "preferred": [5],
    }


def test_normalize_planning_days_saving_unavailable_clears_available():
    selected_days = {
        "available": [4],
        "unavailable": [6],
        "preferred": [4],
    }

    assert month_setup.normalize_planning_days(selected_days, "unavailable", False, [4, 5, 6]) == {
        "available": [],
        "unavailable": [6],
        "preferred": [4],
    }


def test_normalize_planning_days_force_unavailable_uses_all_possible_days():
    selected_days = {
        "available": [4],
        "unavailable": [6],
        "preferred": [4],
    }

    assert month_setup.normalize_planning_days(selected_days, "available", True, [4, 5, 6]) == {
        "available": [],
        "unavailable": [4, 5, 6],
        "preferred": [],
    }


def test_default_cannot_host_false_for_non_room_with_saved_available_day():
    stored_entry = PlanningEntry(
        person="Gustav",
        room_number="FL1",
        available_dates="7",
        unavailable_dates="",
        preferred_dates="",
        limit_one_day=False,
    )

    assert month_setup._default_cannot_host_this_month("FL1", stored_entry, [1, 2, 7], 2026, 6) is False


def test_default_cannot_host_true_for_non_room_without_saved_choices():
    assert month_setup._default_cannot_host_this_month("FL1", None, [1, 2, 7], 2026, 6) is True


def test_default_date_category_uses_unavailable_when_only_cannot_dates_are_saved():
    stored_entry = PlanningEntry(
        person="Philip",
        room_number="354",
        available_dates="",
        unavailable_dates="1, 2, 3, 24",
        preferred_dates="",
        limit_one_day=False,
    )

    assert month_setup._default_date_category(stored_entry, 2026, 6) == "unavailable"


def test_planning_responsive_style_targets_small_screens():
    style = month_setup._planning_responsive_style()

    assert "@media (max-width: 900px)" in style
    # Scoped to our own keyed-container class, not Streamlit's form internals.
    assert '[class*="st-key-kpalcal"]' in style
    assert 'grid-template-columns: repeat(7, minmax(0, 1fr))' in style
    # Tap targets must be thumb-sized, never scaled down.
    assert "min-height: 2.5rem" in style
    assert "scale(" not in style
    assert ":has(" not in style
    assert 'div[data-testid="stForm"]' not in style


def test_weekday_label_uses_one_letter():
    assert month_setup._weekday_label("Monday") == "M"
    assert month_setup._weekday_label("Thursday") == "T"


def test_planning_overview_rows_show_current_choices():
    rows = month_setup.planning_overview_rows(
        people_list=["Julia", "Gustav"],
        person_to_room={"Julia": "346", "Gustav": "FL1"},
        available={"Julia": ["2", "4"], "Gustav": []},
        unavailable={"Julia": [], "Gustav": ["1", "2", "3"]},
        preferences={"Julia": [4], "Gustav": []},
        limit_one_day_per_person={"Julia": True, "Gustav": False},
    )

    assert rows == [
        {
            "Person": "Julia",
            "Room": "346",
            "Can host": "2, 4",
            "Cannot host": "None",
            "Preferred": "4",
            "Host at most once": "Yes",
        },
        {
            "Person": "Gustav",
            "Room": "FL1",
            "Can host": "None",
            "Cannot host": "1, 2, 3",
            "Preferred": "None",
            "Host at most once": "No",
        },
    ]


def test_planning_overview_rows_show_empty_availability_as_all_possible_dates():
    rows = month_setup.planning_overview_rows(
        people_list=["Julia"],
        person_to_room={"Julia": "346"},
        available={"Julia": []},
        unavailable={"Julia": []},
        preferences={"Julia": []},
        limit_one_day_per_person={"Julia": False},
    )

    assert rows[0]["Can host"] == "All possible dates"


def _planner_app():
    import streamlit as st

    from kitchenpal.ui.month_setup import render_availability_planner

    render_availability_planner(st.session_state["planner_service"])


class _FakeSheet:
    """Just enough of a gspread worksheet for the Planning/Possible Days reads."""

    def __init__(self, rows=()):
        self.rows = [list(row) for row in rows]

    def get_all_values(self):
        return [list(row) for row in self.rows]

    def clear(self):
        self.rows = []

    def update(self, range_name, values):
        start_row = int("".join(character for character in range_name.split(":")[0] if character.isdigit()))
        while len(self.rows) < start_row - 1 + len(values):
            self.rows.append([""] * 8)
        for offset, row in enumerate(values):
            self.rows[start_row - 1 + offset] = [str(cell) for cell in row]


def _planner_service(month_sheet_name, planning_rows, room_names):
    from kitchenpal.constants import PLANNING_HEADERS
    from kitchenpal.sheets.planning import PlanningSheetsMixin
    from kitchenpal.sheets_service import RoomEntry

    class _Service(PlanningSheetsMixin):
        def __init__(self):
            self.sheets = {
                "Planning": _FakeSheet([list(PLANNING_HEADERS)] + list(planning_rows)),
                "Possible Days": _FakeSheet([["Year", "Month", "Limit days"]]),
                month_sheet_name: _FakeSheet(),
            }

        def list_sheets(self):
            return list(self.sheets)

        def get_worksheet(self, worksheet_name):
            return self.sheets[worksheet_name]

        def get_room_entries(self, worksheet_name):
            return [
                RoomEntry(label=label, name=room_names.get(label, ""), account_row=45 + index, signup_column=9 + index)
                for index, label in enumerate(["348", "350", "352"])
            ]

        def planning_rows(self):
            return [row for row in self.sheets["Planning"].get_all_values()[1:] if any(row)]

    return _Service()


def _planning_day_checkbox(at, person, category, day, month_name):
    prefix = f"planning_dates_{{}}_{month_name}_{person}_{category}_v"
    matches = [
        checkbox
        for checkbox in at.checkbox
        if checkbox.key.startswith(prefix.format(at.number_input[0].value)) and checkbox.key.endswith(f"_{day}")
    ]
    assert len(matches) == 1, (person, category, day, [checkbox.key for checkbox in matches])
    return matches[0]


def _checked_planning_days(at, person, category, month_name):
    prefix = f"planning_dates_{at.number_input[0].value}_{month_name}_{person}_{category}_v"
    return sorted(
        int(checkbox.key.rsplit("_", 1)[1]) for checkbox in at.checkbox if checkbox.key.startswith(prefix) and checkbox.value
    )


def _click_save(at, person):
    for button in at.button:
        if button.proto.label == "Save availability" and button.proto.form_id.endswith(f"_{person}"):
            return button.click().run()
    raise AssertionError(f"no save button for {person}")


def test_planner_updates_the_stored_room_row_when_the_month_sheet_name_changes():
    # Reproduces the September corruption: the sign-ups were written while the
    # month sheet had no names, so the Planning rows are keyed by room number.
    # Once the names come back, editing must reload and update those rows
    # instead of orphaning them behind a duplicate.
    from datetime import datetime, timedelta

    from streamlit.testing.v1 import AppTest

    from kitchenpal.constants import ENGLISH_MONTHS
    from kitchenpal.scheduler import get_weekdays_in_month

    planned = datetime.now().replace(day=1) + timedelta(days=32)
    month_name = ENGLISH_MONTHS[planned.month - 1]
    month_sheet_name = f"{month_name} {planned.year}"
    possible_days = get_weekdays_in_month(planned.year, planned.month)
    stored_days, added_day = possible_days[:3], possible_days[3]

    service = _planner_service(
        month_sheet_name=month_sheet_name,
        planning_rows=[
            [str(planned.year), month_name, "348", "348", ", ".join(str(day) for day in possible_days[:2]), "", "", "FALSE"],
            [str(planned.year), month_name, "350", "350", ", ".join(str(day) for day in stored_days), "", "", "FALSE"],
        ],
        room_names={"348": "Alberte", "350": "Josefine", "352": "Asta"},
    )

    at = AppTest.from_function(_planner_app)
    at.session_state["planner_service"] = service
    at.run()
    assert not at.exception

    # Her preferences load even though the row was saved under the room number.
    assert _checked_planning_days(at, "Josefine", "available", month_name) == stored_days

    _planning_day_checkbox(at, "Josefine", "available", added_day, month_name).check()
    at = _click_save(at, "Josefine")
    assert not at.exception

    expected_days = ", ".join(str(day) for day in stored_days + [added_day])
    assert service.planning_rows() == [
        [str(planned.year), month_name, "348", "348", ", ".join(str(day) for day in possible_days[:2]), "", "", "FALSE"],
        [str(planned.year), month_name, "Josefine", "350", expected_days, "", "", "FALSE"],
    ]
