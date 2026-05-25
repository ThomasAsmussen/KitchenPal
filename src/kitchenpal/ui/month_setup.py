import calendar
from datetime import datetime, timedelta

import gspread
import streamlit as st

from ..constants import ENGLISH_MONTHS, MONTH_TO_NUMBER
from ..runtime_state import bump_cache_version, cache_key, get_cache_version
from ..scheduler import combine_availability, get_weekdays_in_month, parse_dates, schedule_people, split_date_input
from ..sheets.utils import parse_month_sheet_name
from ..sheets_service import PlanningEntry, SheetsService
from .errors import show_user_error, user_error_message

ENGLISH_WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DATE_CATEGORY_OPTIONS = {
    "available": "Can host food club",
    "unavailable": "Cannot host food club",
}


def _is_numeric_room_label(label: str) -> bool:
    return label.isdigit()


def _is_planner_room_entry(entry) -> bool:
    return entry.label.isdigit() or (entry.label.startswith("FL") and bool(entry.name))


def _month_sheet_names(sheet_names: list[str]) -> list[str]:
    return [sheet_name for sheet_name in sheet_names if parse_month_sheet_name(sheet_name) is not None]


def _month_sheet_for(month: int, year: int, sheet_names: list[str]) -> str | None:
    for sheet_name in sheet_names:
        if parse_month_sheet_name(sheet_name) == (month, year):
            return sheet_name
    return None


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


def _get_cached_possible_days_limit(service: SheetsService, month_name: str, year: int):
    key = cache_key("month_setup_possible_days_limit", month_name, year)
    if key not in st.session_state:
        st.session_state[key] = service.get_possible_days_limit(month_name, year)
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
                    show_user_error(st, exc, "Could not create the month sheet")

        st.header("Update new month from previous month")
        with st.form(key="update_month_form"):
            update_month = st.selectbox("Choose month ", ENGLISH_MONTHS, key="update_month")
            update_year = st.selectbox("Choose year ", [current_year, current_year + 1], key="update_year")

            if st.form_submit_button("Update month sheet"):
                try:
                    service.copy_balances_from_previous_month(update_month, update_year)
                    bump_cache_version()
                    st.success(f"Transferred balances to {update_month} {update_year}.")
                except ValueError as exc:
                    show_user_error(st, exc, "Could not update balances")

        st.header("Manage people in month")
        available_month_sheets = _month_sheet_names(_get_cached_sheet_names(service))
        if not available_month_sheets:
            st.warning("Create a month sheet before managing people.")
            return

        people_sheet = st.selectbox("Month sheet", available_month_sheets, key="manage_people_sheet")
        previous_people_sheet = service.previous_month_sheet_name(people_sheet)
        if previous_people_sheet:
            st.caption(f"Deletion balance check uses {previous_people_sheet}.")
        try:
            account_entries = service.get_personal_account_entries(people_sheet)
        except (ValueError, gspread.exceptions.WorksheetNotFound) as exc:
            show_user_error(st, exc, "Could not load people")
            account_entries = []

        room_entries = [entry for entry in account_entries if entry.label.isdigit()]
        fl_entries = [entry for entry in account_entries if entry.label.upper().startswith("FL")]
        named_fl_entries = [entry for entry in fl_entries if entry.name]

        if account_entries:
            st.table(
                [
                    {
                        "Account": entry.label,
                        "Name": entry.name,
                        "Balance": f"{entry.balance:.2f} DKK",
                    }
                    for entry in account_entries
                    if entry.label.isdigit() or entry.label.upper().startswith("FL")
                ]
            )

        with st.form(key=f"add_fl_person_form_{people_sheet}"):
            new_fl_person = st.text_input("New FL person", key=f"new_fl_person_{people_sheet}")
            if st.form_submit_button("Add as FL"):
                try:
                    fl_label = service.add_person_as_fl(people_sheet, new_fl_person)
                    bump_cache_version()
                    st.success(f"Added {new_fl_person.strip()} to {fl_label}.")
                    st.rerun()
                except (ValueError, gspread.exceptions.WorksheetNotFound) as exc:
                    show_user_error(st, exc, "Could not add FL person")

        if room_entries:
            with st.form(key=f"replace_room_person_form_{people_sheet}"):
                replacement_person = st.text_input(
                    "Person moving into room",
                    help="Use a new name or the exact name of a current FL person.",
                    key=f"replacement_person_{people_sheet}",
                )
                room_to_replace = st.selectbox(
                    "Room to take over",
                    room_entries,
                    format_func=lambda entry: f"{entry.label} — {entry.name or 'Empty'}",
                    key=f"room_to_replace_{people_sheet}",
                )
                if st.form_submit_button("Replace room person"):
                    try:
                        fl_label = service.replace_room_person(people_sheet, room_to_replace.label, replacement_person)
                        bump_cache_version()
                        st.success(f"Updated {room_to_replace.label}; moved the replaced person to {fl_label}.")
                        st.rerun()
                    except (ValueError, gspread.exceptions.WorksheetNotFound) as exc:
                        show_user_error(st, exc, "Could not replace room person")

        if named_fl_entries:
            with st.form(key=f"delete_fl_person_form_{people_sheet}"):
                fl_person_to_delete = st.selectbox(
                    "FL person to delete",
                    named_fl_entries,
                    format_func=lambda entry: f"{entry.label} — {entry.name} ({entry.balance:.2f} DKK)",
                    key=f"fl_person_to_delete_{people_sheet}",
                )
                if st.form_submit_button("Delete FL person"):
                    try:
                        service.delete_fl_person(
                            people_sheet,
                            fl_person_to_delete.name,
                            balance_source_worksheet_name=previous_people_sheet,
                        )
                        bump_cache_version()
                        st.success(f"Deleted {fl_person_to_delete.name} from {fl_person_to_delete.label}.")
                        st.rerun()
                    except (ValueError, gspread.exceptions.WorksheetNotFound) as exc:
                        show_user_error(st, exc, "Could not delete FL person")
        else:
            st.caption("No named FL accounts to delete.")


