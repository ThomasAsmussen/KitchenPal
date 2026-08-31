"""The Plan tab: when you can cook next month, and what you got.

One calendar, not two. Every dinner day is already in one of three states in
the data — you can, you can't, you would like to — so the state lives on the
day itself and a tap cycles it. That retires the radio above the old grid,
which reversed the meaning of every tick you had already made, and the second
"preferred dates" grid, whose relationship to the first was never stated.

Days the house cannot hold a dinner on are drawn flat and do not respond, which
also retires the wall of numbers that used to list them.

Once you have answered, the page opens on your answer in words rather than on
the form: the only question anyone asks this tab after answering once is "what
did I put?". And once the schedule exists it says which nights are yours, which
is the half of the conversation the tab never had.
"""
from __future__ import annotations

import calendar

import streamlit as st

from ..runtime_state import bump_cache_version, get_cache_version
from ..sheets_service import PlanningEntry, SheetsService
from . import data
from .day_to_day import (
    _dinner_line,
    _ledger_row,
    _ordinal,
    _swap_dialog,
    build_month_context,
    my_cooking_nights,
)
from .errors import show_user_error
from .month_setup import (
    ENGLISH_WEEKDAY_NAMES,
    PlanningContext,
    _answered_count,
    _planning_context,
    upcoming_month,
    _planning_room_entry,
    _rota_entries,
    _weekday_label,
    format_days,
    parse_entry_days,
)
from .calendar_grid import render_grid, render_static_grid

CAN, CANT, PREF = "can", "cant", "pref"
_NEXT_STATE = {CAN: CANT, CANT: PREF, PREF: CAN}
_MARK = {CAN: "", CANT: "✕", PREF: "★"}
EDIT_KEY = "planning_editing"


# --------------------------------------------------------------- the answer

def day_states_from_entry(
    stored, possible_days, year: int, month: int, *, default: str = CAN
) -> dict[int, str]:
    """Every dinner day starts as a yes; the answer is the exceptions.

    Most people can cook most days, so a handful of taps beats ticking fourteen.
    Someone without a room starts the other way round (default=CANT): they are
    not on the rota, so they should never end up cooking a night they did not
    ask for — but every day is one tap away if they want it.

    The one answer that cannot be read as exceptions is one saved under the old
    whitelist UI — available days listed with nothing marked unavailable — where
    the days left out WERE the no. Those are restored as no, not as yes.
    """
    days = list(possible_days)
    if stored is None:
        return {day: default for day in days}

    available = parse_entry_days(stored.available_dates, year, month)
    unavailable = parse_entry_days(stored.unavailable_dates, year, month)
    preferred = parse_entry_days(stored.preferred_dates, year, month)

    if available and not unavailable:
        states = {day: (CAN if day in available else CANT) for day in days}
    else:
        states = {day: (CANT if day in unavailable else CAN) for day in days}

    for day in preferred:
        if states.get(day) == CAN:
            states[day] = PREF
    return states


def entry_days(states: dict[int, str], possible_days) -> dict[str, list[int]]:
    """A preferred day is still a day you can cook, or the solver cannot use it."""
    days = sorted(day for day in possible_days if day in states)
    return {
        "available": [day for day in days if states[day] in (CAN, PREF)],
        "unavailable": [day for day in days if states[day] == CANT],
        "preferred": [day for day in days if states[day] == PREF],
    }


def has_answered(stored, possible_days, year: int, month: int) -> bool:
    if stored is None:
        return False
    return bool(
        parse_entry_days(stored.available_dates, year, month)
        or parse_entry_days(stored.unavailable_dates, year, month)
        or parse_entry_days(stored.preferred_dates, year, month)
    )


def day_list(days) -> str:
    """"the 3rd, 4th and 17th" — dates people say out loud, with one "the"."""
    ordered = [f"{day}{_ordinal(day)}" for day in sorted(days)]
    if not ordered:
        return ""
    if len(ordered) == 1:
        return f"the {ordered[0]}"
    if len(ordered) > 8:
        return "the " + ", ".join(ordered[:8]) + f" and {len(ordered) - 8} more"
    return "the " + ", ".join(ordered[:-1]) + f" and {ordered[-1]}"


# --------------------------------------------------------------- the calendar

def _states_key(context: PlanningContext, label: str) -> str:
    return f"planning_days_{context.year}_{context.month_name}_{label}"


def _cycle_day(states_key: str, day: int) -> None:
    states = st.session_state.get(states_key, {})
    states[day] = _NEXT_STATE.get(states.get(day, CAN), CANT)
    st.session_state[states_key] = states


