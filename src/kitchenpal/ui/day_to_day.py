import calendar
import html
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

import streamlit as st

from ..a1 import range_end_row as _range_end_row, range_start_row as _range_start_row
from ..constants import (
    ANDET_ROW_CAPACITY,
    DANISH_TO_ENGLISH_MONTH,
    ENGLISH_MONTHS,
    ENGLISH_TO_DANISH_MONTH,
    PURCHASE_LOOKUP_RANGE,
    PURCHASE_ROW_CAPACITY,
    TRANSACTION_ROW_CAPACITY,
)
from ..sheets.utils import is_occupied_account, is_room_label, ordinal, parse_month_sheet_name
from ..sheets_service import DayRow, SheetsService
from . import data
from .calendar_grid import render_grid
from .errors import show_user_error, user_error_message
from .identity import current_room, default_index
from .month import current_month_sheet, is_current_month, render_month_picker


@dataclass(frozen=True)
class DayToDayContext:
    selected_sheet_name: str
    room_entries: list
    signup_room_entries: list
    room_name_by_label: dict[str, str]
    room_labels: list[str]
    signup_room_labels: list[str]
    month_entries: object | None = None


def _default_day_index() -> int:
    return max(0, min(datetime.now().day - 1, 30))


def _ordinal(n: int) -> str:
    """Just the suffix: callers write f"{day}{_ordinal(day)}"."""
    return ordinal(n)[len(str(int(n))):]


def _english_month(month_raw: str) -> str:
    if not month_raw:
        return ""
    m = month_raw.strip()
    for en in ENGLISH_MONTHS:
        if m.lower() == en.lower() or m.lower()[:3] == en.lower()[:3]:
            return en

    return DANISH_TO_ENGLISH_MONTH.get(m.title(), m)


def _delete_confirmation_key(kind: str, worksheet_name: str) -> str:
    return f"day_to_day_confirm_delete_{kind}:{worksheet_name}"


def _meal_details_saved_key(worksheet_name: str, day: int) -> str:
    return f"day_to_day_meal_details_saved:{worksheet_name}:{day}"


def _display_box():
    try:
        return st.container(border=True)
    except TypeError:
        return st.container()


def _default_sheet_index(sheets_list: list[str]) -> int:
    current_month_name = ENGLISH_MONTHS[datetime.now().month - 1]
    current_month_candidates = [f"{current_month_name} {datetime.now().year}"]

    danish_month = ENGLISH_TO_DANISH_MONTH.get(current_month_name)
    if danish_month:
        current_month_candidates.append(f"{danish_month} {datetime.now().year}")

    for candidate in current_month_candidates:
        if candidate in sheets_list:
            return sheets_list.index(candidate)

    return 0


def _month_sheet_names(sheet_names: list[str]) -> list[str]:
    return [sheet_name for sheet_name in sheet_names if parse_month_sheet_name(sheet_name) is not None]


def _valid_days_for_sheet(worksheet_name: str) -> list[int]:
    parsed = parse_month_sheet_name(worksheet_name)
    if parsed is None:
        return list(range(1, 32))
    month, year = parsed
    return list(range(1, calendar.monthrange(year, month)[1] + 1))


def _default_day_for_sheet(worksheet_name: str) -> int:
    days = _valid_days_for_sheet(worksheet_name)
    today = datetime.now()
    parsed = parse_month_sheet_name(worksheet_name)
    if parsed == (today.month, today.year):
        return min(today.day, days[-1])
    return days[0]


def _day_selectbox(label: str, worksheet_name: str, key: str, prefer_today: bool = True) -> int:
    days = _valid_days_for_sheet(worksheet_name)
    default_day = _default_day_for_sheet(worksheet_name) if prefer_today else days[0]
    return st.selectbox(label, days, index=days.index(default_day), key=key)


def _format_amount_dkk(amount: float) -> str:
    return f"{amount:.2f} DKK"


def _signed_amount(amount: float) -> str:
    """A ledger reads as movement, so every row carries its direction."""
    text = _format_amount_dkk(abs(amount))
    return f"-{text}" if amount < 0 else f"+{text}"


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def _format_optional_amount_dkk(amount: float) -> str:
    return _format_amount_dkk(amount) if amount else "Not set"


def _meal_price_for_edit(amount: float) -> str:
    return f"{amount:.2f}" if amount else ""


def _signed_up_count(value: str) -> int:
    try:
        return int(float(str(value or "0").replace(",", ".")))
    except (TypeError, ValueError):
        return 0


def _meal_budget(signed_up: str) -> float:
    return _signed_up_count(signed_up) * 35


def _meal_price_per_person(signed_up: str, meal_price: float) -> float:
    signed_up_count = _signed_up_count(signed_up)
    if not signed_up_count or not meal_price:
        return 0.0
    return meal_price / signed_up_count


def _meal_price_per_person_display(signed_up: str, meal_price: float) -> str:
    price_per_person = _meal_price_per_person(signed_up, meal_price)
    return _format_optional_amount_dkk(price_per_person)


def _display_chef(chef: str, room_name_by_label: dict[str, str]) -> str:
    chef_label = str(chef).strip()
    chef_name = room_name_by_label.get(chef_label, "")
    if chef_name:
        return f"{chef_label} — {chef_name}"
    return chef_label or "Not assigned"


def _selected_day_display(month_part: str, selected_day: int) -> str:
    return f"{month_part} {selected_day}{_ordinal(selected_day)}"


def _sheet_year(worksheet_name: str) -> int:
    parts = worksheet_name.split()
    if len(parts) >= 2:
        try:
            return int(parts[-1])
        except ValueError:
            pass
    return datetime.now().year


def _parse_sheet_date(value: str, worksheet_name: str) -> date | None:
    """The sheet writes 03/06, but residents type 2026-06-03 and 3/6/2026 too."""
    text = str(value or "").strip()
    if not text:
        return None

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if fmt == "%d/%m":
            return parsed.replace(year=_sheet_year(worksheet_name)).date()
        return parsed.date()

    return None


def _transaction_date_for_edit(value: str, worksheet_name: str) -> date:
    return _parse_sheet_date(value, worksheet_name) or datetime.now().date()


def _short_date(value: str, worksheet_name: str) -> str:
    parsed = _parse_sheet_date(value, worksheet_name)
    if parsed is None:
        return str(value or "").strip() or "No date"
    return f"{parsed.day} {calendar.month_abbr[parsed.month]}"


def _newest_first(entries, worksheet_name: str):
    """Undated rows sort last; row order breaks ties, so the sheet still shows through."""
    return sorted(
        entries,
        key=lambda entry: (_parse_sheet_date(entry.date, worksheet_name) or date.min, entry.row_number),
        reverse=True,
    )


def _purchase_date_for_edit(value: str, worksheet_name: str) -> date:
    return _transaction_date_for_edit(value, worksheet_name)


