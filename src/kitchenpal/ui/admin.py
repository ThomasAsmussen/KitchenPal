"""Admin: two questions a month, and who lives here.

Of the six things that used to be steps, four are chores the app can do or
decide by itself: the sheet appears when something first needs it, and the
balances carry themselves on the 1st (see ui/rollover.py). What is left needs a
person, and only twice a month:

  * Is anyone moving in or out? — the only thing the app cannot know, and it
    must be answered BEFORE the month turns, because copy-balances reads the new
    sheet's names to decide who to keep.
  * Who is cooking? — the answers, the day limit, the schedule, the write.

Everything else on the screen is a to-do list derived from the sheet, so it
survives a restart and cannot go stale. The roster is the old people section as
one list, where every action is a sentence about a person rather than the
spreadsheet operation behind it; nothing here invents sheet logic.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime

import gspread
import streamlit as st

from ..constants import ENGLISH_MONTHS, MONTH_TO_NUMBER
from ..runtime_state import bump_cache_version, get_cache_version
from ..scheduler import combine_availability, schedule_people
from ..sheets.utils import (
    is_person_account_label,
    is_room_label,
    normalized_person_name,
    parse_month_sheet_name,
)
from ..sheets_service import SheetsService
from . import data, rollover
from .day_to_day import _dinner_line, _format_amount_dkk, _ledger_row
from .errors import show_user_error, user_error_message
from .identity import ROOM_STATE_KEY
from .month_setup import (
    ENGLISH_WEEKDAY_NAMES,
    _month_sheet_for,
    _month_sheet_names,
    _planning_context,
    _stored_availability,
    _unassigned_people_with_room_numbers,
)

SCREEN_KEY = "admin_screen"
OPEN_STEP_KEY = "admin_open_step"
REPORT_KEY = "admin_copy_report"


# --------------------------------------------------------------- state

@dataclass(frozen=True)
class Suggestion:
    """Someone parked in an FL slot whose intended room is now free."""

    person: str
    fl_label: str
    room_label: str
    balance: float


def next_month_and_year(today: datetime | None = None) -> tuple[str, int]:
    """The rollover is about the month you are not living in yet."""
    return rollover.next_month(today)


def _is_person_account(label: str) -> bool:
    return is_person_account_label(label)


def parked_fl_suggestions(log_entries, accounts) -> list[Suggestion]:
    """The Log says who is waiting for which room; the sheet says if it is free.

    Only the newest parked_fl row per person counts, and only while that person
    is still sitting in an FL slot with the room they named still empty.
    get_log_entries returns newest first, so the first row seen for a person is
    the one that stands.
    """
    by_label = {str(entry.label).strip(): entry for entry in accounts}
    fl_by_name = {
        normalized_person_name(entry.name): entry
        for entry in accounts
        if entry.name and not is_room_label(entry.label) and _is_person_account(entry.label)
    }

    suggestions: list[Suggestion] = []
    seen: set[str] = set()
    for log_entry in log_entries:
        if log_entry.event != "parked_fl":
            continue
        intent = str(log_entry.room_intent or "").strip()
        person_key = normalized_person_name(log_entry.person)
        if not intent or not person_key or person_key in seen:
            continue
        seen.add(person_key)

        parked = fl_by_name.get(person_key)
        room = by_label.get(intent)
        if parked is None or room is None or room.name:
            continue
        suggestions.append(
            Suggestion(
                person=parked.name,
                fl_label=parked.label,
                room_label=room.label,
                balance=float(parked.balance),
            )
        )
    return suggestions


# --------------------------------------------------------------- chrome

def _rollover_month() -> tuple[str, int]:
    """Proposes the month after this one; _render_month_picker offers the rest."""
    default_month, default_year = rollover.next_month()
    st.session_state.setdefault("admin_month", default_month)
    st.session_state.setdefault("admin_year", default_year)
    return st.session_state["admin_month"], int(st.session_state["admin_year"])


def _render_month_picker() -> None:
    default_year = rollover.next_month()[1]
    with st.expander("Another month"):
        st.selectbox("Month", ENGLISH_MONTHS, key="admin_month")
        st.selectbox("Year", [default_year - 1, default_year, default_year + 1], key="admin_year")


def render_admin_view(service: SheetsService) -> None:
    screen = st.session_state.get(SCREEN_KEY)
    if screen == "roster":
        _render_roster_screen(service)
    elif screen == "history":
        _render_history_screen(service)
    else:
        _render_rollover_screen(service)


def _back_to_rollover() -> None:
    st.session_state.pop(SCREEN_KEY, None)


def _go_to(screen: str) -> None:
    st.session_state[SCREEN_KEY] = screen


def _status_line(service: SheetsService, status, month_name: str, year: int) -> str:
    days = rollover.days_until_the_first(month_name, year)
    if days > 0:
        return f"Turns by itself in {days} day{'s' if days != 1 else ''}"
    if status.is_open:
        return f"Opened {status.turned_at}" if status.turned_at else "Open"
    return "Has not opened yet"


def _when_line(month_name: str, year: int, status) -> str:
    """A date, not a countdown: "in 3 days" tells you nothing you can act on."""
    days = rollover.days_until_the_first(month_name, year)
    if days > 1:
        first = date(year, MONTH_TO_NUMBER[month_name], 1)
        weekday = ENGLISH_WEEKDAY_NAMES[first.weekday()]
        return f"Opens by itself on {weekday} {first.day} {month_name}"
    if days == 1:
        return "Opens by itself tomorrow"
    if status.is_open:
        return f"Opened {status.turned_at}" if status.turned_at else "Open"
    if status.turned_early:
        return "Opened early — the balances refresh by themselves on the 1st"
    return "Has not opened yet"


def _question_card(
    number: int,
    title: str,
    *,
    key: str,
    summary: str,
    done: bool,
    urgent: bool,
    body=None,
) -> None:
    """One numbered question: what it asks, where it stands, and its own controls.

    Bordered, because the state line has to belong visibly to its question —
    loose captions between two full-width buttons could be read as belonging to
    either one.
    """
    with st.container(border=True):
        st.button(
            f"{number}. {title}",
            icon=":material/check_circle:" if done else ":material/radio_button_unchecked:",
            key=f"admin_question_{key}",
            use_container_width=True,
            # An answered question keeps the card's border and drops its own.
            type="primary" if urgent and not done else ("tertiary" if done else "secondary"),
            on_click=_open_question,
            args=(key,),
        )
        st.caption(summary)
        if body is not None and st.session_state.get(OPEN_STEP_KEY) == key:
            body()


def _automatic_card(month_name: str, year: int, status) -> None:
    """The step nobody performs, shown anyway.

    Leaving it out is what made the screen feel unfinished: two things to do
    and no statement of what happens after them.
    """
    with st.container(border=True):
        first = date(year, MONTH_TO_NUMBER[month_name], 1)
        st.markdown(":material/autorenew: **3. Everyone's balance carries over**")
        if status.is_open:
            st.caption(f"Done {status.turned_at}." if status.turned_at else "Done.")
        else:
            st.caption(
                f"The app does this by itself on {first.day} {month_name} — every tab moves to "
                "the new month, and anyone who has left is chased for what they owe."
            )


def _render_rollover_screen(service: SheetsService) -> None:
    month_name, year = _rollover_month()
    status = rollover.month_status(service, month_name, year)
    room = st.session_state.get(ROOM_STATE_KEY, "")
    current_month, current_year = rollover.this_month()

    # No kicker: the section heading above already says Admin, and a fourth
    # line of chrome before the first card costs more than it explains.
    st.markdown(
        f'<div class="kp-money kp-small">{month_name} {year}</div>',
        unsafe_allow_html=True,
    )
    st.caption(_when_line(month_name, year, status))

    moving_done = bool(status.sheet_name) and rollover.occupancy_is_confirmed(service, status.sheet_name)
    cooking_done = bool(status.sheet_name) and rollover.cooks_are_written(service, status.sheet_name)

    if moving_done and cooking_done:
        st.success(f"Nothing left to do. {_when_line(month_name, year, status).lower()}.")
    else:
        # Deadline and division of labour in one sentence: the two things that
        # were missing were "by when" and "who does the rest".
        st.markdown("Two things to answer before then — the app does the rest.")

    # Only the first unanswered question is a primary button: two of them
    # competing is two calls to action and no next thing to do.
    _question_moving(service, month_name, year, status, room, done=moving_done, urgent=not moving_done)
    _question_cooking(service, month_name, year, status, done=cooking_done, urgent=moving_done)
    _automatic_card(month_name, year, status)
    _render_todo(service, month_name, year, status)

    st.divider()
    st.button(
        f"Change {current_month} (this month)",
        icon=":material/groups:",
        key="admin_open_roster",
        help=f"Who lives here right now, for a change part-way through {current_month}",
        use_container_width=True,
        on_click=_go_to_current_roster,
        args=(service, current_month, current_year),
    )
    st.button(
        "What has been done",
        icon=":material/history:",
        key="admin_open_history",
        use_container_width=True,
        on_click=_go_to,
        args=("history",),
    )
    with st.expander("Something went wrong?"):
        _render_manual_open(service, month_name, year, status, room)
        _render_month_picker()


def _go_to_current_roster(service: SheetsService, month_name: str, year: int) -> None:
    sheet_name = rollover.resolve_sheet_name(service, month_name, year)
    if sheet_name:
        st.session_state["admin_roster_sheet"] = sheet_name
    st.session_state[SCREEN_KEY] = "roster"


def _render_manual_open(service: SheetsService, month_name: str, year: int, status, room: str) -> None:
    st.caption(
        "The month opens by itself on the 1st. Run it here to fix a failed turn, or to carry the "
        "balances again after correcting last month. Running it BEFORE the 1st only gives "
        "provisional figures — the automatic turn refreshes them once the month starts."
    )
    if st.button(f"Open {month_name} {year} now", key="admin_open_month", use_container_width=True):
        try:
            result = rollover.open_month(service, month_name, year, by=room)
        except ValueError as exc:
            show_user_error(st, exc, "Could not open the month")
            return
        st.session_state[REPORT_KEY] = result.report
        st.rerun()

    report = st.session_state.get(REPORT_KEY)
    if report is not None:
        _render_copy_report(report, month_name, year)
        st.button("Clear this report", key="admin_clear_results", on_click=_clear_results)


def _clear_results() -> None:
    st.session_state.pop(REPORT_KEY, None)


def _render_copy_report(report, month_name: str, year: int) -> None:
    st.success(f"Opened {month_name} {year} and carried the balances.")
    for name, balance, fl_label in report.chased:
        st.info(f"{name} no longer has a room — their {balance:.2f} DKK balance was moved to {fl_label}.")
    for name, balance in report.unplaced:
        st.warning(
            f"No free FL slot for {name} ({balance:.2f} DKK) — their balance was NOT carried over. "
            "Settle and remove someone without a room, then open the month again."
        )
    for label, previous_name, current_name in report.suspected_renames:
        st.warning(
            f"Room {label}: '{current_name}' replaced '{previous_name}', who still has money outstanding. "
            f"If this is the same person misspelled, fix the name in room {label} and clear the FL row, "
            "then open the month again."
        )
    for name in report.duplicate_names:
        st.warning(f"'{name}' appears in more than one row — check the sheet before trusting the balances.")


# --------------------------------------------------------------- question one

def _question_moving(
    service: SheetsService, month_name: str, year: int, status, room: str, *, done: bool, urgent: bool
) -> None:
    """Who lives here next month — asked as a roster, not as a list of verbs.

    An admin does not think in move types. A room can empty, fill, or change
    hands three ways round in one month, and enumerating those cases is how you
    end up with a form nobody can map onto their own situation. So the answer is
    the roster itself: next month starts as a copy of this one, and you edit
    rows until it is right. Any permutation is expressible by typing the right
    name in each room.
    """
    changes = _recorded_changes(service, status.sheet_name)
    if done:
        summary = (
            f"{len(changes)} change{'s' if len(changes) != 1 else ''} recorded"
            if changes
            else "Nobody is moving"
        )
    elif changes:
        summary = f"{len(changes)} change{'s' if len(changes) != 1 else ''} so far — say when you are done"
    else:
        summary = "Needs you before the month starts"

    _question_card(
        1,
        f"Who lives here in {month_name}?",
        key="moving",
        summary=summary,
        done=done,
        urgent=urgent,
        body=lambda: _moving_body(service, month_name, year, status, room, changes, done=done),
    )


def _moving_body(service, month_name, year, status, room, changes, *, done: bool) -> None:
    prepared = rollover.is_prepared(service, status.sheet_name)

    if prepared:
        st.caption(f"Everyone below lives in {month_name}. Change any row that is wrong.")
    else:
        st.caption(
            f"{month_name} starts as a copy of {_previous_label(service, month_name, year)}. "
            "Recording a change — or saying this is right — sets it up."
        )

    if changes:
        st.caption("Recorded so far:")
        for line in changes[:8]:
            _dinner_line(line, "")
        if len(changes) > 8:
            st.caption(f"…and {len(changes) - 8} more, in What has been done.")

    # The actions sit above the roster: on a phone, twenty rows between the
    # question and its answer means nobody ever reaches the answer.
    rooms = None
    if prepared:
        accounts = _roster_accounts(service, status.sheet_name)
        rooms = [entry.label for entry in accounts if is_room_label(entry.label)]

    st.button(
        "Someone is moving in",
        icon=":material/person_add:",
        key="admin_arriving",
        use_container_width=True,
        on_click=_arriving_dialog,
        args=(service, rooms, month_name, year),
    )
    if not done and st.button(
        "That's everyone — done",
        key="admin_confirm_occupancy",
        type="primary",
        use_container_width=True,
    ):
        sheet_name = _ensure_prepared(service, month_name, year, room)
        if sheet_name is None:
            return
        try:
            rollover.confirm_occupancy(service, sheet_name, by=room)
        except ValueError as exc:
            show_user_error(st, exc, "Could not save the answer")
            return
        bump_cache_version()
        st.rerun()

    if prepared:
        _roster_body(service, status.sheet_name)


def _previous_label(service: SheetsService, month_name: str, year: int) -> str:
    return rollover.previous_sheet_name(service, month_name, year) or "an empty sheet"


def _render_moving_actions(
    service: SheetsService, month_name: str, year: int, status, room: str, *, rooms
) -> None:
    st.button(
        "Someone is moving in",
        icon=":material/person_add:",
        key="admin_arriving",
        use_container_width=True,
        on_click=_arriving_dialog,
        args=(service, rooms, month_name, year),
    )
    if st.button(
        "That's everyone — done",
        key="admin_confirm_occupancy",
        use_container_width=True,
    ):
        sheet_name = _ensure_prepared(service, month_name, year, room)
        if sheet_name is None:
            return
        try:
            rollover.confirm_occupancy(service, sheet_name, by=room)
        except ValueError as exc:
            show_user_error(st, exc, "Could not save the answer")
            return
        bump_cache_version()
        st.rerun()


def _recorded_changes(service: SheetsService, sheet_name: str | None) -> list[str]:
    """Moves already written into the month being opened."""
    if not sheet_name:
        return []
    try:
        entries = data.log_entries(service)
    except (ValueError, gspread.exceptions.WorksheetNotFound):
        return []
    # Newest first, one line per person: an admin who recorded the same move
    # twice wants to read it once.
    changes: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not rollover.same_month_sheet(entry.month_sheet, sheet_name):
            continue
        if entry.event not in ("moved_in", "moved_out", "parked_fl", "moved"):
            continue
        key = normalized_person_name(entry.person) or str(entry.summary)
        if key in seen:
            continue
        seen.add(key)
        changes.append(str(entry.summary or entry.event).strip().rstrip("."))
    return changes


def _ensure_prepared(service: SheetsService, month_name: str, year: int, room: str = "") -> str | None:
    """Next month appears, filled from this one, the first time anything needs it.

    Never a step of its own: a half-populated sheet — one name typed in and
    fourteen blank rooms — is a worse thing to hand an admin than no sheet.
    """
    sheet_name = rollover.resolve_sheet_name(service, month_name, year)
    if sheet_name and rollover.is_prepared(service, sheet_name):
        return sheet_name
    try:
        return rollover.prepare_month(service, month_name, year, by=room).sheet_name
    except ValueError as exc:
        show_user_error(st, exc, f"Could not set up {month_name} {year}")
        return None


# --------------------------------------------------------------- question two

def _question_cooking(service: SheetsService, month_name: str, year: int, status, *, done: bool, urgent: bool) -> None:
    answered, total = _answer_counts(service, month_name, year, status.sheet_name)
    if done:
        summary = "The schedule is written"
    elif not total:
        summary = "Nobody to ask yet"
    else:
        summary = f"{answered} of {total} have said when they can cook · no schedule yet"

    _question_card(
        2,
        "Who is cooking?",
        key="cooking",
        summary=summary,
        done=done,
        urgent=urgent,
        body=lambda: _cooking_body(service, month_name, year, status),
    )


def _cooking_body(service, month_name: str, year: int, status) -> None:
    if not status.sheet_name:
        st.caption(f"Answer question 1 first — it is what creates the {month_name} {year} sheet.")
        return
    st.caption("People answer on their own Plan tab. Build the schedule once enough of them have.")
    _dinner_days_setting(service, month_name, year)
    _schedule_tools(service, month_name, year)


def _open_question(key: str) -> None:
    """Tapping the open card closes it — anything else is a trap."""
    if st.session_state.get(OPEN_STEP_KEY) == key:
        st.session_state.pop(OPEN_STEP_KEY, None)
    else:
        st.session_state[OPEN_STEP_KEY] = key


def _answer_counts(service: SheetsService, month_name: str, year: int, sheet_name: str | None) -> tuple[int, int]:
    if not sheet_name:
        return 0, 0
    try:
        # People without a room are welcome to answer on Plan and are scheduled
        # if they do, but they are not on the rota, so they are not part of
        # "everyone has answered".
        room_entries = [
            entry
            for entry in data.room_entries(service, sheet_name)
            if is_room_label(entry.label) and entry.name
        ]
        stored = {
            str(entry.room_number).strip(): entry
            for entry in data.planning_entries(service, month_name, year)
            if str(entry.room_number).strip()
        }
    except (ValueError, gspread.exceptions.WorksheetNotFound):
        return 0, 0

    context = _AnswerContext(
        year=year, month=MONTH_TO_NUMBER[month_name], room_entries=room_entries, stored_entries=stored
    )
    return len(room_entries) - len(_missing_answers(context)), len(room_entries)


def _missing_answers(context) -> list[str]:
    from .month_setup import _stored_planning_days

    missing = []
    for entry in context.room_entries:
        days = _stored_planning_days(context.stored_entries.get(entry.label), context.year, context.month)
        if not (days["available"] or days["unavailable"] or days["preferred"]):
            missing.append(entry.name or entry.label)
    return missing


@dataclass(frozen=True)
class _AnswerContext:
    """Just enough of a PlanningContext for _missing_answers."""

    year: int
    month: int
    room_entries: list
    stored_entries: dict


def _dinner_days_setting(service: SheetsService, month_name: str, year: int) -> None:
    """Not a step: blank is the normal answer, so it is a setting on this question."""
    limit = str(data.possible_days_limit(service, month_name, year) or "").strip()
    with st.expander(
        "Dinner can happen any day this month" if not limit else f"Dinner only on: {limit}"
    ):
        limit_input = st.text_input(
            "Dates dinner can happen",
            value=limit,
            placeholder="e.g. 1-20, 23-30",
            help="Leave blank to allow every normal dinner day. Dates, ranges or weekday names.",
            key=f"admin_limit_days_{month_name}_{year}_{get_cache_version()}",
        )
        if st.button("Save the dates", key="admin_save_limit_days", use_container_width=True):
            try:
                service.save_possible_days_limit(month_name, year, limit_input)
            except ValueError as exc:
                show_user_error(st, exc, "Could not save the possible dates")
                return
            data.clear_planning()
            bump_cache_version()
            st.rerun()


def _schedule_tools(service: SheetsService, month_name: str, year: int) -> None:
    context = _planning_context(service, month_name=month_name, year=year)
    if context is None:
        return

    available, unavailable, preferences, limit_one_day, person_to_room = _stored_availability(context)
    schedule_key = f"admin_schedule_{month_name}_{year}"
    if st.button("Build a schedule", key="admin_generate_schedule", use_container_width=True):
        available_days = combine_availability(available, unavailable, context.year, context.month)
        try:
            st.session_state[schedule_key] = schedule_people(
                available_days, preferences, context.possible_days, limit_one_day
            )
        except ModuleNotFoundError as exc:
            if exc.name != "ortools":
                raise
            st.error("Scheduling needs the 'ortools' package. Reinstall with `pip install -r requirements.txt`.")
            return

    if schedule_key not in st.session_state:
        return
    schedule = st.session_state[schedule_key]
    if schedule is None:
        st.warning("No schedule fits the answers and the possible dates.")
        return

    st.markdown("###### Suggested schedule")
    for day, person in schedule.assignments.items():
        weekday = ENGLISH_WEEKDAY_NAMES[calendar.weekday(context.year, context.month, day)]
        st.markdown(
            f'<div class="kp-line"><span>{weekday[:3]} {day}</span>'
            f'<span class="kp-note">{person}</span></div>',
            unsafe_allow_html=True,
        )

    if schedule.unassigned_people:
        st.info("Not assigned: " + ", ".join(schedule.unassigned_people))
    unassigned_room_people = _unassigned_people_with_room_numbers(schedule.unassigned_people, person_to_room)
    if unassigned_room_people:
        st.warning("Room residents without a dinner: " + ", ".join(unassigned_room_people))

    missing_rooms = sorted({person for person in schedule.assignments.values() if person not in person_to_room})
    confirm = st.checkbox(
        f"I have reviewed the schedule and want to write these cooks to {context.sheet_name}.",
        key="admin_confirm_write_cooks",
    )
    if st.button(
        "Write the cooks to the sheet",
        key="admin_write_cooks",
        type="primary",
        use_container_width=True,
        disabled=not confirm,
    ):
        if missing_rooms:
            st.error("Missing room for: " + ", ".join(missing_rooms))
            return
        service.populate_cooks_for_month(context.sheet_name, schedule.assignments, person_to_room)
        data.clear_dinners()
        bump_cache_version()
        st.success(f"Wrote the cooks to {context.sheet_name}.")


# --------------------------------------------------------------- what is left

def _render_todo(service: SheetsService, month_name: str, year: int, status) -> None:
    """Derived from the sheet, so it survives a restart and cannot go stale.

    Only after the month has opened: before the copy runs, everyone in the
    previous month is trivially "missing" from a sheet with no names on it.
    """
    if not status.sheet_name or not rollover.is_prepared(service, status.sheet_name):
        return
    previous = rollover.previous_sheet_name(service, month_name, year)
    try:
        strays = rollover.outstanding_strays(service, status.sheet_name, previous)
        duplicates = rollover.duplicate_people(service, status.sheet_name)
        accounts = [
            entry for entry in data.personal_accounts(service, status.sheet_name)
            if _is_person_account(entry.label)
        ]
        suggestions = parked_fl_suggestions(data.log_entries(service), accounts)
        reverted = rollover.reverted_move_outs(service, status.sheet_name, accounts)
    except (ValueError, gspread.exceptions.WorksheetNotFound):
        return

    if not strays and not duplicates and not suggestions and not reverted:
        return

    st.markdown("###### Still to sort out")
    if strays:
        st.caption(
            f"Money left on {previous} by someone with no row in {month_name}. Opening the month "
            "again (below) chases each of them into a free FL row."
        )
    for stray in strays:
        _dinner_line(f"{stray.name} has no row in {month_name}", f"{stray.balance:.2f} DKK")
    for name in duplicates:
        _dinner_line(f"{name} appears on more than one row", "rename one of them")
    for name in reverted:
        st.info(
            f"{name} was moved out of this month but is on the sheet again — the copy puts a "
            "settled leaver back into an empty room. Move them out once more and it will stick."
        )
    for suggestion in suggestions:
        st.info(
            f"{suggestion.person} is parked in {suggestion.fl_label} waiting for room "
            f"{suggestion.room_label}, which is now empty."
        )
        if st.button(
            f"Move {suggestion.person} into {suggestion.room_label}",
            key=f"admin_move_in_{suggestion.fl_label}",
            use_container_width=True,
        ):
            _run(
                service,
                "Could not move the person in",
                lambda: service.move_person_between_accounts(
                    status.sheet_name, suggestion.fl_label, suggestion.room_label
                ),
                done=f"{suggestion.person} moved into {suggestion.room_label}.",
            )


# --------------------------------------------------------------- the roster

def _roster_sheet_name(service: SheetsService, month_name: str, year: int) -> str | None:
    sheets = _month_sheet_names(data.sheet_names(service))
    if not sheets:
        return None
    preferred = _month_sheet_for(MONTH_TO_NUMBER[month_name], year, sheets)
    if st.session_state.get("admin_roster_sheet") not in sheets:
        st.session_state["admin_roster_sheet"] = preferred or sheets[0]
    return st.session_state["admin_roster_sheet"]


def _render_roster_month_picker(service: SheetsService) -> None:
    sheets = _month_sheet_names(data.sheet_names(service))
    with st.expander("Another month"):
        st.selectbox("Month sheet", sheets, key="admin_roster_sheet")


def _waiting_for(suggestions, room_label: str) -> Suggestion | None:
    return next((item for item in suggestions if item.room_label == room_label), None)


def _roster_accounts(service: SheetsService, sheet_name: str) -> list:
    try:
        return [
            entry for entry in data.personal_accounts(service, sheet_name) if _is_person_account(entry.label)
        ]
    except (ValueError, gspread.exceptions.WorksheetNotFound) as exc:
        show_user_error(st, exc, "Could not load the people")
        return []


def _roster_body(service: SheetsService, sheet_name: str) -> list:
    """The rows themselves, shared by the roster screen and question one."""
    accounts = _roster_accounts(service, sheet_name)

    try:
        suggestions = parked_fl_suggestions(data.log_entries(service), accounts)
    except (ValueError, gspread.exceptions.WorksheetNotFound):
        suggestions = []

    free_slots = []
    for entry in accounts:
        if not entry.name and not is_room_label(entry.label):
            free_slots.append(entry.label)
            continue
        _render_roster_row(service, sheet_name, entry, accounts, suggestions)
    if free_slots:
        _dinner_line(
            f"{free_slots[0]}–{free_slots[-1]}" if len(free_slots) > 1 else free_slots[0],
            f"{len(free_slots)} free {'slot' if len(free_slots) == 1 else 'slots'} for leftover tabs",
            dim=True,
        )
    return accounts


def _render_roster_screen(service: SheetsService) -> None:
    st.button(
        "Start next month",
        icon=":material/arrow_back:",
        key="admin_back_rollover",
        type="tertiary",
        on_click=_back_to_rollover,
    )
    month_name = st.session_state.get("admin_month") or next_month_and_year()[0]
    year = int(st.session_state.get("admin_year") or next_month_and_year()[1])
    sheet_name = _roster_sheet_name(service, month_name, year)
    if sheet_name is None:
        st.warning("There is no month sheet to show yet.")
        return

    st.markdown(
        '<div class="kp-money kp-small">Who lives here</div>',
        unsafe_allow_html=True,
    )
    # Which month, before the rows and not after them: the picker below can put
    # any month on this screen, and every action here writes to that sheet.
    summary = st.empty()
    accounts = _roster_body(service, sheet_name)
    rooms = [entry for entry in accounts if is_room_label(entry.label)]
    empty_rooms = [entry for entry in rooms if not entry.name]
    summary.caption(f"{sheet_name} · {len(rooms)} rooms, {len(empty_rooms)} empty")

    _render_roster_month_picker(service)
    st.divider()
    # The month being shown, not the one Admin proposed: the picker above may
    # have moved the roster somewhere else entirely.
    shown = parse_month_sheet_name(sheet_name)
    st.button(
        "Someone is moving in",
        icon=":material/person_add:",
        key="admin_add_person",
        use_container_width=True,
        on_click=_arriving_dialog,
        args=(
            service,
            [entry.label for entry in rooms],
            ENGLISH_MONTHS[shown[0] - 1] if shown else month_name,
            shown[1] if shown else year,
        ),
    )


def _render_roster_row(service, sheet_name, entry, accounts, suggestions) -> None:
    room = is_room_label(entry.label)
    if entry.name:
        waiting = next((item for item in suggestions if item.fl_label == entry.label), None)
        subtitle = entry.label if room else f"{entry.label} · no room"
        if waiting:
            subtitle += f" · waiting for {waiting.room_label}"
        _ledger_row(
            title=entry.name,
            subtitle=subtitle,
            note=_format_amount_dkk(entry.balance),
            key=f"roster_{entry.label}",
            help_text=f"What is happening with {entry.name}",
            on_edit=_person_dialog,
            args=(service, sheet_name, entry, accounts),
        )
        return

    if room:
        waiting = _waiting_for(suggestions, entry.label)
        _ledger_row(
            title=f"{entry.label} — empty",
            subtitle=f"{waiting.person} is waiting for this room" if waiting else "",
            note="move in",
            key=f"roster_{entry.label}",
            help_text=f"Someone moving into {entry.label}",
            on_edit=_person_dialog,
            args=(service, sheet_name, entry, accounts),
        )
        return

    # The caller collapses free FL slots into one line; this is only a fallback.
    _dinner_line(f"{entry.label} — empty", "a free slot for a leftover tab", dim=True)


@st.dialog("Change who lives here")
def _person_dialog(service: SheetsService, sheet_name: str, entry, accounts) -> None:
    is_room = is_room_label(entry.label)
    room = st.session_state.get(ROOM_STATE_KEY, "")
    empty_rooms = [item for item in accounts if is_room_label(item.label) and not item.name]
    # Every other row is a possible destination: a person to swap with, or an
    # empty room to move into.
    others = [item for item in accounts if item.label != entry.label and (item.name or is_room_label(item.label))]

    if not entry.name:
        if is_room:
            _moving_into_room(service, sheet_name, entry, accounts)
        return

    st.markdown(f"**{entry.name}** · {entry.label} · {_format_amount_dkk(entry.balance)}")

    if is_room:
        _moving_out(service, sheet_name, entry, room)
        _moving_within_the_house(service, sheet_name, entry, others)
        _correcting_the_name(service, sheet_name, entry, room)
        return

    _moving_in_from_fl(service, sheet_name, entry, empty_rooms)
    _correcting_the_name(service, sheet_name, entry)
    _removing_a_settled_person(service, sheet_name, entry)


def _moving_into_room(service, sheet_name, entry, accounts) -> None:
    """An empty room fills either from outside the house or from inside it.

    Inside covers the case that has no name of its own: 346 empties, 350 moves
    into 346, and someone new takes 350. Nobody should have to know that the
    middle step is a "move between accounts".
    """
    waiting = [item for item in accounts if item.name and item.label != entry.label]
    if waiting:
        person = st.selectbox(
            "Someone already on the sheet",
            [None] + waiting,
            format_func=lambda item: "Nobody — a new person" if item is None else f"{item.name} ({item.label})",
            key=f"roster_existing_{entry.label}",
        )
        if person is not None:
            st.caption(f"{person.name} keeps their {_format_amount_dkk(person.balance)} balance.")
            if st.button(
                f"Move {person.name} into {entry.label}",
                type="primary",
                use_container_width=True,
                key=f"roster_move_in_{entry.label}",
            ):
                _run(
                    service,
                    "Could not move the person in",
                    lambda: service.move_person_between_accounts(sheet_name, person.label, entry.label),
                    done=f"{person.name} moved from {person.label} to {entry.label}.",
                )
            return

    with st.form(key=f"roster_new_person_{entry.label}"):
        name = st.text_input(f"Who is moving into {entry.label}?")
        saved = st.form_submit_button("Move them in", type="primary", use_container_width=True)
    if saved:
        if not name.strip():
            st.error("Add a name before saving.")
            return
        _run(
            service,
            "Could not move the person in",
            lambda: service.replace_room_person(sheet_name, entry.label, name),
            done=f"{name.strip()} moved into {entry.label}.",
        )


def _moving_out(service, sheet_name, entry, room: str = "") -> None:
    st.caption(
        "A settled tab just frees the room. Anything owed follows them to the highest free FL "
        "row — leftover tabs fill from the top, arrivals from the bottom, so the two never "
        "collide."
    )
    if st.button(
        f"{entry.name} is moving out",
        key=f"roster_move_out_{entry.label}",
        use_container_width=True,
    ):
        _run(
            service,
            "Could not move the person out",
            lambda: _moved_out_message(service, sheet_name, entry, room),
        )


def _moved_out_message(service, sheet_name, entry, room: str) -> str:
    fl_label = service.move_person_out(sheet_name, entry.label, by=room)
    if fl_label:
        return f"{entry.name} left {entry.label}; their tab is parked at {fl_label}."
    return f"{entry.name} left {entry.label} with nothing owed."


def _moving_within_the_house(service, sheet_name, entry, others) -> None:
    """One control for both moving and swapping — the sheet already knows which.

    move_person_between_accounts swaps when the destination is taken and simply
    moves when it is free, so the admin picks a destination and never has to
    name which of the two is happening.
    """
    if not others:
        return
    st.caption("If someone already lives there, the two of them swap.")
    with st.form(key=f"roster_swap_{entry.label}"):
        other = st.selectbox(
            "Moving to another room",
            others,
            format_func=lambda item: f"{item.name} ({item.label})" if item.name else f"{item.label} — empty",
        )
        saved = st.form_submit_button("Move them there", use_container_width=True)
    if saved:
        _run(
            service,
            "Could not move them",
            lambda: service.move_person_between_accounts(sheet_name, entry.label, other.label),
            done=(
                f"{entry.name} and {other.name} swapped rooms."
                if other.name
                else f"{entry.name} moved to {other.label}."
            ),
        )


def _correcting_the_name(service, sheet_name, entry, room: str = "") -> None:
    """A typo is the same person, so this only rewrites the cell."""
    with st.form(key=f"roster_rename_{entry.label}"):
        corrected = st.text_input("The name is spelled wrong", value=entry.name)
        saved = st.form_submit_button("Save the name", use_container_width=True)
    if saved:
        if not corrected.strip():
            return
        # Saving an unchanged name is not a no-op: it re-spreads the spelling to
        # the months either side, which is the one-tap repair for a name that
        # was corrected on one sheet before this did that.
        _run(
            service,
            "Could not change the name",
            lambda: service.rename_person(sheet_name, entry.label, corrected, by=room),
            done=f"{entry.label} is now {corrected.strip()}.",
        )


def _moving_in_from_fl(service, sheet_name, entry, empty_rooms) -> None:
    if not empty_rooms:
        st.caption("No room is free for them yet.")
        return
    with st.form(key=f"roster_fl_move_{entry.label}"):
        room = st.selectbox(
            "Moving into",
            empty_rooms,
            format_func=lambda item: item.label,
        )
        saved = st.form_submit_button("Move them in", type="primary", use_container_width=True)
    if saved:
        _run(
            service,
            "Could not move the person in",
            lambda: service.move_person_between_accounts(sheet_name, entry.label, room.label),
            done=f"{entry.name} moved into {room.label}.",
        )


def _removing_a_settled_person(service, sheet_name, entry) -> None:
    previous = service.previous_month_sheet_name(sheet_name)
    if previous:
        st.caption(f"Removing checks that both the {sheet_name} and {previous} balances are 0 DKK.")
    else:
        st.caption(f"No previous month sheet — only the {sheet_name} balance is checked.")
    if st.button(
        f"{entry.name} has settled up — remove them",
        key=f"roster_delete_{entry.label}",
        use_container_width=True,
    ):
        _run(
            service,
            "Could not remove the person",
            lambda: service.delete_fl_person(sheet_name, entry.name),
            done=f"{entry.name} removed from {entry.label}.",
        )


@st.dialog("Someone is moving in")
def _arriving_dialog(
    service: SheetsService,
    room_labels: list[str] | None = None,
    target_month: str | None = None,
    target_year: int | None = None,
) -> None:
    """One path, whoever arrives when.

    Somebody joining the house needs the same two things whether they turn up
    on the 12th or on the 1st: a row without a room in the month running now,
    so the app knows who they are and they can answer when they can cook, and
    the room itself on the month they take it over. Asking "when?" and then
    doing those same two writes in a different order was a question with no
    consequence — and the two orders did not even fail the same way.

    So the only question left is which room, if any. A room's accounting belongs
    to one person for a whole month, which is the one reason a room cannot start
    part-way through: hence the room lands on the month being opened, while the
    month running now gets the room-less row.
    """
    current_month, current_year = rollover.this_month()
    upcoming_month = target_month or rollover.next_month()[0]
    upcoming_year = target_year or rollover.next_month()[1]
    takes_over_later = (upcoming_month, upcoming_year) != (current_month, current_year)

    rooms = list(room_labels or _room_labels(service))
    name = st.text_input("Who is arriving?", key="admin_arrival_name")
    room_label = st.selectbox(
        "Which room will they have?",
        [""] + rooms,
        format_func=lambda value: "No room yet" if not value else value,
        key="admin_arrival_room",
    )

    if room_label and takes_over_later:
        st.caption(
            f"They get a row without a room in {current_month}, so they can use the app and say "
            f"when they can cook — and room {room_label} on the {upcoming_month} {upcoming_year} "
            "sheet, moving whoever holds it there out."
        )
    elif room_label:
        st.caption(f"They take room {room_label} in {current_month} straight away.")
    else:
        st.caption(
            f"They get a row without a room in {current_month}. Give them a room from the roster "
            "when they have one."
        )

    if not st.button("Add them", type="primary", use_container_width=True, key="admin_arrival_save"):
        return
    if not name.strip():
        st.error("Add a name before saving.")
        return

    by = st.session_state.get(ROOM_STATE_KEY, "")
    current_sheet = rollover.resolve_sheet_name(service, current_month, current_year)
    target_sheet = None
    if room_label and takes_over_later:
        target_sheet = _ensure_prepared(service, upcoming_month, upcoming_year, by)
        if target_sheet is None:
            return
    elif room_label:
        target_sheet = current_sheet

    if not current_sheet and not target_sheet:
        st.error(f"There is no {current_month} {current_year} sheet to add them to.")
        return

    _run(
        service,
        "Could not add the person",
        lambda: _add_arrival(service, name, room_label, by, current_sheet, target_sheet, takes_over_later),
    )


def _add_arrival(
    service, name: str, room_label: str, by: str, current_sheet, target_sheet, takes_over_later: bool
) -> str:
    """The room first, then the row for now.

    That order matters: this month's FL rows can legitimately all be taken, and
    a full FL table must not stop the app recording which room somebody has
    next month — the half that is hard to reconstruct afterwards.
    """
    person = name.strip()
    if room_label and not takes_over_later:
        service.replace_room_person(target_sheet, room_label, person)
        return f"{person} has moved into {room_label}."

    said = []
    if room_label:
        service.replace_room_person(target_sheet, room_label, person)
        said.append(f"has {room_label} on the {target_sheet} sheet")

    if current_sheet:
        try:
            fl_label = service.add_person_as_fl(current_sheet, person, intended_room=room_label, by=by)
            said.insert(0, f"is in {fl_label} for the rest of {current_sheet}")
        except (ValueError, gspread.exceptions.WorksheetNotFound) as exc:
            said.append(f"has no row in {current_sheet} yet — {user_error_message(exc, '')}")

    return f"{person} " + " and ".join(said) + "."


def _room_labels(service: SheetsService) -> list[str]:
    """The house's rooms are the same every month, so any sheet will do."""
    month_name, year = rollover.this_month()
    sheet_name = rollover.resolve_sheet_name(service, month_name, year)
    if sheet_name is None:
        return []
    try:
        return [
            entry.label
            for entry in data.personal_accounts(service, sheet_name)
            if is_room_label(entry.label)
        ]
    except (ValueError, gspread.exceptions.WorksheetNotFound):
        return []