def render_availability_planner(service: SheetsService):
    st.header("Planning")
    st.markdown(_planning_responsive_style(), unsafe_allow_html=True)

    current_year = datetime.now().year
    next_month_date = datetime.now().replace(day=1) + timedelta(days=32)
    default_year = next_month_date.year
    default_month_index = next_month_date.month - 1

    year = st.number_input("Year", min_value=2024, max_value=current_year + 5, value=default_year, step=1)
    month_name = st.selectbox("Month", ENGLISH_MONTHS, index=default_month_index, key="planning_month")
    month = MONTH_TO_NUMBER[month_name]

    available_month_sheets = _month_sheet_names(_get_cached_sheet_names(service))
    if not available_month_sheets:
        st.warning("No month sheets are available yet.")
        return

    room_source_sheet = _month_sheet_for(month, int(year), available_month_sheets)
    if room_source_sheet is None:
        st.info(f"Create the {month_name} {int(year)} sheet before planning.")
        return

    st.caption(f"Room directory source: {room_source_sheet}")
    saved_limit_days = _get_cached_possible_days_limit(service, month_name, year)
    limit_days_input = st.text_input(
        "Limit days",
        value=saved_limit_days,
        placeholder="e.g. 1-20, 23-30",
        key=f"planning_limit_days_{year}_{month_name}_{get_cache_version()}",
    )
    if st.button("Save day limit", key=f"planning_save_limit_days_{year}_{month_name}"):
        try:
            service.save_possible_days_limit(month_name, year, limit_days_input)
            bump_cache_version()
            st.success(f"Saved possible days for {month_name} {int(year)}.")
            st.rerun()
        except ValueError as exc:
            show_user_error(st, exc, "Could not save possible days")

    try:
        room_entries = [entry for entry in _get_cached_room_entries(service, room_source_sheet) if _is_planner_room_entry(entry)]
    except gspread.exceptions.WorksheetNotFound as exc:
        show_user_error(st, exc, "Could not load room directory")
        st.info("Click Refresh data if the sheet was renamed or deleted directly in Google Sheets.")
        return
    planning_entries = _get_cached_planning_entries(service, month_name, year)
    stored_entries = {entry.person: entry for entry in planning_entries}
    people_list = [entry.name or entry.label for entry in room_entries]

    possible_days = get_weekdays_in_month(year, month)
    if limit_days_input.strip():
        try:
            limit_days = parse_dates(split_date_input(limit_days_input), year, month)
            possible_days = [day for day in possible_days if day in limit_days]
        except ValueError as exc:
            st.error(user_error_message(exc, "Could not read the day limit"))

    st.caption(f"Possible food club days in {month_name.lower()}: {', '.join(str(day) for day in possible_days)}")

    available = {}
    unavailable = {}
    preferences = {}
    limit_one_day_per_person = {}
    person_to_room = {}

    room_entry_by_name = {entry.name: entry for entry in room_entries if entry.name}
    room_entry_by_label = {entry.label: entry for entry in room_entries}

    if not people_list:
        st.warning("Add at least one person to create a schedule.")
        return

    for person in people_list:
        stored_entry = stored_entries.get(person)
        room_entry = room_entry_by_name.get(person) or room_entry_by_label.get(person)
        if room_entry is None:
            st.warning(f"Skipping {person}: no matching room entry was found.")
            continue

        cannot_host_default = not _is_numeric_room_label(room_entry.label)

        with st.expander(person):
            st.caption(f"Room: {room_entry.label}{f' — {room_entry.name}' if room_entry.name else ''}")
            person_to_room[person] = room_entry.label
            cannot_host_this_month = st.checkbox(
                "Cannot host food club this month",
                value=cannot_host_default,
                key=f"planning_cannot_host_{year}_{month_name}_{person}",
            )
            limit_one_day_per_person[person] = st.checkbox(
                "Max. 1 day",
                value=stored_entry.limit_one_day if stored_entry else False,
                disabled=cannot_host_this_month,
                key=f"planning_limit_{year}_{month_name}_{person}",
            )

            category_key = f"planning_date_category_{year}_{month_name}_{person}"
            if cannot_host_this_month:
                st.session_state[category_key] = "unavailable"
            date_category = st.radio(
                "The date means",
                list(DATE_CATEGORY_OPTIONS.keys()),
                format_func=lambda value: DATE_CATEGORY_OPTIONS[value],
                horizontal=True,
                disabled=cannot_host_this_month,
                key=category_key,
            )

            with st.form(key=f"planning_form_{year}_{month_name}_{person}"):
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
                save_request = st.form_submit_button("Save request")

            selected_days = normalize_planning_days(
                selected_days,
                selected_category=date_category,
                force_unavailable=cannot_host_this_month,
                possible_days=possible_days,
            )

            available[person] = [str(day) for day in selected_days["available"]]
            unavailable[person] = [str(day) for day in selected_days["unavailable"]]
            preferences[person] = selected_days["preferred"]

            if save_request:
                _sync_planning_day_state(
                    year=year,
                    month_name=month_name,
                    person=person,
                    selected_days=selected_days,
                )
                entry = PlanningEntry(
                    person=person,
                    room_number=person_to_room[person],
                    available_dates=format_days(available[person]),
                    unavailable_dates=format_days(unavailable[person]),
                    preferred_dates=format_days(preferences[person]),
                    limit_one_day=limit_one_day_per_person[person],
                )
                service.save_planning_entries(month_name, year, [entry])
                bump_cache_version()
                st.success(f"Saved requests for {person} in {month_name} {year}.")

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

    unassigned_room_people = _unassigned_people_with_room_numbers(schedule.unassigned_people, person_to_room)
    if unassigned_room_people:
        st.warning("Room-number people without a date: " + ", ".join(unassigned_room_people))

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

    stored_days = {
        "available": parse_entry_days(stored_entry.available_dates, year, month) if stored_entry else set(),
        "unavailable": parse_entry_days(stored_entry.unavailable_dates, year, month) if stored_entry else set(),
        "preferred": parse_entry_days(stored_entry.preferred_dates, year, month) if stored_entry else set(),
    }

    _initialize_planning_day_state(
        key_prefix=key_prefix,
        stored_days=stored_days,
        possible_day_set=possible_day_set,
        source_version=get_cache_version(),
    )

    if force_unavailable:
        signature_key = f"{key_prefix}_force_unavailable_signature"
        signature = tuple(possible_days)
        reset_widgets = st.session_state.get(signature_key) != signature
        _set_category_days(key_prefix, "available", [], reset_widgets=reset_widgets)
        _set_category_days(key_prefix, "preferred", [], reset_widgets=reset_widgets)
        _set_category_days(key_prefix, "unavailable", possible_days, reset_widgets=reset_widgets)
        st.session_state[signature_key] = signature
        selected_category = "unavailable"
    else:
        st.session_state.pop(f"{key_prefix}_force_unavailable_signature", None)

    picker_title = DATE_CATEGORY_OPTIONS[selected_category]
    with st.container(border=True):
        render_calendar_selector(
            title=picker_title,
            year=year,
            month=month,
            possible_day_set=possible_day_set,
            state_key=f"{key_prefix}_{selected_category}",
            disabled=force_unavailable,
        )

    with st.container(border=True):
        render_calendar_selector(
            "Preferred dates (optional)",
            year=year,
            month=month,
            possible_day_set=possible_day_set,
            state_key=f"{key_prefix}_preferred",
            disabled=force_unavailable,
        )

    return {
        "available": sorted(st.session_state[f"{key_prefix}_available"]),
        "unavailable": sorted(st.session_state[f"{key_prefix}_unavailable"]),
        "preferred": sorted(st.session_state[f"{key_prefix}_preferred"]),
    }


