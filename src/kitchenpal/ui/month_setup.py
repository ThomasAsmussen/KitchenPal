import calendar
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import gspread
import streamlit as st

from ..constants import ENGLISH_MONTHS, MONTH_TO_NUMBER
from ..runtime_state import bump_cache_version, cache_key, get_cache_version
from ..scheduler import combine_availability, get_weekdays_in_month, parse_dates, schedule_people, split_date_input
from ..sheets.utils import parse_month_sheet_name
from ..sheets_service import PlanningEntry, SheetsService
from .day_to_day import render_kitchen_fund_view
from .errors import show_user_error, user_error_message

ENGLISH_WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DATE_CATEGORY_OPTIONS = {
    "available": "I can host on these dates",
    "unavailable": "I cannot host on these dates",
}


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


def _render_refresh_button(key: str):
    loaded_at_key = f"{key}_loaded_at:{get_cache_version()}"
    if loaded_at_key not in st.session_state:
        st.session_state[loaded_at_key] = datetime.now(ZoneInfo("Europe/Copenhagen")).strftime("%H:%M")
    col1, col2 = st.columns([1, 4])
    if col1.button("Refresh data", key=key):
        bump_cache_version()
        st.rerun()
    col2.caption(f"Loaded from Google Sheets at {st.session_state[loaded_at_key]}.")


def render_planning_view(service: SheetsService):
    st.title("Planning")
    _render_refresh_button("planning_refresh")
    render_availability_planner(service)


def render_admin_view(service: SheetsService):
    st.title("Admin")
    _render_refresh_button("admin_refresh")
    month_tab, people_tab, fund_tab = st.tabs(["Month setup", "People", "Kitchen fund payments"])

    with month_tab:
        render_month_creation_section(service)

    with people_tab:
        render_people_management_section(service)

    with fund_tab:
        render_kitchen_fund_view(service, embedded=True)


def render_month_setup_view(service: SheetsService):
    render_admin_view(service)


def _previous_month_and_year(month_number: int, year: int) -> tuple[str, int]:
    previous_index = (month_number - 2) % 12
    previous_year = year - 1 if month_number == 1 else year
    return ENGLISH_MONTHS[previous_index], previous_year


def render_month_creation_section(service: SheetsService):
    st.header("1. Create a month sheet")
    current_year = datetime.now().year

    with st.form(key="create_month_form"):
        month = st.selectbox("Month to create", ENGLISH_MONTHS, key="new_month")
        year = st.selectbox("Year", [current_year, current_year + 1], key="new_year")
        st.caption("This duplicates the template sheet. Copy balances in the next step after the sheet exists.")
        submitted = st.form_submit_button("Create month sheet")

    if submitted:
        try:
            service.create_month_sheet(month, year)
            bump_cache_version()
            st.session_state["manage_people_preferred_month"] = (MONTH_TO_NUMBER[month], year)
            st.success(f"New sheet created: {month} {year}")
            for problem in service.check_month_sheet_integrity(f"{month} {year}"):
                st.warning(problem)
        except ValueError as exc:
            show_user_error(st, exc, "Could not create the month sheet")

    st.header("2. Copy names and balances from last month")
    # No st.form here: the checkbox must rerun the script to re-enable the
    # button, and the label must follow the selected month — form widgets do
    # neither until submit, which deadlocks a disabled submit button.
    update_month = st.selectbox("Month to update", ENGLISH_MONTHS, key="update_month")
    update_year = st.selectbox("Year ", [current_year, current_year + 1], key="update_year")
    previous_month_name, previous_month_year = _previous_month_and_year(MONTH_TO_NUMBER[update_month], update_year)
    confirm_copy = st.checkbox(
        f"I have checked that the {update_month} {update_year} sheet exists and should "
        f"receive the balances from {previous_month_name} {previous_month_year}.",
        key="confirm_copy_balances",
    )
    submitted = st.button("Copy names and balances", key="copy_balances_button", disabled=not confirm_copy)

    if submitted:
        try:
            report = service.copy_balances_from_previous_month(update_month, update_year)
            bump_cache_version()
            st.session_state["manage_people_preferred_month"] = (MONTH_TO_NUMBER[update_month], update_year)
            st.success(f"Copied names and balances to {update_month} {update_year}.")
            for name, balance, fl_label in report.chased:
                st.info(f"{name} no longer has a room — their {balance:.2f} DKK balance was moved to {fl_label}.")
            for name, balance in report.unplaced:
                st.warning(
                    f"No free FL slot for {name} ({balance:.2f} DKK) — their balance was NOT carried over. "
                    "Settle and delete an FL person, then run the copy again."
                )
            for label, previous_name, current_name in report.suspected_renames:
                st.warning(
                    f"Room {label}: '{current_name}' replaced '{previous_name}', who still has money outstanding. "
                    f"If this is the same person misspelled, fix the name in room {label} and clear the FL row, "
                    "then run the copy again."
                )
            for name in report.duplicate_names:
                st.warning(f"'{name}' appears in more than one row — check the sheet before trusting the balances.")
        except ValueError as exc:
            show_user_error(st, exc, "Could not copy names and balances")


