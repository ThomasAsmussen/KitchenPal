import calendar
from datetime import datetime, timedelta

import streamlit as st

from ..constants import ENGLISH_MONTHS, MONTH_TO_NUMBER
from ..runtime_state import bump_cache_version, cache_key
from ..scheduler import combine_availability, get_weekdays_in_month, parse_dates, schedule_people, split_date_input
from ..sheets_service import PlanningEntry, SheetsService


PLANNING_SHEET_NAME = "Planning"

ENGLISH_WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DATE_CATEGORY_OPTIONS = {
    "available": "Can host food club",
    "unavailable": "Cannot host food club",
}


def _is_numeric_room_label(label: str) -> bool:
    return label.isdigit()


def _room_display_label(label: str, name: str) -> str:
    return f"{label} — {name}" if name else label


def _get_cached_room_entries(service: SheetsService, worksheet_name: str):
    key = cache_key("month_setup_room_entries", worksheet_name)
    if key not in st.session_state:
        st.session_state[key] = service.get_room_entries(worksheet_name)
    return st.session_state[key]


def _get_cached_planning_entries(service: SheetsService, month_name: str, year: int):
    key = cache_key("month_setup_planning_entries", month_name, year)
    if key not in st.session_state:
        st.session_state[key] = service.get_planning_entries(month_name, year)
    return st.session_state[key]


def _get_cached_sheet_names(service: SheetsService):
    key = cache_key("month_setup_sheet_names")
    if key not in st.session_state:
        st.session_state[key] = service.list_sheets()
    return st.session_state[key]


def render_month_setup_view(service: SheetsService):
    st.title("Create New Month")

    refresh_clicked = st.sidebar.button("Refresh data", key="month_setup_refresh")
    if refresh_clicked:
        bump_cache_version()
        st.rerun()

    availability_tab, month_tab = st.tabs(["Choose when you can host food club", "Create new month"])

    with availability_tab:
        render_availability_planner(service)

    with month_tab:
        st.header("Add new month")
        current_year = datetime.now().year

        with st.form(key="create_month_form"):
            month = st.selectbox("Choose month", ENGLISH_MONTHS, key="new_month")
            year = st.selectbox("Choose year", [current_year, current_year + 1], key="new_year")

            if st.form_submit_button("Add new month"):
                try:
                    service.create_month_sheet(month, year)
                    bump_cache_version()
                    st.success(f"New sheet created: {month} {year}")
                except ValueError as exc:
                    st.error(str(exc))

        st.header("Update new month from previous month")
        with st.form(key="update_month_form"):
            update_month = st.selectbox("Choose month ", ENGLISH_MONTHS, key="update_month")
            update_year = st.selectbox("Choose year ", [current_year, current_year + 1], key="update_year")

            if st.form_submit_button("Update month sheet"):
                service.copy_balances_from_previous_month(update_month, update_year)
                bump_cache_version()
                st.success(f"Transferred balances to {update_month} {update_year}.")