def normalize_planning_days(
    selected_days: dict[str, list[int]],
    selected_category: str,
    force_unavailable: bool,
    possible_days: list[int],
) -> dict[str, list[int]]:
    if force_unavailable:
        return {
            "available": [],
            "unavailable": sorted(possible_days),
            "preferred": [],
        }

    available_days = sorted(set(selected_days.get("available", [])))
    unavailable_days = sorted(set(selected_days.get("unavailable", [])))
    preferred_days = sorted(set(selected_days.get("preferred", [])))

    if selected_category == "available":
        unavailable_days = []
    elif selected_category == "unavailable":
        available_days = []

    return {
        "available": available_days,
        "unavailable": unavailable_days,
        "preferred": preferred_days,
    }


def _unassigned_people_with_room_numbers(unassigned_people: list[str], person_to_room: dict[str, str]) -> list[str]:
    people = []
    for person in unassigned_people:
        room = str(person_to_room.get(person, "")).strip()
        if room.isdigit():
            people.append(f"{person} ({room})")
    return people


def _initialize_planning_day_state(
    key_prefix: str,
    stored_days: dict[str, set[int]],
    possible_day_set: set[int],
    source_version: int,
) -> None:
    source_key = f"{key_prefix}_source_version"
    reset_from_source = st.session_state.get(source_key) != source_version

    for category, days in stored_days.items():
        state_key = f"{key_prefix}_{category}"
        if reset_from_source or state_key not in st.session_state:
            _set_category_days(
                key_prefix,
                category,
                sorted(day for day in days if day in possible_day_set),
                reset_widgets=reset_from_source,
            )

    st.session_state[source_key] = source_version