def _load_states(context: PlanningContext, label: str, stored, *, on_the_rota: bool = True) -> str:
    """Kept in session state between taps, reloaded whenever the sheet moves."""
    states_key = _states_key(context, label)
    version_key = f"{states_key}_version"
    version = get_cache_version()
    if states_key not in st.session_state or st.session_state.get(version_key) != version:
        st.session_state[states_key] = day_states_from_entry(
            stored,
            context.possible_days,
            context.year,
            context.month,
            default=CAN if on_the_rota else CANT,
        )
        st.session_state[version_key] = version
    return states_key


def render_day_grid(context: PlanningContext, states_key: str, *, override: str = "") -> None:
    states = st.session_state[states_key]
    possible = set(context.possible_days)
    render_grid(
        key=states_key,
        year=context.year,
        month=context.month,
        day_state=lambda day: (override or states.get(day, CAN)) if day in possible else "",
        day_label=lambda day: f"{day}{_MARK[override or states.get(day, CAN)]}",
        on_click=_cycle_day,
        args_for=lambda day: (states_key, day),
        disabled=bool(override),
    )


def _render_legend() -> None:
    st.markdown(
        "<div class='kpal-legend'>"
        "<span><i class='kpal-sw kpal-sw-can'></i>can cook</span>"
        "<span><i class='kpal-sw kpal-sw-cant'></i>can't</span>"
        "<span><i class='kpal-sw kpal-sw-pref'></i>would like to</span>"
        "<span><i class='kpal-sw kpal-sw-off'></i>no dinner</span>"
        "</div>",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------- the screens

def _cannot_at_all(states: dict[int, str], possible_days) -> bool:
    return bool(possible_days) and all(states.get(day) == CANT for day in possible_days)


def render_answer_summary(context: PlanningContext, states: dict[int, str], limit_one_day: bool) -> None:
    """What you said, as the picture you drew.

    Three sentences carrying lists of a dozen dates each is how this read
    before: accurate and unreadable. The answer IS a calendar, so it is shown
    as one, with a single line of prose above it for the shape of it.
    """
    days = entry_days(states, context.possible_days)
    total = len(context.possible_days)
    possible = set(context.possible_days)

    if not days["available"]:
        headline = "You can't cook at all this month"
    else:
        headline = f"You can cook on {len(days['available'])} of {total} dinner days"
        if days["preferred"]:
            headline += f" · {len(days['preferred'])} you would like"
    st.markdown(f'<div class="kp-money kp-small">{headline}</div>', unsafe_allow_html=True)
    if limit_one_day:
        st.caption("At most once this month.")

    render_static_grid(
        year=context.year,
        month=context.month,
        day_state=lambda day: states.get(day, CAN) if day in possible else "",
    )
    _render_legend()


def render_schedule_card(service: SheetsService, context: PlanningContext, room_entry, states) -> bool:
    """Which nights are yours — the half of the conversation the tab never had."""
    try:
        rows = data.day_rows(service, context.sheet_name)
    except Exception:  # noqa: BLE001 - the schedule is a bonus, never a blocker
        return False

    mine = my_cooking_nights(rows, room_entry.label)
    if not any(row.chef for row in rows):
        return False

    preferred = set(entry_days(states, context.possible_days)["preferred"])
    st.markdown(
        f'<div class="kp-money kp-small">'
        f'{"You are cooking " + _times(len(mine)) if mine else "You are not cooking"}</div>',
        unsafe_allow_html=True,
    )
    st.caption(f"{context.month_name} {context.year} · the schedule is written")
    # The swap dialog needs the month's people, and Plan has already read them
    # for this sheet — build_month_context adds no round trip here.
    day_context = build_month_context(service, context.sheet_name, include_month_entries=False)
    for row in mine:
        weekday = ENGLISH_WEEKDAY_NAMES[calendar.weekday(context.year, context.month, row.day)]
        note = "one you asked for" if row.day in preferred else ""
        title = f"{weekday} {row.day} {context.month_name}"
        if day_context is None:
            _dinner_line(title, note)
            continue
        # The same swap as on Dinner, on the tab where you are looking at next
        # month's nights. Dinner opens on the month you are living in, so
        # sending people there to trade a night in the month they have just
        # answered for was a tab change and a month change to reach a control
        # that fits here.
        _ledger_row(
            title=title,
            note=note,
            key=f"plannight_{context.sheet_name}_{row.day}",
            help_text="Swap this dinner with somebody",
            on_edit=_swap_dialog,
            args=(service, day_context, context.sheet_name, row.day, room_entry.label, rows),
            icon=":material/swap_horiz:",
        )
    if not mine:
        st.caption("Nobody put you down for a dinner this month.")
    else:
        st.caption(
            "Use the arrows to hand a night over, or trade it for one of theirs."
        )
    return True


def _times(count: int) -> str:
    if count == 1:
        return "once"
    if count == 2:
        return "twice"
    return f"{count} times"


def _start_editing(key: str) -> None:
    st.session_state[EDIT_KEY] = key


def _stop_editing() -> None:
    st.session_state.pop(EDIT_KEY, None)


def render_planning_view(service: SheetsService) -> None:
    """The Plan tab: your own dates, and nobody else's."""
    context = _planning_context(service)
    if context is None:
        return

    st.subheader(f"{context.month_name} {context.year}")
    ahead = upcoming_month()
    if (context.month_name, context.year) != ahead:
        # Say why you are looking at the month you are in rather than the one
        # you came to answer for, or the heading reads as the app's mistake.
        st.caption(f"{ahead[0]} is not ready to plan yet.")

    room_entry, claimed = _planning_room_entry(service, context)
    if room_entry is None:
        if claimed:
            st.info(
                f"You are not on the {context.month_name} {context.year} sheet — room {claimed} "
                "belongs to someone else that month. Ask an admin to add you."
            )
        else:
            st.info("Pick your room at the top to answer for yourself.")
        return

    if room_entry.label != claimed:
        st.caption(f"You have room {room_entry.label} in {context.month_name}.")

    stored = context.stored_entries.get(room_entry.label)
    answered = has_answered(stored, context.possible_days, context.year, context.month)
    on_the_rota = room_entry.label.isdigit()
    states_key = _load_states(context, room_entry.label, stored, on_the_rota=on_the_rota)
    states = st.session_state[states_key]

    scheduled = render_schedule_card(service, context, room_entry, states)
    if scheduled:
        st.divider()

    editing = st.session_state.get(EDIT_KEY) == states_key or not answered
    if editing:
        _render_editor(service, context, room_entry, states_key, stored, answered, on_the_rota)
    else:
        render_answer_summary(context, states, bool(stored and stored.limit_one_day))
        st.button(
            "Change my answer",
            key="planning_edit",
            icon=":material/edit_calendar:",
            width="stretch",
            on_click=_start_editing,
            args=(states_key,),
        )

    _render_progress(context, answered)


def _render_progress(context: PlanningContext, answered: bool) -> None:
    total = len(_rota_entries(context))
    done = _answered_count(context)
    if not total:
        return
    remaining = max(total - done, 0)
    if answered:
        others = max(done - 1, 0)
        st.caption(
            f"You and {others} {'other' if others == 1 else 'others'} have answered · "
            f"{remaining} to go"
            if others
            else f"You have answered · {remaining} to go"
        )
    else:
        st.caption(f"{done} of {total} have answered so far.")


def _render_editor(
    service: SheetsService,
    context: PlanningContext,
    room_entry,
    states_key: str,
    stored,
    answered: bool,
    on_the_rota: bool = True,
) -> None:
    states = st.session_state[states_key]
    if on_the_rota:
        st.caption("Tap a day to change it. Every dinner day starts as one you can cook.")
    else:
        st.caption(
            "You do not have a room this month, so you are not on the cooking rota and nobody "
            "will put you down for a night. Tap any day you would like to cook anyway."
        )

    cannot = st.checkbox(
        "I can't cook at all this month",
        value=_cannot_at_all(states, context.possible_days),
        key=f"{states_key}_none",
    )
    limit_one_day = st.checkbox(
        "At most once this month",
        value=bool(stored and stored.limit_one_day),
        disabled=cannot,
        key=f"{states_key}_once",
    )

    render_day_grid(context, states_key, override=CANT if cannot else "")
    _render_legend()

    if st.button("Save my answer", type="primary", width="stretch", key="planning_save"):
        days = (
            {"available": [], "unavailable": list(context.possible_days), "preferred": []}
            if cannot
            else entry_days(states, context.possible_days)
        )
        entry = PlanningEntry(
            person=room_entry.name or room_entry.label,
            room_number=room_entry.label,
            available_dates=format_days([str(day) for day in days["available"]]),
            unavailable_dates=format_days([str(day) for day in days["unavailable"]]),
            preferred_dates=format_days([str(day) for day in days["preferred"]]),
            limit_one_day=limit_one_day and not cannot,
        )
        try:
            service.save_planning_entries(context.month_name, context.year, [entry])
        except ValueError as exc:
            show_user_error(st, exc, "Could not save your dates")
            return
        data.clear_planning()
        bump_cache_version()
        _stop_editing()
        # Without the rerun the page keeps the counts it read BEFORE the write,
        # so answering never moves the number underneath it.
        st.rerun()

    if answered:
        st.button("Cancel", key="planning_cancel", width="stretch", on_click=_stop_editing)
