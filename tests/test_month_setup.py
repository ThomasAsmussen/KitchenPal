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
    assert ':has(> div[data-testid="stColumn"]:nth-child(7))' in style
    assert 'grid-template-columns: repeat(7, minmax(0, 1fr))' in style
    assert 'transform: scale(0.42)' in style
    assert 'div[data-testid="stForm"] div[data-testid="stHorizontalBlock"]' in style


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