def _next_available_row(entries, start_row: int, end_row: int | None = None) -> int | None:
    used_rows = {entry.row_number for entry in entries}
    if end_row is None:
        end_row = max(used_rows, default=start_row - 1) + 1
    for row_number in range(start_row, end_row + 1):
        if row_number not in used_rows:
            return row_number
    return None


def _person_caption(label: str, room_name_by_label: dict[str, str]) -> str:
    """"Julia · 346" — the name first, because that is how people find themselves."""
    text = str(label or "").strip()
    name = room_name_by_label.get(text, "")
    return f"{name} · {text}" if name else (text or "Unknown")


def _room_display_factory(room_name_by_label: dict[str, str]):
    def room_display(label: str) -> str:
        room_name = room_name_by_label.get(label, "")
        return f"{label} — {room_name}" if room_name else label

    return room_display


def identity_room_entries(service: SheetsService):
    """The people the app can be: this month's accounts."""
    sheet_name = current_month_sheet(service)
    if sheet_name is None:
        return []
    return [entry for entry in data.room_entries(service, sheet_name) if entry.label.isdigit() or entry.name]


def _load_context(service: SheetsService, *, include_month_entries: bool) -> DayToDayContext | None:
    selected_sheet_name = render_month_picker(service)
    if selected_sheet_name is None:
        st.warning("No month sheets are available yet.")
        return None
    return build_month_context(service, selected_sheet_name, include_month_entries=include_month_entries)


def build_month_context(
    service: SheetsService, selected_sheet_name: str, *, include_month_entries: bool
) -> DayToDayContext | None:
    """The month's people and rows, without asking which month."""
    room_entries = data.room_entries(service, selected_sheet_name)
    if not room_entries:
        st.warning("No room mapping is available on this sheet.")
        return None

    signup_room_entries = [entry for entry in room_entries if entry.signup_column is not None]
    room_name_by_label = {entry.label: entry.name for entry in room_entries}
    room_labels = [entry.label for entry in room_entries]
    signup_room_labels = [entry.label for entry in signup_room_entries]
    month_entries = data.month_entries(service, selected_sheet_name) if include_month_entries else None

    return DayToDayContext(
        selected_sheet_name=selected_sheet_name,
        room_entries=room_entries,
        signup_room_entries=signup_room_entries,
        room_name_by_label=room_name_by_label,
        room_labels=room_labels,
        signup_room_labels=signup_room_labels,
        month_entries=month_entries,
    )


def _day_display(worksheet_name: str, selected_day: int) -> str:
    month_part_raw = worksheet_name.split()[0] if worksheet_name else ""
    month_part = _english_month(month_part_raw)
    return _selected_day_display(month_part, selected_day)


def _render_meal_metrics(day_details, selected_day_display: str, room_name_by_label: dict[str, str]):
    top_col1, top_col2, top_col3 = st.columns(3)
    top_col1.metric("Date", selected_day_display)
    top_col2.metric("Signed up", day_details.signed_up)
    top_col3.metric("Host", _display_chef(day_details.chef, room_name_by_label))

    bottom_col1, bottom_col2, bottom_col3 = st.columns(3)
    bottom_col1.metric("Expected budget", _format_amount_dkk(_meal_budget(day_details.signed_up)))
    bottom_col2.metric("Actual total cost", _format_optional_amount_dkk(day_details.meal_price))
    bottom_col3.metric("Actual cost/person", _meal_price_per_person_display(day_details.signed_up, day_details.meal_price))


def _render_menu_box(day_details, heading: str = "Dinner"):
    with _display_box():
        st.markdown(f"**{heading}**")
        st.write(day_details.menu or "No menu yet")
        if day_details.menu_description:
            st.caption(day_details.menu_description)


ENGLISH_WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

DINNER_DAY_KEY = "dinner_day"


def upcoming_dinners(rows, from_day: int, limit: int = 4):
    """The next few dinners that someone is actually cooking."""
    return [row for row in rows if row.day > from_day and (row.chef or row.menu)][:limit]


def my_cooking_nights(rows, room: str):
    return [row for row in rows if room and row.chef == room]


def signed_up_names(row, room_name_by_label: dict[str, str]) -> list[str]:
    """Who is eating, from the month read — no extra call per day."""
    people = []
    for label, count in row.signups.items():
        if count <= 0:
            continue
        name = room_name_by_label.get(label) or label
        people.append(f"{name} ({count})" if count > 1 else name)
    return people


def _weekday_name(worksheet_name: str, day: int) -> str:
    parsed = parse_month_sheet_name(worksheet_name)
    if parsed is None:
        return ""
    month, year = parsed
    try:
        return ENGLISH_WEEKDAY_NAMES[calendar.weekday(year, month, day)]
    except ValueError:
        return ""


def _short_day(worksheet_name: str, day: int) -> str:
    weekday = _weekday_name(worksheet_name, day)
    return f"{weekday[:3]} {day}" if weekday else str(day)


def _dinner_line(text: str, note: str, *, dim: bool = False, strong: bool = False, tone: str = "") -> None:
    classes = "kp-line" + (" kp-past" if dim else "") + (" kp-mine" if strong else "")
    note_classes = "kp-note" + (f" {tone}" if tone else "")
    st.markdown(
        f'<div class="{classes}"><span>{text}</span><span class="{note_classes}">{note}</span></div>',
        unsafe_allow_html=True,
    )


def _host_caption(chef: str, room_name_by_label: dict[str, str]) -> str:
    label = str(chef).strip()
    if not label:
        return "nobody is cooking yet"
    name = room_name_by_label.get(label)
    return f"{name} is cooking" if name else f"{label} is cooking"