def render_people_management_section(service: SheetsService):
    st.header("People in a month")
    available_month_sheets = _month_sheet_names(_get_cached_sheet_names(service))
    if not available_month_sheets:
        st.warning("Create a month sheet before managing people.")
        return

    preferred_month = st.session_state.pop("manage_people_preferred_month", None)
    preferred_people_sheet = (
        _month_sheet_for(preferred_month[0], preferred_month[1], available_month_sheets) if preferred_month else None
    )
    if preferred_people_sheet:
        st.session_state["manage_people_sheet"] = preferred_people_sheet
    people_sheet_index = (
        available_month_sheets.index(preferred_people_sheet)
        if preferred_people_sheet in available_month_sheets
        else 0
    )
    people_sheet = st.selectbox(
        "Month sheet",
        available_month_sheets,
        index=people_sheet_index,
        key="manage_people_sheet",
    )
    try:
        account_entries = service.get_personal_account_entries(people_sheet)
    except (ValueError, gspread.exceptions.WorksheetNotFound) as exc:
        show_user_error(st, exc, "Could not load people")
        account_entries = []

    room_entries = [entry for entry in account_entries if entry.label.isdigit()]
    fl_entries = [entry for entry in account_entries if entry.label.upper().startswith("FL")]
    named_fl_entries = [entry for entry in fl_entries if entry.name]
    person_account_entries = [entry for entry in account_entries if entry.label.isdigit() or entry.label.upper().startswith("FL")]
    named_person_account_entries = [entry for entry in person_account_entries if entry.name]

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

    if named_person_account_entries and person_account_entries:
        with st.form(key=f"move_person_form_{people_sheet}"):
            person_to_move = st.selectbox(
                "Person to move",
                named_person_account_entries,
                format_func=lambda entry: f"{entry.label} — {entry.name}",
                key=f"person_to_move_{people_sheet}",
            )
            destination_account = st.selectbox(
                "Move to account",
                person_account_entries,
                index=1 if len(person_account_entries) > 1 else 0,
                format_func=lambda entry: f"{entry.label} — {entry.name or 'Empty'}",
                key=f"destination_account_{people_sheet}",
            )
            st.caption("If the destination already has a person, the two people swap accounts.")
            if st.form_submit_button("Move person"):
                try:
                    service.move_person_between_accounts(people_sheet, person_to_move.label, destination_account.label)
                    bump_cache_version()
                    st.success(f"Moved {person_to_move.name} to {destination_account.label}.")
                    st.rerun()
                except (ValueError, gspread.exceptions.WorksheetNotFound) as exc:
                    show_user_error(st, exc, "Could not move person")

    named_room_entries = [entry for entry in room_entries if entry.name]
    if named_room_entries:
        with st.form(key=f"move_out_form_{people_sheet}"):
            person_moving_out = st.selectbox(
                "Person moving out",
                named_room_entries,
                format_func=lambda entry: f"{entry.label} — {entry.name} ({entry.balance:.2f} DKK)",
                key=f"person_moving_out_{people_sheet}",
            )
            st.caption("A non-zero tab is parked in an FL slot and chased; a settled tab just frees the room.")
            if st.form_submit_button("Move person out"):
                try:
                    fl_label = service.move_person_out(people_sheet, person_moving_out.label)
                    bump_cache_version()
                    if fl_label:
                        st.success(f"Moved {person_moving_out.name} out of {person_moving_out.label}; balance parked at {fl_label}.")
                    else:
                        st.success(f"Moved {person_moving_out.name} out of {person_moving_out.label}; nothing to chase.")
                    st.rerun()
                except (ValueError, gspread.exceptions.WorksheetNotFound) as exc:
                    show_user_error(st, exc, "Could not move person out")

    with st.form(key=f"add_fl_person_form_{people_sheet}"):
        new_fl_person = st.text_input(
            "New person arriving (parked in FL1-FL3 until next month)",
            help="Mid-month arrivals stay in an FL slot for the rest of the month and move into their room at the next rollover.",
            key=f"new_fl_person_{people_sheet}",
        )
        intended_room = st.selectbox(
            "Room they take over at the next rollover (optional)",
            [""] + [entry.label for entry in room_entries],
            key=f"intended_room_{people_sheet}",
        )
        if st.form_submit_button("Park arriving person"):
            try:
                fl_label = service.add_person_as_fl(people_sheet, new_fl_person, intended_room=intended_room)
                bump_cache_version()
                st.success(f"Added {new_fl_person.strip()} to {fl_label}.")
                st.rerun()
            except (ValueError, gspread.exceptions.WorksheetNotFound) as exc:
                show_user_error(st, exc, "Could not add person")

    if room_entries:
        with st.form(key=f"replace_room_person_form_{people_sheet}"):
            replacement_person = st.text_input(
                "New person moving into a room",
                help="Use a new name. To move someone already listed, use Move person.",
                key=f"replacement_person_{people_sheet}",
            )
            room_to_replace = st.selectbox(
                "Room",
                room_entries,
                format_func=lambda entry: f"{entry.label} — {entry.name or 'Empty'}",
                key=f"room_to_replace_{people_sheet}",
            )
            if st.form_submit_button("Add or replace room person"):
                try:
                    fl_label = service.replace_room_person(people_sheet, room_to_replace.label, replacement_person)
                    bump_cache_version()
                    if room_to_replace.name:
                        st.success(f"Updated {room_to_replace.label}; moved the replaced person to {fl_label}.")
                    else:
                        st.success(f"Added {replacement_person.strip()} to {room_to_replace.label}.")
                    st.rerun()
                except (ValueError, gspread.exceptions.WorksheetNotFound) as exc:
                    show_user_error(st, exc, "Could not update room person")

    if named_fl_entries:
        previous_sheet_name = service.previous_month_sheet_name(people_sheet)
        if previous_sheet_name:
            st.caption(f"Deleting checks that both the {people_sheet} and {previous_sheet_name} balances are 0 DKK.")
        else:
            st.caption(f"No previous month sheet found — only the {people_sheet} balance is checked before deleting.")
        with st.form(key=f"delete_fl_person_form_{people_sheet}"):
            fl_person_to_delete = st.selectbox(
                "Person without a room to delete",
                named_fl_entries,
                format_func=lambda entry: f"{entry.label} — {entry.name} ({entry.balance:.2f} DKK)",
                key=f"fl_person_to_delete_{people_sheet}",
            )
            if st.form_submit_button("Delete person without a room"):
                try:
                    service.delete_fl_person(people_sheet, fl_person_to_delete.name)
                    bump_cache_version()
                    st.success(f"Deleted {fl_person_to_delete.name} from {fl_person_to_delete.label}.")
                    st.rerun()
                except (ValueError, gspread.exceptions.WorksheetNotFound) as exc:
                    show_user_error(st, exc, "Could not delete person")
    else:
        st.caption("No named accounts without rooms to delete.")


