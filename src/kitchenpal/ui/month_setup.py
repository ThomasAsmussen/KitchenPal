import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta

import gspread
import streamlit as st

from ..constants import ENGLISH_MONTHS, MONTH_TO_NUMBER
from ..runtime_state import bump_cache_version, get_cache_version
from ..scheduler import get_weekdays_in_month, parse_dates, split_date_input
from ..sheets.utils import normalized_person_name, parse_month_sheet_name
from ..sheets_service import PlanningEntry, SheetsService
from . import data
from .errors import show_user_error, user_error_message
from .identity import current_room

ENGLISH_WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
def _is_numeric_room_label(label: str) -> bool:
    return label.isdigit()


def _is_planner_room_entry(entry) -> bool:
    return entry.label.isdigit() or (entry.label.startswith("FL") and bool(entry.name))


def _stored_planning_days(stored_entry: PlanningEntry | None, year: int, month: int) -> dict[str, set[int]]:
    return {
        "available": parse_entry_days(stored_entry.available_dates, year, month) if stored_entry else set(),
        "unavailable": parse_entry_days(stored_entry.unavailable_dates, year, month) if stored_entry else set(),
        "preferred": parse_entry_days(stored_entry.preferred_dates, year, month) if stored_entry else set(),
    }


def _default_cannot_host_this_month(room_label: str, stored_entry: PlanningEntry | None, possible_days: list[int], year: int, month: int) -> bool:
    if _is_numeric_room_label(room_label):
        return False

    stored_days = _stored_planning_days(stored_entry, year, month)
    if stored_days["available"] or stored_days["preferred"]:
        return False
    if stored_days["unavailable"]:
        return set(possible_days).issubset(stored_days["unavailable"])
    return True


def _default_date_category(stored_entry: PlanningEntry | None, year: int, month: int) -> str:
    stored_days = _stored_planning_days(stored_entry, year, month)
    if stored_days["unavailable"] and not stored_days["available"]:
        return "unavailable"
    return "available"


def _month_sheet_names(sheet_names: list[str]) -> list[str]:
    return [sheet_name for sheet_name in sheet_names if parse_month_sheet_name(sheet_name) is not None]


def _month_sheet_for(month: int, year: int, sheet_names: list[str]) -> str | None:
    for sheet_name in sheet_names:
        if parse_month_sheet_name(sheet_name) == (month, year):
            return sheet_name
    return None


def _previous_month_and_year(month_number: int, year: int) -> tuple[str, int]:
    previous_index = (month_number - 2) % 12
    previous_year = year - 1 if month_number == 1 else year
    return ENGLISH_MONTHS[previous_index], previous_year


@dataclass(frozen=True)
class PlanningContext:
    year: int
    month: int
    month_name: str
    sheet_name: str
    room_entries: list
    stored_entries: dict
    possible_days: list
    limit_days: str


def _planning_month(service: SheetsService, *, show_picker: bool):
    """Planning is about the month ahead, so it keeps its own choice."""
    next_month_date = datetime.now().replace(day=1) + timedelta(days=32)
    year_key, month_key = "planning_year", "planning_month"
    if month_key not in st.session_state:
        st.session_state[month_key] = ENGLISH_MONTHS[next_month_date.month - 1]
    if year_key not in st.session_state:
        st.session_state[year_key] = next_month_date.year

    if show_picker:
        with st.expander("Another month"):
            st.selectbox("Month", ENGLISH_MONTHS, key=month_key)
            st.selectbox("Year", [next_month_date.year - 1, next_month_date.year, next_month_date.year + 1], key=year_key)
    return st.session_state[month_key], int(st.session_state[year_key])


def _planning_context(
    service: SheetsService,
    *,
    show_picker: bool = False,
    month_name: str | None = None,
    year: int | None = None,
) -> PlanningContext | None:
    """Plan keeps its own month; Admin passes the one the rollover is about."""
    if month_name is None or year is None:
        month_name, year = _planning_month(service, show_picker=show_picker)
    month = MONTH_TO_NUMBER[month_name]

    available_month_sheets = _month_sheet_names(data.sheet_names(service))
    if not available_month_sheets:
        st.warning("No month sheets are available yet.")
        return None

    sheet_name = _month_sheet_for(month, year, available_month_sheets)
    if sheet_name is None:
        st.info(f"Create the {month_name} {year} sheet before planning.")
        return None

    try:
        room_entries = [
            entry for entry in data.room_entries(service, sheet_name) if _is_planner_room_entry(entry)
        ]
    except gspread.exceptions.WorksheetNotFound as exc:
        show_user_error(st, exc, "Could not load the people for this month")
        return None

    # Stored preferences are looked up by room label, the identity the Planning
    # sheet keys rows on. The name in the sheet is only what the month sheet
    # called the occupant at save time, so it must never be the lookup key.
    stored_entries = {
        str(entry.room_number).strip(): entry
        for entry in data.planning_entries(service, month_name, year)
        if str(entry.room_number).strip()
    }

    limit_days = data.possible_days_limit(service, month_name, year)
    possible_days = get_weekdays_in_month(year, month)
    if str(limit_days).strip():
        try:
            allowed = parse_dates(split_date_input(limit_days), year, month)
            possible_days = [day for day in possible_days if day in allowed]
        except ValueError as exc:
            st.error(user_error_message(exc, "Could not read the day limit"))

    return PlanningContext(
        year=year,
        month=month,
        month_name=month_name,
        sheet_name=sheet_name,
        room_entries=room_entries,
        stored_entries=stored_entries,
        possible_days=possible_days,
        limit_days=str(limit_days or ""),
    )