def render_dinner_view(service: SheetsService):
    sheet_name = current_month_sheet(service)
    if sheet_name is None:
        st.warning("No month sheets are available yet.")
        return

    days = _valid_days_for_sheet(sheet_name)
    default_day = _default_day_for_sheet(sheet_name)
    if st.session_state.get(DINNER_DAY_KEY) not in days:
        st.session_state.pop(DINNER_DAY_KEY, None)
    selected_day = st.session_state.get(DINNER_DAY_KEY, default_day)

    context = build_month_context(service, sheet_name, include_month_entries=False)
    if context is None:
        return
    if not context.signup_room_labels:
        st.warning("No rooms can sign up on this sheet.")
        return

    room = current_room(context.room_entries)
    rows = data.day_rows(service, sheet_name)
    row = next(
        (candidate for candidate in rows if candidate.day == selected_day),
        DayRow(day=selected_day, chef="", menu="", menu_description="", signed_up=0, meal_price=0.0, signups={}),
    )

    showing_today = selected_day == default_day and is_current_month(sheet_name)
    st.title("Tonight" if showing_today else _day_display(sheet_name, selected_day))
    st.caption(
        f"{_weekday_name(sheet_name, selected_day)} {_day_display(sheet_name, selected_day)}"
        f" · {_host_caption(row.chef, context.room_name_by_label)}"
    )

    _render_dinner_card(row)
    _render_cook_controls(service, context, sheet_name, selected_day, row, room)
    _render_signup_controls(service, context, sheet_name, selected_day, row, room)
    _render_other_day_picker(service, sheet_name, days, selected_day, rows, room)

    upcoming = upcoming_dinners(rows, selected_day)
    if upcoming:
        st.markdown("###### Coming up")
        for entry in upcoming:
            cook = _host_caption(entry.chef, context.room_name_by_label)
            note = "you're in" if room and entry.signups.get(room, 0) else "—"
            _dinner_line(f"{_short_day(sheet_name, entry.day)} · {cook}", note, strong=entry.chef == room)

    nights = my_cooking_nights(rows, room)
    if nights:
        st.markdown("###### Your nights this month")
        for entry in nights:
            done = is_current_month(sheet_name) and entry.day < default_day
            note = _format_amount_dkk(entry.meal_price) if entry.meal_price else ("cooked" if done else "add menu")
            if done:
                _dinner_line(_short_day(sheet_name, entry.day), note, dim=True)
                continue
            _ledger_row(
                title=_short_day(sheet_name, entry.day),
                note=note,
                key=f"mynight_{sheet_name}_{entry.day}",
                help_text="Swap this dinner with somebody",
                on_edit=_swap_dialog,
                args=(service, context, sheet_name, entry.day, room, rows),
                icon=":material/swap_horiz:",
            )

    signed_people = signed_up_names(row, context.room_name_by_label)
    with st.expander(f"Who is eating ({row.signed_up})"):
        if signed_people:
            for name in signed_people:
                st.markdown(f"- {name}")
        else:
            st.caption("No one is signed up yet.")

    # No separate "Host dinner" screen to know about: the fields show up on the
    # day you are cooking. On anyone else's day they stay behind one button, for
    # when you are covering for them.
    if room and row.chef == room:
        st.subheader("You are cooking")
        render_dish_form(service, context, selected_day, row)
    elif st.button("Add the menu for this dinner", type="tertiary", key=f"dish_for_{sheet_name}_{selected_day}"):
        _dish_dialog(service, context, selected_day, row)


def _take_dinner(service, sheet_name: str, day: int, label: str, name: str) -> None:
    try:
        service.claim_dinner(sheet_name, day, label, by=label)
    except ValueError as exc:
        st.session_state[_signup_error_key(sheet_name, day)] = user_error_message(
            exc, "Could not put you down to cook"
        )
        return
    data.clear_dinners()
    st.toast(f"{name} is cooking on the {day}{_ordinal(day)}.")


@st.dialog("Who is cooking?")
def _cook_dialog(service, context, sheet_name: str, day: int) -> None:
    people = [
        entry
        for entry in context.signup_room_entries
        if is_occupied_account(entry.label, entry.name)
    ]
    if not people:
        st.caption("Nobody on this sheet can be put down to cook.")
        return
    chosen = st.selectbox(
        "Who is cooking?",
        people,
        format_func=lambda entry: entry.name or entry.label,
        key=f"cook_who_{sheet_name}_{day}",
    )
    if st.button("Put them down", type="primary", use_container_width=True, key=f"cook_go_{sheet_name}_{day}"):
        _take_dinner(service, sheet_name, day, chosen.label, chosen.name or chosen.label)
        st.rerun()


def _render_cook_controls(service, context, sheet_name: str, day: int, row, room: str) -> None:
    """A night nobody has taken should not be a dead end.

    Taking it yourself is the common case and stays one tap; putting somebody
    else down is the same action with a picker in front of it.
    """
    if row.chef:
        return
    if is_current_month(sheet_name) and day < _default_day_for_sheet(sheet_name):
        return

    if room and st.button(
        "I'll cook this dinner",
        icon=":material/skillet:",
        use_container_width=True,
        key=f"cook_mine_{sheet_name}_{day}",
    ):
        _take_dinner(service, sheet_name, day, room, "You")
        st.rerun()
    st.button(
        "Someone else is cooking",
        type="tertiary",
        use_container_width=True,
        key=f"cook_other_{sheet_name}_{day}",
        on_click=_cook_dialog,
        args=(service, context, sheet_name, day),
    )


def _render_dinner_card(row) -> None:
    price_line = _meal_price_per_person_display(row.signed_up, row.meal_price)
    details = f"{row.signed_up} eating"
    if price_line != "Not set":
        details += f" · {price_line} each"
    else:
        details += f" · {_format_amount_dkk(_meal_budget(row.signed_up))} expected"

    with st.container(border=True):
        st.markdown('<div class="kp-kicker">On the menu</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="kp-dish">{row.menu or "No menu yet"}</div>', unsafe_allow_html=True)
        if row.menu_description:
            st.caption(row.menu_description)
        st.markdown(f'<div class="kp-note">{details}</div>', unsafe_allow_html=True)


def _signup_error_key(worksheet_name: str, day: int) -> str:
    return f"dinner_signup_error_{worksheet_name}_{day}"


def _render_signup_controls(service, context, sheet_name, selected_day, row, room) -> None:
    if not room:
        st.info("Pick your room at the top to sign up with one tap.")
        return
    if room not in context.signup_room_labels:
        st.info("This account cannot sign up for dinner on this sheet.")
        return

    my_count = row.signups.get(room, 0)

    def save(count: int) -> None:
        # An on_click callback: Streamlit reruns by itself afterwards, and the
        # line above the buttons is the confirmation.
        try:
            service.update_dish_signup(sheet_name, selected_day, room, count)
            data.clear_dinners()
        except ValueError as exc:
            st.session_state[_signup_error_key(sheet_name, selected_day)] = user_error_message(
                exc, "Could not save signup"
            )

    error = st.session_state.pop(_signup_error_key(sheet_name, selected_day), "")
    if error:
        st.error(error)

    if my_count:
        guests = my_count - 1
        st.success(f"You're eating{f' with {guests} guest' + ('s' if guests > 1 else '') if guests else ''}.")
        guests_key = f"dinner_guests_{sheet_name}_{selected_day}"

        def save_guests() -> None:
            save(1 + int(st.session_state.get(guests_key, 0)))

        left, right = st.columns([2, 1], vertical_alignment="bottom")
        left.number_input(
            "Guests",
            min_value=0,
            max_value=20,
            step=1,
            value=guests,
            key=guests_key,
            help="People you are bringing. Each one pays a share, and the change saves itself.",
            on_change=save_guests,
        )
        right.button(
            "Not eating",
            key=f"dinner_cancel_{sheet_name}_{selected_day}",
            use_container_width=True,
            on_click=save,
            args=(0,),
        )
        return

    left, right = st.columns([1, 2], vertical_alignment="bottom")
    guests = left.number_input(
        "Guests",
        min_value=0,
        max_value=20,
        step=1,
        value=0,
        key=f"dinner_guests_{sheet_name}_{selected_day}",
        help="People you are bringing. Each one pays a share.",
    )
    right.button(
        "I'm eating",
        type="primary",
        key=f"dinner_join_{sheet_name}_{selected_day}",
        use_container_width=True,
        on_click=save,
        args=(1 + guests,),
    )