def _sync_planning_day_state(year: int, month_name: str, person: str, selected_days: dict[str, list[int]]) -> None:
    key_prefix = f"planning_dates_{year}_{month_name}_{person}"
    for category, days in selected_days.items():
        _set_category_days(key_prefix, category, days, reset_widgets=True)


def _set_category_days(key_prefix: str, category: str, days, reset_widgets: bool = False) -> None:
    day_set = set(days)
    state_key = f"{key_prefix}_{category}"
    st.session_state[state_key] = sorted(day_set)
    if reset_widgets:
        st.session_state[_calendar_widget_version_key(state_key)] = st.session_state.get(
            _calendar_widget_version_key(state_key), 0
        ) + 1


def _calendar_widget_version_key(state_key: str) -> str:
    return f"{state_key}_widget_version"


def _calendar_widget_key(state_key: str, day: int) -> str:
    version = st.session_state.get(_calendar_widget_version_key(state_key), 0)
    return f"{state_key}_v{version}_{day}"


def render_calendar_selector(
    title: str,
    year: int,
    month: int,
    possible_day_set: set[int],
    state_key: str,
    disabled: bool = False,
):
    st.markdown(f"**{title}**")
    selected_days = set(st.session_state[state_key])

    header_columns = st.columns(7)
    for index, weekday_name in enumerate(ENGLISH_WEEKDAY_NAMES):
        header_columns[index].markdown(f"**{_weekday_label(weekday_name)}**")

    month_calendar = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
    for week in month_calendar:
        columns = st.columns(7)
        for index, day in enumerate(week):
            with columns[index]:
                if day == 0:
                    st.write("")
                    continue

                st.markdown(f"<div style='text-align:center; font-size:0.9rem; font-weight:600; line-height:1; margin-bottom:0.2rem;'>{day}</div>", unsafe_allow_html=True)
                checked = st.checkbox(
                    " ",
                    value=day in selected_days,
                    disabled=disabled or day not in possible_day_set,
                    label_visibility="collapsed",
                    key=_calendar_widget_key(state_key, day),
                )
                if day not in possible_day_set:
                    continue
                if checked:
                    selected_days.add(day)
                else:
                    selected_days.discard(day)

    st.session_state[state_key] = sorted(selected_days)


def _planning_responsive_style() -> str:
    return """
<style>
@media (max-width: 900px) {
    div[data-testid="stHorizontalBlock"]:has(div[data-testid="stHorizontalBlock"]) {
        flex-direction: column;
        gap: 1rem;
    }

    div[data-testid="stHorizontalBlock"]:has(div[data-testid="stHorizontalBlock"]) > div[data-testid="column"] {
        width: 100% !important;
        flex: 1 1 100% !important;
        min-width: 0 !important;
    }
}
</style>
"""


def _weekday_label(weekday_name: str) -> str:
    return weekday_name[:1]


def format_day_label(year: int, month: int, day: int) -> str:
    weekday = ENGLISH_WEEKDAY_NAMES[calendar.weekday(year, month, day)]
    return f"{day}. {weekday.lower()}"


def parse_entry_days(value: str, year: int, month: int) -> set[int]:
    return set(parse_dates(split_date_input(value), year, month))


def format_days(days) -> str:
    return ", ".join(str(day) for day in days)