def render_availability_planner(service: SheetsService):
    st.header("Planning")

    current_year = datetime.now().year
    next_month_date = datetime.now().replace(day=1) + timedelta(days=32)
    default_year = next_month_date.year
    default_month_index = next_month_date.month - 1
    settings_col, people_col = st.columns([1, 2])

    with settings_col:
        year = st.number_input("Year", min_value=2024, max_value=current_year + 5, value=default_year, step=1)
        month_name = st.selectbox("Month", ENGLISH_MONTHS, index=default_month_index, key="planning_month")
        month = MONTH_TO_NUMBER[month_name]
        limit_days_input = st.text_input("Limit days", placeholder="e.g. 1-10, 27-30, Thursday")

    available_month_sheets = [sheet_name for sheet_name in _get_cached_sheet_names(service) if sheet_name != PLANNING_SHEET_NAME]
    default_room_source = f"{month_name} {int(year)}"
    if default_room_source not in available_month_sheets and available_month_sheets:
        default_room_source = available_month_sheets[0]

    if not available_month_sheets:
        st.warning("No month sheets are available yet.")
        return

    room_source_sheet = st.selectbox(
        "Room directory source",
        available_month_sheets,
        index=available_month_sheets.index(default_room_source) if default_room_source in available_month_sheets else 0,
        key=f"planning_room_source_{month_name}_{year}",
    )

    room_entries = _get_cached_room_entries(service, room_source_sheet)
    planning_entries = _get_cached_planning_entries(service, month_name, year)
    stored_entries = {entry.person: entry for entry in planning_entries}
    default_people = ", ".join(entry.name or entry.label for entry in room_entries)

    with people_col:
        people = st.text_area("Names, separated by commas", default_people, height=96, key=f"planning_people_{year}_{month_name}")
        people_list = [person.strip() for person in people.split(",") if person.strip()]

    possible_days = get_weekdays_in_month(year, month)
    if limit_days_input.strip():
        try:
            limit_days = parse_dates(split_date_input(limit_days_input), year, month)
            possible_days = [day for day in possible_days if day in limit_days]
        except ValueError as exc:
            st.error(f"Could not read the day limit: {exc}")

    st.caption(f"Possible food club days in {month_name.lower()}: {', '.join(str(day) for day in possible_days)}")

    available = {}
    unavailable = {}
    preferences = {}
    limit_one_day_per_person = {}
    person_to_room = {}

    room_entry_by_name = {entry.name: entry for entry in room_entries if entry.name}
    room_entry_by_label = {entry.label: entry for entry in room_entries}
    available_room_labels = [entry.label for entry in room_entries]

    if not people_list:
        st.warning("Add at least one person to create a schedule.")
        return

    with st.form(key=f"planning_form_{year}_{month_name}"):
        for person in people_list:
            stored_entry = stored_entries.get(person)
            default_room = stored_entry.room_number if stored_entry and stored_entry.room_number else room_entry_by_name.get(person, room_entries[0]).label
            default_room_index = available_room_labels.index(default_room) if default_room in available_room_labels else 0
            cannot_host_default = not _is_numeric_room_label(default_room)

            with st.expander(person):
                person_to_room[person] = st.selectbox(
                    "Room",
                    available_room_labels,
                    index=default_room_index,
                    format_func=lambda label: _room_display_label(label, room_entry_by_label[label].name if label in room_entry_by_label else ""),
                    key=f"planning_room_{year}_{month_name}_{person}",
                )
                cannot_host_this_month = st.checkbox(
                    "Cannot host food club this month",
                    value=cannot_host_default,
                    key=f"planning_cannot_host_{year}_{month_name}_{person}",
                )
                limit_one_day_per_person[person] = st.checkbox(
                    "Max. 1 day",
                    value=stored_entry.limit_one_day if stored_entry else False,
                    key=f"planning_limit_{year}_{month_name}_{person}",
                )
                date_category = st.radio(
                    "The date means",
                    list(DATE_CATEGORY_OPTIONS.keys()),
                    format_func=lambda value: DATE_CATEGORY_OPTIONS[value],
                    horizontal=True,
                    key=f"planning_date_category_{year}_{month_name}_{person}",
                )
                selected_days = render_date_picker(
                    person=person,
                    year=year,
                    month=month,
                    month_name=month_name,
                    possible_days=possible_days,
                    selected_category=date_category,
                    stored_entry=stored_entry,
                    force_unavailable=cannot_host_this_month,
                )

                available[person] = [str(day) for day in selected_days["available"]]
                unavailable[person] = [str(day) for day in selected_days["unavailable"]]
                preferences[person] = selected_days["preferred"]

        save_clicked = st.form_submit_button("Save requests")

    entries = [
        PlanningEntry(
            person=person,
            room_number=person_to_room[person],
            available_dates=format_days(available[person]),
            unavailable_dates=format_days(unavailable[person]),
            preferred_dates=format_days(preferences[person]),
            limit_one_day=limit_one_day_per_person[person],
        )
        for person in people_list
    ]

    if save_clicked:
        service.save_planning_entries(month_name, year, entries)
        bump_cache_version()
        st.success(f"Saved requests for {month_name} {year}.")

    schedule_key = f"planning_schedule_{year}_{month_name}"
    schedule_col = st.container()
    with schedule_col:
        if st.button("Create schedule", key=f"planning_create_schedule_{year}_{month_name}"):
            available_days = combine_availability(available, unavailable, year, month)
            try:
                schedule = schedule_people(available_days, preferences, possible_days, limit_one_day_per_person)
            except ModuleNotFoundError as exc:
                if exc.name != "ortools":
                    raise
                st.error("Scheduling requires the 'ortools' package. Reinstall dependencies with `pip install -r requirements.txt`.")
                return

            st.session_state[schedule_key] = schedule

    if schedule_key not in st.session_state:
        return

    schedule = st.session_state[schedule_key]
    if schedule is None:
        st.header("Suggested Schedule")
        st.warning("No feasible schedule could be created with the selected constraints.")
        return

    st.header("Suggested Schedule")

    schedule_rows = [
        {
            "Day": day,
            "Weekday": ENGLISH_WEEKDAY_NAMES[calendar.weekday(year, month, day)],
            "Person": person,
            "Room": person_to_room.get(person),
        }
        for day, person in schedule.assignments.items()
    ]
    st.dataframe(schedule_rows, hide_index=True, use_container_width=True)

    if schedule.unassigned_people:
        st.info("Not assigned: " + ", ".join(schedule.unassigned_people))

    missing_rooms = sorted({person for person in schedule.assignments.values() if person not in person_to_room})
    month_sheet_name = f"{month_name} {year}"
    if st.button("Write schedule to month sheet", key=f"planning_write_{year}_{month_name}"):
        if missing_rooms:
            st.error("Missing room for: " + ", ".join(missing_rooms))
            return

        service.populate_cooks_for_month(month_sheet_name, schedule.assignments, person_to_room)
        bump_cache_version()
        st.success(f"Wrote rooms to {month_sheet_name}.")