def render_availability_planner(service: SheetsService):
    st.header("Host schedule")
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

    st.caption(f"People are loaded from: {room_source_sheet}")
    saved_limit_days = _get_cached_possible_days_limit(service, month_name, year)
    limit_days_input = st.text_input(
        "Food club can only happen on these dates",
        value=saved_limit_days,
        placeholder="e.g. 1-20, 23-30",
        help="Leave blank to allow every normal food club day. You can enter dates, ranges, or weekday names.",
        key=f"planning_limit_days_{year}_{month_name}_{get_cache_version()}",
    )
    if st.button("Save possible food club dates", key=f"planning_save_limit_days_{year}_{month_name}"):
        try:
            service.save_possible_days_limit(month_name, year, limit_days_input)
            bump_cache_version()
            st.success(f"Saved possible food club dates for {month_name} {int(year)}.")
            st.rerun()
        except ValueError as exc:
            show_user_error(st, exc, "Could not save possible food club dates")

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

    st.caption(f"Possible food club dates in {month_name.lower()}: {', '.join(str(day) for day in possible_days)}")

    available = {}
    unavailable = {}
    preferences = {}
    limit_one_day_per_person = {}
    person_to_room = {}

    room_entry_by_name = {entry.name: entry for entry in room_entries if entry.name}
    room_entry_by_label = {entry.label: entry for entry in room_entries}
    control_version = get_cache_version()

    if not people_list:
        st.warning("Add at least one person to create a schedule.")
        return

    for person in people_list:
        stored_entry = stored_entries.get(person)
        room_entry = room_entry_by_name.get(person) or room_entry_by_label.get(person)
        if room_entry is None:
            st.warning(f"Skipping {person}: no matching room entry was found.")
            continue

        cannot_host_default = _default_cannot_host_this_month(
            room_entry.label,
            stored_entry,
            possible_days,
            year,
            month,
        )

        with st.expander(person):
            st.caption(f"Room: {room_entry.label}{f' — {room_entry.name}' if room_entry.name else ''}")
            person_to_room[person] = room_entry.label
            cannot_host_this_month = st.checkbox(
                "Cannot host food club this month",
                value=cannot_host_default,
                key=f"planning_cannot_host_{year}_{month_name}_{person}_{control_version}",
            )
            limit_one_day_per_person[person] = st.checkbox(
                "Host at most once this month",
                value=stored_entry.limit_one_day if stored_entry else False,
                disabled=cannot_host_this_month,
                key=f"planning_limit_{year}_{month_name}_{person}_{control_version}",
            )

            category_key = f"planning_date_category_{year}_{month_name}_{person}_{control_version}"
            if cannot_host_this_month:
                st.session_state[category_key] = "unavailable"
            elif category_key not in st.session_state:
                st.session_state[category_key] = _default_date_category(stored_entry, year, month)
            date_category = st.radio(
                "The selected dates mean",
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
                save_request = st.form_submit_button("Save availability")

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
                st.success(f"Saved availability for {person} in {month_name} {year}.")

    overview_rows = planning_overview_rows(
        people_list=people_list,
        person_to_room=person_to_room,
        available=available,
        unavailable=unavailable,
        preferences=preferences,
        limit_one_day_per_person=limit_one_day_per_person,
    )
    if overview_rows:
        st.header("Availability overview")
        st.dataframe(overview_rows, hide_index=True, use_container_width=True)

    schedule_key = f"planning_schedule_{year}_{month_name}"
    schedule_col = st.container()
    with schedule_col:
        st.caption("Schedule generation uses the availability currently shown above, including unsaved changes.")
        if st.button("Generate host schedule", key=f"planning_create_schedule_{year}_{month_name}"):
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
        st.header("Suggested host schedule")
        st.warning("No feasible schedule could be created with the selected constraints.")
        return

    st.header("Suggested host schedule")

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
        st.info("People not assigned: " + ", ".join(schedule.unassigned_people))

    unassigned_room_people = _unassigned_people_with_room_numbers(schedule.unassigned_people, person_to_room)
    if unassigned_room_people:
        st.warning("Room residents without a host date: " + ", ".join(unassigned_room_people))

    missing_rooms = sorted({person for person in schedule.assignments.values() if person not in person_to_room})
    confirm_write = st.checkbox(
        f"I have reviewed the schedule and want to write these hosts to {room_source_sheet}.",
        key=f"planning_confirm_write_{year}_{month_name}",
    )
    if st.button("Write hosts to month sheet", key=f"planning_write_{year}_{month_name}", disabled=not confirm_write):
        if missing_rooms:
            st.error("Missing room for: " + ", ".join(missing_rooms))
            return

        service.populate_cooks_for_month(room_source_sheet, schedule.assignments, person_to_room)
        bump_cache_version()
        st.success(f"Wrote hosts to {room_source_sheet}.")


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
    selected_days = set(st.session_state[state_key])

    # The keyed container emits a stable `st-key-kpalcal_*` class that the
    # responsive CSS targets, so the styling cannot silently detach when
    # Streamlit renames its internal test ids.
    with st.container(key=f"kpalcal_{state_key}"):
        st.markdown(f"**{title}**")

        header_columns = st.columns(7)
        for index, weekday_name in enumerate(ENGLISH_WEEKDAY_NAMES):
            header_columns[index].markdown(f"<div class='kpal-weekday'>{_weekday_label(weekday_name)}</div>", unsafe_allow_html=True)

        month_calendar = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
        for week in month_calendar:
            columns = st.columns(7)
            for index, day in enumerate(week):
                with columns[index]:
                    if day == 0:
                        st.write("")
                        continue

                    st.markdown(f"<div class='kpal-day-number'>{day}</div>", unsafe_allow_html=True)
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
    # Scoped to the `st-key-kpalcal_*` class emitted by the keyed containers in
    # render_calendar_selector — our own hook, not a Streamlit internal. Only
    # the inner stHorizontalBlock/stColumn/stCheckbox test ids are Streamlit's.
    # Desktop (>900px) is untouched; on phones the flex columns would stack
    # into one full-width cell per row, so the grid is forced instead and the
    # checkbox tap area is stretched to the full cell width at thumb size.
    return """
<style>
@media (max-width: 900px) {
    [class*="st-key-kpalcal"] div[data-testid="stHorizontalBlock"] {
        display: grid !important;
        grid-template-columns: repeat(7, minmax(0, 1fr)) !important;
        gap: 0.15rem !important;
        align-items: stretch;
    }

    [class*="st-key-kpalcal"] div[data-testid="stColumn"] {
        min-width: 0 !important;
        width: auto !important;
        flex: none !important;
    }

    [class*="st-key-kpalcal"] div[data-testid="stColumn"] > div {
        border: 1px solid rgba(49, 51, 63, 0.2);
        border-radius: 0.25rem;
        min-height: 3.2rem;
        box-sizing: border-box;
        gap: 0 !important;
        padding: 0.1rem 0;
    }

    [class*="st-key-kpalcal"] .kpal-weekday {
        text-align: center;
        font-weight: 600;
        font-size: 0.7rem;
        line-height: 1.2;
        margin: 0;
    }

    [class*="st-key-kpalcal"] .kpal-day-number {
        text-align: center;
        font-weight: 600;
        font-size: 0.85rem;
        line-height: 1.3;
        margin: 0;
    }

    /* The label is the tap target: stretch it across the cell at thumb size. */
    [class*="st-key-kpalcal"] div[data-testid="stCheckbox"] {
        margin: 0;
    }

    [class*="st-key-kpalcal"] div[data-testid="stCheckbox"] label {
        width: 100%;
        min-height: 2.5rem;
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 0;
        padding: 0;
    }

    [class*="st-key-kpalcal"] div[data-testid="stCheckbox"] label > span:first-of-type {
        width: 1.3rem;
        height: 1.3rem;
        margin: 0;
    }

    [class*="st-key-kpalcal"] div[data-testid="stMarkdownContainer"] {
        margin: 0;
        padding: 0;
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