def _pick_day(day: int) -> None:
    st.session_state[DINNER_DAY_KEY] = day


def _render_other_day_picker(service, sheet_name, days, selected_day, rows, room) -> None:
    """A month you can see, rather than a dropdown of numbers.

    The days somebody is cooking, the ones that are yours, and the one you are
    looking at are all visible at once — which is the question people actually
    bring to a day picker.
    """
    parsed = parse_month_sheet_name(sheet_name)
    if parsed is None:
        with st.expander("Choose day"):
            render_month_picker(service)
            st.selectbox("Day", days, index=days.index(selected_day), key=DINNER_DAY_KEY)
        return

    month, year = parsed
    chef_by_day = {row.day: row.chef for row in rows}
    day_set = set(days)

    def state_for(day: int) -> str:
        if day not in day_set:
            return ""
        if day == selected_day:
            return "here"
        if room and chef_by_day.get(day) == room:
            return "mine"
        # "free" gets no fill: a day nobody has taken must not look like a day
        # somebody has.
        return "cook" if chef_by_day.get(day) else "free"

    with st.expander("Choose day"):
        render_grid(
            key=f"dinnerday_{sheet_name}",
            year=year,
            month=month,
            day_state=state_for,
            on_click=_pick_day,
            args_for=lambda day: (day,),
        )
        st.markdown(
            "<div class='kpal-legend'>"
            "<span><i class='kpal-sw kpal-sw-mine'></i>your night</span>"
            "<span><i class='kpal-sw kpal-sw-can'></i>someone is cooking</span>"
            "<span><i class='kpal-sw kpal-sw-off'></i>nobody yet</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        render_month_picker(service)


@st.dialog("Swap this dinner")
def _swap_dialog(service: SheetsService, context, sheet_name: str, day: int, room: str, rows) -> None:
    """Bytte madklub: give a night away, or trade it for one of theirs.

    The chef is one cell per day, so both are the same write. Nobody is asked to
    consent — this is a house, not a workflow engine — but both people end up in
    the Log, which is what an argument about it would need.
    """
    others = [
        entry
        for entry in context.signup_room_entries
        if entry.label != room and is_occupied_account(entry.label, entry.name)
    ]
    if not others:
        st.caption("There is nobody else on this sheet to swap with.")
        return

    st.markdown(f"**{_weekday_name(sheet_name, day)} {_day_display(sheet_name, day)}** is yours.")
    taker = st.selectbox(
        "Who takes it?",
        others,
        format_func=lambda entry: entry.name or entry.label,
        key=f"swap_taker_{sheet_name}_{day}",
    )

    theirs = [entry.day for entry in rows if entry.chef == taker.label and entry.day != day]
    other_day = None
    if theirs:
        choice = st.selectbox(
            "And you take",
            [None] + theirs,
            format_func=lambda value: (
                "nothing — they just take mine" if value is None else _short_day(sheet_name, value)
            ),
            key=f"swap_theirs_{sheet_name}_{day}",
        )
        other_day = choice
    else:
        st.caption(f"{taker.name or taker.label} is not cooking any other night this month.")

    # A swap is its own inverse, so swap_dinner's "is this still your night?"
    # guard cannot tell a replayed click from a genuine swap back the other way.
    # One test click ended up applied twice from a reconnecting tab, so the
    # dialog refuses to fire the same swap twice within a session.
    done_key = f"swapped_{sheet_name}_{day}_{taker.label}_{other_day}"
    if not st.button("Swap", type="primary", use_container_width=True, key=f"swap_go_{sheet_name}_{day}"):
        return
    if st.session_state.get(done_key):
        st.caption("That swap has already gone through.")
        return
    try:
        service.swap_dinner(sheet_name, day, room, taker.label, other_day=other_day, by=room)
    except ValueError as exc:
        show_user_error(st, exc, "Could not swap the dinner")
        return
    st.session_state[done_key] = True
    data.clear_dinners()
    st.toast(
        f"{taker.name or taker.label} has the {day}{_ordinal(day)}"
        + (f", and you have the {other_day}{_ordinal(other_day)}." if other_day else ".")
    )
    st.rerun()


@st.dialog("Menu and cost")
def _dish_dialog(service, context, selected_day, day_details) -> None:
    render_dish_form(service, context, selected_day, day_details)


def render_dish_form(service: SheetsService, context: DayToDayContext, selected_day: int, day_details):
    """The host's own fields. Takes anything with menu, menu_description and meal_price."""
    if st.session_state.pop(_meal_details_saved_key(context.selected_sheet_name, selected_day), False):
        st.success("Dinner details have been updated.")

    with st.form(key=f"dish_form_{context.selected_sheet_name}_{selected_day}"):
        dish_name = st.text_input(
            "Dish name",
            value=day_details.menu,
            key=f"dish_name_{context.selected_sheet_name}_{selected_day}",
        )
        menu_description = st.text_area(
            "Menu details",
            value=day_details.menu_description,
            key=f"dish_description_{context.selected_sheet_name}_{selected_day}",
        )
        meal_price = st.text_input(
            "Actual total cost",
            value=_meal_price_for_edit(day_details.meal_price),
            placeholder="Example: 350.00",
            help="Leave blank if the final cost is not known yet.",
            key=f"dish_price_{context.selected_sheet_name}_{selected_day}",
        )
        submitted = st.form_submit_button("Save dinner details", type="primary", use_container_width=True)

    if submitted:
        if not dish_name.strip() and not menu_description.strip() and not str(meal_price or "").strip():
            st.error("Add a dish name, menu details, or total cost before saving.")
            return
        try:
            service.update_meal_details(
                context.selected_sheet_name,
                selected_day,
                dish_name,
                meal_price,
                menu_description,
            )
            data.clear_dinners()
            st.session_state[_meal_details_saved_key(context.selected_sheet_name, selected_day)] = True
            st.rerun()
        except ValueError as exc:
            show_user_error(st, exc, "Could not save dinner details")


STATEMENT_LABELS = {
    "carried_in": "Balance from last month",
    "dinners": "Dinners eaten",
    "cooked": "Dinners you cooked",
    "drinks": "Drinks",
    "purchases": "Shared purchases you paid for",
    "payments": "Kitchen fund payments",
    "dues": "Monthly dues",
    "interest": "Interest",
}
STATEMENT_ORDER = ["carried_in", "dinners", "cooked", "drinks", "purchases", "payments", "dues", "interest"]


def _balance_sentence(balance: float) -> str:
    if balance < 0:
        return f"You owe the kitchen fund {_format_amount_dkk(abs(balance))}."
    if balance > 0:
        return "The kitchen fund owes you this."
    return "You are square with the kitchen fund."


def statement_detail(key: str, *, day_rows, room: str, drinks, purchases) -> str:
    """The human count behind a line, when the app can know it."""
    if key == "dinners":
        meals = sum(row.signups.get(room, 0) for row in day_rows)
        return f"{meals} meal{'s' if meals != 1 else ''}"
    if key == "cooked":
        nights = len(my_cooking_nights(day_rows, room))
        return f"{nights} night{'s' if nights != 1 else ''}"
    if key == "drinks":
        entry = next((item for item in drinks if item.room == room), None)
        if entry is None:
            return ""
        parts = []
        if entry.beer_soda:
            parts.append(f"{entry.beer_soda} beer/soda")
        if entry.wine:
            parts.append(f"{entry.wine} wine")
        return ", ".join(parts)
    if key == "purchases":
        mine = [item for item in purchases if item.room == room]
        return f"{len(mine)} purchase{'s' if len(mine) != 1 else ''}" if mine else ""
    return ""


def _render_statement(statement, *, day_rows, room, drinks, purchases) -> None:
    with st.container(border=True):
        # Red when you owe, green when you are owed: the one number people open
        # this tab for should not need reading to know which way it points.
        tone = "kp-owed" if statement.balance < 0 else ("kp-good" if statement.balance > 0 else "")
        st.markdown('<div class="kp-kicker">Your balance</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="kp-money {tone}">{_format_amount_dkk(statement.balance)}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(f'<div class="kp-note">{_balance_sentence(statement.balance)}</div>', unsafe_allow_html=True)

    lines = [(key, statement.components.get(key, 0.0)) for key in STATEMENT_ORDER]
    lines = [(key, amount) for key, amount in lines if amount]
    if not lines:
        st.caption("Nothing has happened on your account this month yet.")
        return

    st.markdown("###### This month")
    for key, amount in lines:
        detail = statement_detail(key, day_rows=day_rows, room=room, drinks=drinks, purchases=purchases)
        text = STATEMENT_LABELS[key] + (f" · {detail}" if detail else "")
        sign = "+" if amount > 0 else "−"
        _dinner_line(
            text,
            f"{sign}{_format_amount_dkk(abs(amount))}",
            tone="kp-good" if amount > 0 else "kp-owed",
        )


@st.dialog("Add drinks")
def _drinks_dialog(service: SheetsService, context: DayToDayContext, room: str) -> None:
    add_drinks_form(service, context, room)


@st.dialog("Add a shared purchase")
def _purchase_dialog(service: SheetsService, context: DayToDayContext, room: str) -> None:
    add_purchase_form(service, context, room)


@st.dialog("Kitchen fund payment")
def _payment_dialog(service: SheetsService, context: DayToDayContext, room: str) -> None:
    add_payment_form(service, context, room)


@st.dialog("Add a shared cost")
def _andet_dialog(service: SheetsService, context: DayToDayContext, room: str, entry=None) -> None:
    add_andet_form(service, context, room, entry)


def _who_paid_selectbox(context: DayToDayContext, entry_room: str, key: str) -> str:
    """House can move a row to the right person; Me never needs to."""
    labels = list(context.room_labels)
    if entry_room and entry_room not in labels:
        labels.append(entry_room)
    return st.selectbox(
        "Who paid",
        labels,
        index=labels.index(entry_room) if entry_room in labels else 0,
        format_func=_room_display_factory(context.room_name_by_label),
        key=key,
    )


@st.dialog("Edit purchase")
def _edit_purchase_dialog(
    service: SheetsService, context: DayToDayContext, entry, allow_reassign: bool = False
) -> None:
    with st.form(key=f"edit_purchase_form_{entry.row_number}"):
        purchase_room = (
            _who_paid_selectbox(context, entry.room, f"edit_purchase_room_{entry.row_number}")
            if allow_reassign
            else entry.room
        )
        item = st.text_input(
            "What was bought?", value=entry.item, key=f"edit_purchase_item_{entry.row_number}"
        )
        purchase_date = st.date_input(
            "Date",
            value=_purchase_date_for_edit(entry.date, context.selected_sheet_name),
            key=f"edit_purchase_date_{entry.row_number}",
        )
        amount = st.number_input(
            "Total price (negative for refunds)",
            value=float(entry.amount),
            step=0.01,
            key=f"edit_purchase_cost_{entry.row_number}",
        )
        save = st.form_submit_button("Save", type="primary", use_container_width=True)

    removed = _delete_control("purchase", context, entry.row_number, "purchase")

    if save:
        if not str(item).strip():
            st.error("Add what was bought before saving.")
            return
        if amount == 0:
            st.error("Add a non-zero price before saving (negative for refunds).")
            return
        try:
            service.update_purchase(
                context.selected_sheet_name, entry.row_number, purchase_room, purchase_date, item, amount
            )
        except ValueError as exc:
            show_user_error(st, exc, "Could not save the purchase")
            return
    elif removed:
        try:
            service.delete_purchase(context.selected_sheet_name, entry.row_number)
        except ValueError as exc:
            show_user_error(st, exc, "Could not delete the purchase")
            return
    else:
        return

    data.clear_money()
    st.rerun()


@st.dialog("Edit payment")
def _edit_payment_dialog(
    service: SheetsService, context: DayToDayContext, entry, allow_reassign: bool = False
) -> None:
    types = ["Payment to kitchen fund", "Payout from kitchen fund"]
    if entry.transaction_type and entry.transaction_type not in types:
        types.append(entry.transaction_type)
    with st.form(key=f"edit_payment_form_{entry.row_number}"):
        payment_room = (
            _who_paid_selectbox(context, entry.room, f"edit_tx_room_{entry.row_number}")
            if allow_reassign
            else entry.room
        )
        payment_type = st.selectbox(
            "Payment type",
            types,
            index=types.index(entry.transaction_type) if entry.transaction_type in types else 0,
            key=f"edit_tx_type_{entry.row_number}",
        )
        amount = st.number_input(
            "Amount (DKK)",
            value=abs(float(entry.amount)),
            min_value=0.0,
            step=0.01,
            key=f"edit_tx_amount_{entry.row_number}",
        )
        payment_date = st.date_input(
            "Date",
            value=_transaction_date_for_edit(entry.date, context.selected_sheet_name),
            key=f"edit_tx_date_{entry.row_number}",
        )
        save = st.form_submit_button("Save", type="primary", use_container_width=True)

    removed = _delete_control("payment", context, entry.row_number, "payment")

    if save:
        if amount <= 0:
            st.error("Add an amount greater than 0 before saving.")
            return
        try:
            service.update_transaction(
                context.selected_sheet_name, entry.row_number, payment_room, payment_type, amount, payment_date
            )
        except ValueError as exc:
            show_user_error(st, exc, "Could not save the payment")
            return
    elif removed:
        try:
            service.delete_transaction(context.selected_sheet_name, entry.row_number)
        except ValueError as exc:
            show_user_error(st, exc, "Could not delete the payment")
            return
    else:
        return

    data.clear_money()
    st.rerun()


@st.dialog("Correct drinks")
def _edit_drinks_dialog(service: SheetsService, context: DayToDayContext, entry) -> None:
    room_display = _room_display_factory(context.room_name_by_label)
    st.caption(f"The month's running total for {room_display(entry.room)}. Type what it should be.")
    with st.form(key=f"edit_drinks_form_{entry.row_number}"):
        beer = st.number_input(
            "Beers or sodas",
            min_value=0,
            step=1,
            value=int(entry.beer_soda),
            key=f"edit_drinks_beer_{entry.row_number}",
        )
        wine = st.number_input(
            "Bottles of wine",
            min_value=0,
            step=1,
            value=int(entry.wine),
            key=f"edit_drinks_wine_{entry.row_number}",
        )
        save = st.form_submit_button("Save", type="primary", use_container_width=True)

    if not save:
        return
    try:
        service.update_drinks(context.selected_sheet_name, entry.row_number, int(beer), int(wine))
    except ValueError as exc:
        show_user_error(st, exc, f"Could not save the drinks for {room_display(entry.room)}")
        return

    data.clear_money()
    st.rerun()


def _is_payout(transaction_type: str) -> bool:
    text = str(transaction_type).lower()
    return "payout" in text or "udbetal" in text


def _ledger_row(
    *,
    title: str,
    note: str,
    key: str,
    help_text: str,
    on_edit,
    args,
    subtitle: str = "",
    mine: bool = False,
    icon: str = ":material/edit:",
) -> None:
    """One money row: what it was, whose it is, and the pencil that fixes it.

    A horizontal container, not columns: columns stack on a phone and would
    drop the pencil onto its own line under every row.
    """
    with st.container(horizontal=True, vertical_alignment="center", key=f"kpalrow_{key}"):
        classes = "kp-line" + (" kp-mine" if mine else "")
        sub = f'<span class="kp-sub">{_esc(subtitle)}</span>' if subtitle else ""
        # A shopping list typed into one cell can run for lines; the dialog has
        # the whole of it, so the row stops at two.
        st.markdown(
            f'<div class="{classes}"><span><span class="kp-clamp">{_esc(title)}</span>{sub}</span>'
            f'<span class="kp-note">{_esc(note)}</span></div>',
            unsafe_allow_html=True,
        )
        st.button(
            "",
            icon=icon,
            key=f"edit_{key}",
            help=help_text,
            type="tertiary",
            on_click=on_edit,
            args=args,
        )


def _my_row(text: str, note: str, *, key: str, help_text: str, on_edit, args) -> None:
    _ledger_row(title=text, note=note, key=f"my_{key}", help_text=help_text, on_edit=on_edit, args=args)


def _ledger_header(kicker: str, headline: str, caption: str = "") -> None:
    """Every ledger opens with its one number, then the fine print."""
    st.markdown(
        f'<div class="kp-kicker">{_esc(kicker)}</div>'
        f'<div class="kp-money kp-small">{_esc(headline)}</div>',
        unsafe_allow_html=True,
    )
    if caption:
        st.caption(caption)


def _arm_delete(state_key: str, row_number: int) -> None:
    st.session_state[state_key] = row_number


def _disarm_delete(state_key: str) -> None:
    st.session_state.pop(state_key, None)


def _delete_control(kind: str, context: DayToDayContext, row_number: int, noun: str) -> bool:
    """A two-step delete, because these rows are somebody's money.

    The arming and cancelling happen in on_click callbacks: st.rerun() inside a
    dialog closes it, and a callback has already run by the time the dialog
    redraws, so the confirmation swaps in without one.
    """
    state_key = _delete_confirmation_key(kind, context.selected_sheet_name)
    if st.session_state.get(state_key) != row_number:
        st.button(
            f"Delete this {noun}",
            key=f"arm_delete_{kind}_{row_number}",
            use_container_width=True,
            on_click=_arm_delete,
            args=(state_key, row_number),
        )
        return False

    st.warning(f"Delete this {noun} for good?")
    with st.container(horizontal=True):
        confirmed = st.button(
            "Yes, delete",
            key=f"confirm_delete_{kind}_{row_number}",
            type="primary",
            use_container_width=True,
        )
        st.button(
            "Keep it",
            key=f"cancel_delete_{kind}_{row_number}",
            use_container_width=True,
            on_click=_disarm_delete,
            args=(state_key,),
        )
    if confirmed:
        _disarm_delete(state_key)
    return confirmed


def _render_my_rows(service: SheetsService, context: DayToDayContext, room: str) -> None:
    """Your own purchases, payments and shared costs — everyone else's live under House."""
    purchases = [entry for entry in context.month_entries.purchases if entry.room == room]
    payments = [entry for entry in context.month_entries.transactions if entry.room == room]
    shared = [entry for entry in data.andet_rows(service, context.selected_sheet_name) if entry.payer == room]
    if not purchases and not payments and not shared:
        return

    st.markdown("###### Yours this month")
    for entry in purchases:
        _my_row(
            f"{entry.item or 'Purchase'} · {entry.date}",
            f"+{_format_amount_dkk(entry.amount)}",
            key=f"purchase_{entry.row_number}",
            help_text="Edit or delete this purchase",
            on_edit=_edit_purchase_dialog,
            args=(service, context, entry),
        )
    for entry in payments:
        _my_row(
            f"{entry.transaction_type} · {entry.date}",
            _format_amount_dkk(entry.amount),
            key=f"payment_{entry.row_number}",
            help_text="Edit or delete this payment",
            on_edit=_edit_payment_dialog,
            args=(service, context, entry),
        )
    for entry in shared:
        _my_row(
            f"{entry.description or 'Shared cost'} · {entry.head_count} "
            f"{'person' if entry.head_count == 1 else 'people'}",
            f"+{_format_amount_dkk(entry.amount)}",
            key=f"andet_{entry.row_number}",
            help_text="Edit or delete this shared cost",
            on_edit=_andet_dialog,
            args=(service, context, room, entry),
        )


def render_me_view(service: SheetsService):
    sheet_name = current_month_sheet(service)
    if sheet_name is None:
        st.warning("No month sheets are available yet.")
        return

    context = build_month_context(service, sheet_name, include_month_entries=True)
    if context is None or context.month_entries is None:
        return

    room = current_room(context.room_entries)
    statement = data.account_statement(service, sheet_name, room) if room else None
    if statement is None:
        st.info("Pick your room at the top to see what you owe.")
    else:
        _render_statement(
            statement,
            day_rows=data.day_rows(service, sheet_name),
            room=room,
            drinks=context.month_entries.drinks,
            purchases=context.month_entries.purchases,
        )

    if room:
        with st.container(horizontal=True, key="kpaladd"):
            if st.button("Drinks", icon=":material/local_bar:", use_container_width=True):
                _drinks_dialog(service, context, room)
            if st.button("Purchase", icon=":material/receipt_long:", use_container_width=True):
                _purchase_dialog(service, context, room)
            if st.button("Pay in", icon=":material/savings:", use_container_width=True):
                _payment_dialog(service, context, room)
            if st.button("Shared cost", icon=":material/group:", use_container_width=True):
                _andet_dialog(service, context, room)

        _render_my_rows(service, context, room)

    with st.expander("Choose month"):
        render_month_picker(service)


def people_labels(room_entries, *, signup_only: bool = False) -> list[str]:
    """Accounts that are a person right now.

    Empty FL slots are placeholders, not housemates, so they are never offered.
    """
    return [
        entry.label
        for entry in room_entries
        if is_occupied_account(entry.label, entry.name)
        and (entry.signup_column is not None or not signup_only)
    ]


def resident_labels(room_entries, *, signup_only: bool = False) -> list[str]:
    """"Everyone in the house": the numbered rooms 346-360 that someone lives in."""
    return [
        entry.label
        for entry in room_entries
        if is_room_label(entry.label)
        and str(entry.name or "").strip()
        and (entry.signup_column is not None or not signup_only)
    ]


def _who_is_this_for(context: DayToDayContext, key: str, room: str) -> str:
    """Acts as you unless you say otherwise — people do cover for each other."""
    room_display = _room_display_factory(context.room_name_by_label)
    labels = people_labels(context.room_entries)
    if room and not st.toggle("For someone else", key=f"{key}_for_other"):
        st.caption(f"For you — {room_display(room)}")
        return room
    return st.selectbox(
        "Who",
        labels,
        format_func=room_display,
        index=default_index(labels, room),
        key=f"{key}_who",
    )


def add_andet_form(service: SheetsService, context: DayToDayContext, room: str, entry=None) -> None:
    """A cost with no date: what it was, what it cost, and who was in on it.

    The sheet does the splitting — everyone marked here is charged one share and
    whoever paid is credited the whole amount.
    """
    room_display = _room_display_factory(context.room_name_by_label)
    labels = people_labels(context.room_entries, signup_only=True)
    everyone_labels = resident_labels(context.room_entries, signup_only=True)
    suffix = f"_{entry.row_number}" if entry is not None else ""

    payer = _who_is_this_for(context, f"andet{suffix}", entry.payer if entry is not None else room)
    everyone = st.checkbox(
        "Everyone in the house",
        value=bool(entry is not None and set(everyone_labels) <= set(entry.participants)),
        key=f"andet_everyone{suffix}",
        help="For birthdays: every room pays a share, whether they were there or not.",
    )
    default_people = list(entry.participants) if entry is not None else ([room] if room in labels else [])
    people = everyone_labels if everyone else st.multiselect(
        "Who was in on it",
        labels,
        default=[label for label in default_people if label in labels],
        format_func=room_display,
        key=f"andet_people{suffix}",
    )

    with st.form(key=f"andet_form{suffix}"):
        description = st.text_input(
            "What was it?",
            value=entry.description if entry is not None else "",
            placeholder="e.g. birthday cake, Sunday brunch",
        )
        amount = st.number_input(
            "Total cost (DKK)",
            min_value=0.0,
            step=0.01,
            value=float(entry.amount) if entry is not None else 0.0,
        )
        if people:
            st.caption(
                f"{len(people)} {'person' if len(people) == 1 else 'people'}"
                f" · {_format_amount_dkk(amount / len(people))} each"
            )
        save = st.form_submit_button("Save shared cost", type="primary", use_container_width=True)
        remove = st.form_submit_button("Delete this cost", use_container_width=True) if entry is not None else False

    if save:
        if amount <= 0:
            st.error("Add the total cost before saving.")
            return
        try:
            service.save_andet(
                context.selected_sheet_name,
                payer=payer,
                description=description,
                amount=amount,
                participants=list(people),
                room_entries=context.room_entries,
                row_number=entry.row_number if entry is not None else None,
            )
        except ValueError as exc:
            show_user_error(st, exc, "Could not save the shared cost")
            return
    elif remove:
        try:
            service.clear_andet(context.selected_sheet_name, entry.row_number, context.room_entries)
        except ValueError as exc:
            show_user_error(st, exc, "Could not delete the shared cost")
            return
    else:
        return

    data.clear_money()
    st.rerun()


def render_andet_list(service: SheetsService, context: DayToDayContext, room: str) -> None:
    rows = data.andet_rows(service, context.selected_sheet_name)
    if not rows:
        st.caption("No shared costs this month.")
        return

    room_display = _room_display_factory(context.room_name_by_label)
    st.caption(f"{len(rows)} of {ANDET_ROW_CAPACITY} shared cost rows used this month.")
    for entry in rows:
        mine = room and room in entry.participants
        note = f"{_format_amount_dkk(entry.share)} each" if entry.head_count else "—"
        st.markdown(
            f'<div class="kp-line{" kp-mine" if mine else ""}">'
            f"<span>{entry.description or 'Shared cost'} · {room_display(entry.payer)} paid "
            f"{_format_amount_dkk(entry.amount)} · {entry.head_count} "
            f"{'person' if entry.head_count == 1 else 'people'}</span>"
            f'<span class="kp-note">{note}</span></div>',
            unsafe_allow_html=True,
        )


def add_drinks_form(service: SheetsService, context: DayToDayContext, room: str) -> None:
    room_display = _room_display_factory(context.room_name_by_label)
    target_room = _who_is_this_for(context, "drinks", room)
    with st.form(key="drinks_form"):
        beer_quantity = st.number_input("Beers or sodas", min_value=0, step=1, key="drinks_beer")
        wine_quantity = st.number_input("Bottles of wine", min_value=0, step=1, key="drinks_wine")
        st.caption("These are added to the running total for the month.")
        submitted = st.form_submit_button("Add drinks", type="primary", use_container_width=True)

    if not submitted:
        return
    if beer_quantity == 0 and wine_quantity == 0:
        st.error("Add at least one drink before saving.")
        return
    try:
        drink_entry = next((entry for entry in context.month_entries.drinks if entry.room == target_room), None)
        if drink_entry is None:
            service.add_drinks(context.selected_sheet_name, target_room, beer_quantity, wine_quantity)
        else:
            service.update_drinks(
                context.selected_sheet_name,
                drink_entry.row_number,
                drink_entry.beer_soda + beer_quantity,
                drink_entry.wine + wine_quantity,
            )
        data.clear_money()
        st.rerun()
    except ValueError as exc:
        show_user_error(st, exc, f"Could not add drinks for {room_display(target_room)}")


def _drink_summary(beer: int, wine: int) -> str:
    parts = []
    if beer:
        parts.append(f"{beer} beer/soda")
    if wine:
        parts.append(f"{wine} wine")
    return " · ".join(parts) or "None"


def render_drink_totals(service: SheetsService, context: DayToDayContext, room: str = "") -> None:
    """Everyone's drink tally for the month, and the one way to correct it.

    Adding drinks is a Me action; this is the register, so the tally is the
    whole row and the pencil sets it rather than adding to it.
    """
    entries = [entry for entry in context.month_entries.drinks if entry.beer_soda or entry.wine]
    if not entries:
        _ledger_header("Drinks this month", "None yet")
        st.caption("Drinks are added from Me.")
        return

    beers = sum(int(entry.beer_soda) for entry in entries)
    wines = sum(int(entry.wine) for entry in entries)
    _ledger_header(
        "Drinks this month",
        _drink_summary(beers, wines),
        f"{len(entries)} {'person has' if len(entries) == 1 else 'people have'} drinks on the sheet.",
    )

    for entry in sorted(entries, key=lambda item: int(item.beer_soda) + int(item.wine), reverse=True):
        _ledger_row(
            title=entry.name or entry.room,
            subtitle=entry.room if entry.name else "",
            note=_drink_summary(int(entry.beer_soda), int(entry.wine)),
            key=f"drinks_{entry.row_number}",
            help_text="Correct this tally",
            on_edit=_edit_drinks_dialog,
            args=(service, context, entry),
            mine=entry.room == room,
        )


def _table_usage_caption(used: int, capacity: int, noun: str) -> str:
    # The sheet's own formulas only sum the rows inside the table, so running
    # out is a real limit rather than a formality — say so before it bites.
    remaining = capacity - used
    if remaining <= 0:
        return f"The {noun} table is full ({used} of {capacity} rows). Edit or delete one before adding another."
    if remaining <= 5:
        return f"{used} of {capacity} {noun} rows used this month — {remaining} left."
    return f"{used} of {capacity} {noun} rows used this month."


def add_purchase_form(service: SheetsService, context: DayToDayContext, room: str):
    purchase_room = _who_is_this_for(context, "purchase", room)
    with st.form(key="purchase_form"):
        purchase_item = st.text_input("What was bought?", key="purchase_item")
        purchase_date = st.date_input("Date", key="purchase_date")
        purchase_cost = st.number_input(
            "Total price (negative for refunds like pant)", step=0.01, key="purchase_cost"
        )
        submitted = st.form_submit_button("Save purchase", type="primary", use_container_width=True)

    if submitted:
        if not purchase_item.strip():
            st.error("Add what was bought before saving.")
            return
        if purchase_cost == 0:
            st.error("Add a non-zero price before saving (negative for refunds).")
            return
        try:
            target_row = _next_available_row(
                context.month_entries.purchases,
                _range_start_row(PURCHASE_LOOKUP_RANGE) + 1,
                _range_end_row(PURCHASE_LOOKUP_RANGE),
            )
            if target_row is None:
                service.add_purchase(
                    context.selected_sheet_name,
                    purchase_room,
                    purchase_date,
                    purchase_item,
                    purchase_cost,
                )
            else:
                service.update_purchase(
                    context.selected_sheet_name,
                    target_row,
                    purchase_room,
                    purchase_date,
                    purchase_item,
                    purchase_cost,
                )
            data.clear_money()
            st.rerun()
        except ValueError as exc:
            show_user_error(st, exc, "Could not register purchase")


def render_purchase_ledger(service: SheetsService, context: DayToDayContext, room: str = "") -> None:
    """Everyone's purchases, newest first, each one a tap away from a fix."""
    entries = context.month_entries.purchases
    total = sum(float(entry.amount) for entry in entries)
    _ledger_header(
        "Purchases this month",
        _format_amount_dkk(total) if entries else "None yet",
        f"{len(entries)} {'purchase' if len(entries) == 1 else 'purchases'}, "
        "each one credited to whoever paid.",
    )
    if not entries:
        st.caption("Shared purchases are added from Me.")
        return

    for entry in _newest_first(entries, context.selected_sheet_name):
        _ledger_row(
            title=entry.item or "Purchase",
            subtitle=f"{_person_caption(entry.room, context.room_name_by_label)} · "
            f"{_short_date(entry.date, context.selected_sheet_name)}",
            note=_signed_amount(float(entry.amount)),
            key=f"purchase_{entry.row_number}",
            help_text="Edit or delete this purchase",
            on_edit=_edit_purchase_dialog,
            args=(service, context, entry, True),
            mine=entry.room == room,
        )

    st.caption(_table_usage_caption(len(entries), PURCHASE_ROW_CAPACITY, "purchase"))


def add_payment_form(service: SheetsService, context: DayToDayContext, room: str):
    transaction_room = _who_is_this_for(context, "payment", room)
    with st.form(key="transaction_form"):
        transaction_type = st.selectbox(
            "Payment type",
            ["Payment to kitchen fund", "Payout from kitchen fund"],
            key="tx_type",
        )
        transaction_amount = st.number_input("Amount (DKK)", min_value=0.0, step=0.01, key="tx_amount")
        transaction_date = st.date_input("Date", value=datetime.now(), key="tx_date")
        submitted = st.form_submit_button("Save payment", type="primary", use_container_width=True)

    if submitted:
        if transaction_amount <= 0:
            st.error("Add an amount greater than 0 before saving.")
            return
        try:
            target_row = _next_available_row(context.month_entries.transactions, 44)
            if target_row is None:
                service.add_transaction(
                    context.selected_sheet_name,
                    transaction_room,
                    transaction_type,
                    transaction_amount,
                    transaction_date,
                )
            else:
                service.update_transaction(
                    context.selected_sheet_name,
                    target_row,
                    transaction_room,
                    transaction_type,
                    transaction_amount,
                    transaction_date,
                )
            data.clear_money()
            st.rerun()
        except ValueError as exc:
            show_user_error(st, exc, "Could not register kitchen fund payment")


def render_payment_ledger(service: SheetsService, context: DayToDayContext, room: str = "") -> None:
    """Money in and out of the kitchen fund, newest first."""
    entries = context.month_entries.transactions
    paid_in = sum(float(entry.amount) for entry in entries if float(entry.amount) > 0)
    paid_out = sum(-float(entry.amount) for entry in entries if float(entry.amount) < 0)
    _ledger_header(
        "Kitchen fund this month",
        _signed_amount(paid_in - paid_out) if entries else "None yet",
        f"{_format_amount_dkk(paid_in)} in · {_format_amount_dkk(paid_out)} out",
    )
    if not entries:
        st.caption("Payments are added from Me.")
        return

    for entry in _newest_first(entries, context.selected_sheet_name):
        direction = "Paid out" if _is_payout(entry.transaction_type) else "Paid in"
        _ledger_row(
            title=_person_caption(entry.room, context.room_name_by_label),
            subtitle=f"{direction} · {_short_date(entry.date, context.selected_sheet_name)}",
            note=_signed_amount(float(entry.amount)),
            key=f"payment_{entry.row_number}",
            help_text="Edit or delete this payment",
            on_edit=_edit_payment_dialog,
            args=(service, context, entry, True),
            mine=entry.room == room,
        )

    st.caption(_table_usage_caption(len(entries), TRANSACTION_ROW_CAPACITY, "payment"))
