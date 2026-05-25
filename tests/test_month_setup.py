from types import SimpleNamespace

from kitchenpal.ui import month_setup


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