def render_date_picker(
    person: str,
    year: int,
    month: int,
    month_name: str,
    possible_days: list[int],
    selected_category: str,
    stored_entry: PlanningEntry | None,
    force_unavailable: bool,
) -> dict[str, list[int]]:
    key_prefix = f"planning_dates_{year}_{month_name}_{person}"
    possible_day_set = set(possible_days)
    days_in_month = calendar.monthrange(year, month)[1]

    stored_days = {
        "available": parse_entry_days(stored_entry.available_dates, year, month) if stored_entry else set(),
        "unavailable": parse_entry_days(stored_entry.unavailable_dates, year, month) if stored_entry else set(),
        "preferred": parse_entry_days(stored_entry.preferred_dates, year, month) if stored_entry else set(),
    }

    if force_unavailable and f"{key_prefix}_unavailable" not in st.session_state:
        st.session_state[f"{key_prefix}_available"] = []
        st.session_state[f"{key_prefix}_unavailable"] = sorted(possible_day_set)
        st.session_state[f"{key_prefix}_preferred"] = []

    for category, days in stored_days.items():
        key = f"{key_prefix}_{category}"
        if key not in st.session_state:
            st.session_state[key] = sorted(day for day in days if day in possible_day_set)

    picker_col, preferred_col = st.columns(2)

    with picker_col:
        picker_title = DATE_CATEGORY_OPTIONS["unavailable"] if force_unavailable else DATE_CATEGORY_OPTIONS[selected_category]
        with st.container(border=True):
            render_calendar_selector(
                title=picker_title,
                year=year,
                month=month,
                possible_day_set=possible_day_set,
                state_key=f"{key_prefix}_{selected_category}",
            )

    with preferred_col:
        with st.container(border=True):
            render_calendar_selector(
                "Preferred dates (optional)",
                year=year,
                month=month,
                possible_day_set=possible_day_set,
                state_key=f"{key_prefix}_preferred",
            )

    return {
        "available": sorted(st.session_state[f"{key_prefix}_available"]),
        "unavailable": sorted(st.session_state[f"{key_prefix}_unavailable"]),
        "preferred": sorted(st.session_state[f"{key_prefix}_preferred"]),
    }


def render_calendar_selector(title: str, year: int, month: int, possible_day_set: set[int], state_key: str):
    st.markdown(f"**{title}**")
    selected_days = set(st.session_state[state_key])

    header_columns = st.columns(7)
    for index, weekday_name in enumerate(ENGLISH_WEEKDAY_NAMES):
        header_columns[index].markdown(f"**{weekday_name[:3]}**")

    month_calendar = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
    for week in month_calendar:
        columns = st.columns(7)
        for index, day in enumerate(week):
            with columns[index]:
                if day == 0:
                    st.write("")
                    continue

                checked = st.checkbox(
                    str(day),
                    value=day in selected_days,
                    disabled=day not in possible_day_set,
                    key=f"{state_key}_{day}",
                )
                if day not in possible_day_set:
                    continue
                if checked:
                    selected_days.add(day)
                else:
                    selected_days.discard(day)

    st.session_state[state_key] = sorted(selected_days)


def format_day_label(year: int, month: int, day: int) -> str:
    weekday = ENGLISH_WEEKDAY_NAMES[calendar.weekday(year, month, day)]
    return f"{day}. {weekday.lower()}"


def parse_entry_days(value: str, year: int, month: int) -> set[int]:
    return set(parse_dates(split_date_input(value), year, month))


def format_days(days) -> str:
    return ", ".join(str(day) for day in days)