def _stored_availability(context: PlanningContext):
    """Everyone's saved answers, which is what the schedule is built from.

    combine_availability reads an empty list of available days as "every day",
    so silence is a yes. That is right for someone on the rota and wrong for
    someone without a room: they are not expected to cook, so they must not be
    assignable until they say they want to.
    """
    available, unavailable, preferences, limit_one_day, person_to_room = {}, {}, {}, {}, {}
    for entry in context.room_entries:
        person = entry.name or entry.label
        stored = context.stored_entries.get(entry.label)
        if stored is None and not _is_numeric_room_label(entry.label):
            available[person] = []
            unavailable[person] = [str(day) for day in context.possible_days]
            preferences[person] = []
            limit_one_day[person] = False
            person_to_room[person] = entry.label
            continue
        days = _stored_planning_days(stored, context.year, context.month)
        available[person] = [str(day) for day in sorted(days["available"])]
        unavailable[person] = [str(day) for day in sorted(days["unavailable"])]
        preferences[person] = sorted(days["preferred"])
        limit_one_day[person] = stored.limit_one_day if stored else False
        person_to_room[person] = entry.label
    return available, unavailable, preferences, limit_one_day, person_to_room


def _answered_count(context: PlanningContext) -> int:
    answered = 0
    for entry in _rota_entries(context):
        stored = context.stored_entries.get(entry.label)
        days = _stored_planning_days(stored, context.year, context.month)
        if days["available"] or days["unavailable"] or days["preferred"]:
            answered += 1
    return answered


def _planning_room_entry(service: SheetsService, context: PlanningContext):
    """The row that is YOU in the month being planned.

    Identity is a claim on a room in the month you are living in, and rooms
    change hands at a rollover. Planning is about the month ahead, so the claim
    is resolved through your NAME: if you are in 356 this month and 350 next
    month, your answers belong to 350 — and must not land on the card of
    whoever takes 356.
    """
    from .day_to_day import identity_room_entries

    current_entries = identity_room_entries(service)
    claimed = current_room(current_entries)
    if not claimed:
        return None, ""

    my_name = next((entry.name for entry in current_entries if entry.label == claimed), "")
    if my_name:
        key = normalized_person_name(my_name)
        matches = [
            entry
            for entry in context.room_entries
            if entry.name and normalized_person_name(entry.name) == key
        ]
        if len(matches) == 1:
            return matches[0], claimed

    by_label = next((entry for entry in context.room_entries if entry.label == claimed), None)
    if by_label is None:
        return None, claimed
    # The label alone is only good enough while it is nobody else's.
    if not by_label.name or not my_name or normalized_person_name(by_label.name) == normalized_person_name(my_name):
        return by_label, claimed
    return None, claimed


def _rota_entries(context: PlanningContext) -> list:
    """The people expected to cook: rooms with someone living in them.

    Anyone without a room may still answer, and is scheduled if they do. They
    are simply not on the rota, so they cannot be missing from it.
    """
    return [entry for entry in context.room_entries if entry.label.isdigit() and entry.name]


def render_availability_overview(service: SheetsService):
    """Read-only: when everyone else can cook."""
    context = _planning_context(service)
    if context is None:
        return

    available, unavailable, preferences, limit_one_day, person_to_room = _stored_availability(context)
    rows = planning_overview_rows(
        people_list=[entry.name or entry.label for entry in context.room_entries],
        person_to_room=person_to_room,
        available=available,
        unavailable=unavailable,
        preferences=preferences,
        limit_one_day_per_person=limit_one_day,
    )
    st.caption(
        f"{context.month_name} {context.year} · {_answered_count(context)} of "
        f"{len(_rota_entries(context))} answered"
    )
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.caption("Nobody has answered yet.")


def _unassigned_people_with_room_numbers(unassigned_people: list[str], person_to_room: dict[str, str]) -> list[str]:
    people = []
    for person in unassigned_people:
        room = str(person_to_room.get(person, "")).strip()
        if room.isdigit():
            people.append(f"{person} ({room})")
    return people


def _weekday_label(weekday_name: str) -> str:
    return weekday_name[:1]


def format_day_label(year: int, month: int, day: int) -> str:
    weekday = ENGLISH_WEEKDAY_NAMES[calendar.weekday(year, month, day)]
    return f"{day}. {weekday.lower()}"


def parse_entry_days(value: str, year: int, month: int) -> set[int]:
    return set(parse_dates(split_date_input(value), year, month))


def format_days(days) -> str:
    return ", ".join(str(day) for day in days)


def _overview_days(days, empty_label: str = "None") -> str:
    normalized_days = [int(day) for day in days if str(day).strip()]
    if not normalized_days:
        return empty_label
    return format_days(sorted(normalized_days))


def planning_overview_rows(
    people_list: list[str],
    person_to_room: dict[str, str],
    available: dict[str, list[str]],
    unavailable: dict[str, list[str]],
    preferences: dict[str, list[int]],
    limit_one_day_per_person: dict[str, bool],
) -> list[dict[str, str]]:
    rows = []
    for person in people_list:
        if person not in person_to_room:
            continue

        person_available = available.get(person, [])
        person_unavailable = unavailable.get(person, [])
        can_host = _overview_days(person_available, "All possible dates" if not person_unavailable else "None")
        cannot_host = _overview_days(person_unavailable)
        preferred = _overview_days(preferences.get(person, []))

        rows.append(
            {
                "Person": person,
                "Room": person_to_room[person],
                "Can host": can_host,
                "Cannot host": cannot_host,
                "Preferred": preferred,
                "Host at most once": "Yes" if limit_one_day_per_person.get(person, False) else "No",
            }
        )

    return rows
