from types import SimpleNamespace

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