def _run(service: SheetsService, error_heading: str, action, done: str = "") -> None:
    """Every roster action ends the same way: do it, forget the caches, redraw.

    st.toast rather than st.success, because the redraw would wipe a success
    message before anyone read it — and where a person ended up is the one thing
    these actions must not do silently.
    """
    try:
        result = action()
    except (ValueError, gspread.exceptions.WorksheetNotFound) as exc:
        show_user_error(st, exc, error_heading)
        return
    if done:
        st.toast(done)
    elif isinstance(result, str) and result:
        st.toast(result)
    data.clear_people()
    bump_cache_version()
    st.rerun()


# --------------------------------------------------------------- the history

def _render_history_screen(service: SheetsService) -> None:
    st.button(
        "Start next month",
        icon=":material/arrow_back:",
        key="admin_back_from_history",
        type="tertiary",
        on_click=_back_to_rollover,
    )
    st.markdown(
        '<div class="kp-money kp-small">What has been done</div>',
        unsafe_allow_html=True,
    )
    try:
        entries = list(data.log_entries(service))
    except (ValueError, gspread.exceptions.WorksheetNotFound) as exc:
        show_user_error(st, exc, "Could not read the history")
        return

    if not entries:
        st.caption("Nothing has been logged yet.")
        return

    st.caption(f"{len(entries)} events · newest first")
    for entry in entries[:50]:  # get_log_entries already returns newest first
        by = f" · {entry.by}" if entry.by else ""
        _dinner_line(entry.summary or entry.event, f"{entry.timestamp}{by}")
