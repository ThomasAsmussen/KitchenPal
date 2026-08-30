"""When the month turns.

Creating a month sheet is a chore with no decision in it, and carrying the
balances is only correct once the previous month has closed — the copy reads
the previous sheet's live closing column, so running it on the 25th writes
numbers that are still moving. Neither is therefore a step an admin performs:
the sheet appears when something first needs it, and the month turns by itself
the first time anyone opens the app on or after the 1st.

Streamlit has no scheduler, so "on the 1st" means exactly that. Until the turn
happens every screen says so, instead of quietly showing last month's numbers.

The race guard is a module-level lock, which is process-wide because Streamlit
serves every session from one process. Behind several workers two of them could
still both try; create_month_sheet re-reads the sheet list and refuses to make a
second sheet, and the copy is idempotent, so the worst case is wasted requests.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import streamlit as st

from ..constants import ENGLISH_MONTHS, MONTH_TO_NUMBER
from ..runtime_state import bump_cache_version
from ..sheets.log import LogEntry
from ..sheets.utils import is_person_account_label, normalized_person_name
from ..sheets_service import SheetsService
from . import data
from .errors import user_error_message
from .month_setup import _month_sheet_for, _month_sheet_names

TURN_RETRY_SECONDS = 300

_turn_lock = threading.Lock()
_turn_attempts: dict[str, float] = {}
_turn_errors: dict[str, str] = {}


def _key(month_name: str, year: int) -> str:
    return f"{month_name} {year}"


def this_month(today: datetime | None = None) -> tuple[str, int]:
    now = today or datetime.now()
    return ENGLISH_MONTHS[now.month - 1], now.year


def next_month(today: datetime | None = None) -> tuple[str, int]:
    now = today or datetime.now()
    following = now.replace(day=1) + timedelta(days=32)
    return ENGLISH_MONTHS[following.month - 1], following.year


def days_until_the_first(month_name: str, year: int, today: datetime | None = None) -> int:
    now = (today or datetime.now()).date()
    return (date(year, MONTH_TO_NUMBER[month_name], 1) - now).days


@dataclass(frozen=True)
class MonthStatus:
    month_name: str
    year: int
    sheet_name: str | None
    turned_at: str = ""
    nothing_to_carry: bool = False
    error: str = ""
    log_unreadable: bool = False

    @property
    def turned_early(self) -> bool:
        """Opened before the month began, so its figures are provisional.

        The copy reads the previous month's LIVE closing column. Opening on the
        30th freezes carried-in balances that August had not finished moving,
        and every dinner and purchase in the last two days would be lost from
        the carry. So an early turn does not count as open: the automatic turn
        runs again on the 1st and refreshes it.
        """
        stamp = _turn_date(self.turned_at)
        return stamp is not None and stamp < date(self.year, MONTH_TO_NUMBER[self.month_name], 1)

    @property
    def is_open(self) -> bool:
        """Open means the balances have been carried in, after the month began.

        The evidence is the Log's rolled_over row rather than anything on the
        sheet, because a name is not proof: a move-in recorded early puts one
        name on next month's sheet weeks before the copy runs. The bias is
        deliberate — thinking a month is closed when it is open costs one extra
        copy, which is idempotent; the other way round leaves every balance
        wrong.
        """
        if self.sheet_name is None:
            return False
        if self.nothing_to_carry:
            return True
        return bool(self.turned_at) and not self.turned_early


def _turn_date(stamp: str):
    try:
        return datetime.strptime(str(stamp)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


@dataclass(frozen=True)
class OpenResult:
    sheet_name: str
    created: bool
    report: object


@dataclass(frozen=True)
class Stray:
    """Money that ended a month with someone who is on no row in the next one."""

    name: str
    balance: float


def resolve_sheet_name(service: SheetsService, month_name: str, year: int) -> str | None:
    sheets = _month_sheet_names(data.sheet_names(service))
    return _month_sheet_for(MONTH_TO_NUMBER[month_name], year, sheets)


def turned_at(service: SheetsService, sheet_name: str) -> str:
    """When the month was opened, according to the Log. Newest row wins."""
    return _has_log_event(service, sheet_name, ("rolled_over",))


def previous_sheet_name(service: SheetsService, month_name: str, year: int) -> str | None:
    month = MONTH_TO_NUMBER[month_name]
    previous_index = (month - 2) % 12
    previous_year = year - 1 if month == 1 else year
    return resolve_sheet_name(service, ENGLISH_MONTHS[previous_index], previous_year)


def month_status(service: SheetsService, month_name: str, year: int) -> MonthStatus:
    sheet_name = resolve_sheet_name(service, month_name, year)
    return MonthStatus(
        month_name=month_name,
        year=year,
        sheet_name=sheet_name,
        log_unreadable=bool(sheet_name) and read_log(service) is None,
        turned_at=turned_at(service, sheet_name) if sheet_name else "",
        # The house's first month has nothing behind it to carry.
        nothing_to_carry=bool(sheet_name) and previous_sheet_name(service, month_name, year) is None,
        error=_turn_errors.get(_key(month_name, year), ""),
    )


def carry_into_month(
    service: SheetsService, month_name: str, year: int, *, event: str, by: str = ""
) -> OpenResult:
    """Make the sheet exist, then carry the balances into it.

    The same two calls do two different jobs, and only the Log row tells them
    apart. PREPARING happens whenever an admin first touches next month: it
    fills the sheet with this month's people so there is a real roster to edit,
    and the balances it writes are provisional. OPENING is the turn itself on
    the 1st, when the previous month has stopped moving and the numbers are
    final. Running the copy twice is safe: pass 1 keeps every name already on
    the sheet, so an admin's edits survive the second run.
    """
    sheet_name = resolve_sheet_name(service, month_name, year)
    created = False
    if sheet_name is None:
        service.create_month_sheet(month_name, year)
        created = True
        sheet_name = f"{month_name} {year}"
        data.clear_months()

    report = service.copy_balances_from_previous_month(month_name, year)
    data.clear_months()
    bump_cache_version()
    _log_the_carry(service, sheet_name, report, event=event, by=by)
    return OpenResult(sheet_name=sheet_name, created=created, report=report)


def open_month(service: SheetsService, month_name: str, year: int, *, by: str = "") -> OpenResult:
    """The turn: the balances are final from here."""
    return carry_into_month(service, month_name, year, event="rolled_over", by=by)


def prepare_month(service: SheetsService, month_name: str, year: int, *, by: str = "") -> OpenResult:
    """Next month, started from this one, so there is a roster to edit."""
    return carry_into_month(service, month_name, year, event="prepared", by=by)


def same_month_sheet(logged: object, sheet_name: str) -> bool:
    """Case-insensitive, because the Log holds rows from before RAW writing.

    Those rows went in through USER_ENTERED on a Danish-locale spreadsheet,
    which read "September 2026" as a date and stored it back lowercased.
    """
    return str(logged or "").strip().casefold() == str(sheet_name or "").strip().casefold()


def read_log(service: SheetsService):
    """The Log, or None when it could not be read at all.

    None and [] are not the same answer and must never be confused: an empty Log
    means the month has not been opened, while an unreadable one means we do not
    know — and acting on "we do not know" is what makes the app carry the
    balances again on a sheet that was already carried.
    """
    try:
        return list(data.log_entries(service))
    except Exception:  # noqa: BLE001 - a read that failed is not an answer
        return None


def _has_log_event(service: SheetsService, sheet_name: str, events: tuple[str, ...]) -> str:
    entries = read_log(service)
    for entry in entries or []:
        if entry.event in events and same_month_sheet(entry.month_sheet, sheet_name):
            return str(entry.timestamp or "").strip() or "earlier"
    return ""


def is_prepared(service: SheetsService, sheet_name: str | None) -> bool:
    """Has a copy filled this sheet, or is it blank — or worse, half typed in?

    Names cannot answer this either, and for a sharper reason than is_open: a
    sheet with ONE name and fourteen empty rooms is the state an admin lands in
    by recording a move-in before anything filled the sheet, and it is exactly
    the state that needs repairing. Only a copy makes a roster, so only a copy's
    own Log row counts as proof that one has run.
    """
    if not sheet_name:
        return False
    return bool(_has_log_event(service, sheet_name, ("prepared", "rolled_over")))


def _log_the_carry(service: SheetsService, sheet_name: str, report, *, event: str, by: str) -> None:
    if event == "prepared":
        summary = f"{sheet_name} prepared from the previous month: names and provisional balances."
    else:
        summary = f"{sheet_name} opened and the balances carried over."
        if report is not None and getattr(report, "unplaced", None):
            summary += f" {len(report.unplaced)} balance(s) had nowhere to go."
    try:
        service.append_log_entries(
            [
                LogEntry(
                    event=event,
                    summary=summary,
                    action_id=f"roll-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    month_sheet=sheet_name,
                    by=by or "automatic",
                )
            ]
        )
    except Exception:  # noqa: BLE001 - the Log never breaks an action
        pass
    data.clear_people()


def reverted_move_outs(service: SheetsService, sheet_name: str, accounts) -> list[str]:
    """People moved out of a month who are on it again after the turn.

    copy-balances refills a blank room with its previous occupant unless that
    person is named somewhere else, so moving out someone who owes nothing —
    the one case that leaves no FL row behind — is undone by the next copy. No
    money is ever wrong, because a settled tab is 0.00 by definition, but the
    roster is, and a silently reverted admin action is worse than a wrong one.
    """
    here = {normalized_person_name(entry.name): entry.name for entry in accounts if entry.name}
    try:
        entries = data.log_entries(service)
    except Exception:  # noqa: BLE001
        return []

    latest: dict[str, str] = {}
    for entry in entries:  # newest first
        if not same_month_sheet(entry.month_sheet, sheet_name):
            continue
        if entry.event not in ("moved_out", "moved_in", "moved", "parked_fl"):
            continue
        key = normalized_person_name(entry.person)
        if key and key not in latest:
            latest[key] = entry.event

    return [here[key] for key, event in latest.items() if event == "moved_out" and key in here]


def turn_if_due(service: SheetsService, today: datetime | None = None) -> OpenResult | None:
    """The automatic turn: called on every page load, free once it has run."""
    month_name, year = this_month(today)
    key = _key(month_name, year)

    status = month_status(service, month_name, year)
    # A month is only "not open" when the Log SAYS so. If the Log could not be
    # read — a quota error, a renamed worksheet — we do not know, and carrying
    # the balances on a guess is how one month gets opened five times.
    if status.log_unreadable or status.is_open:
        _turn_errors.pop(key, None)
        return None

    with _turn_lock:
        if key in _turn_attempts and (time.monotonic() - _turn_attempts[key]) < TURN_RETRY_SECONDS:
            return None
        _turn_attempts[key] = time.monotonic()

        # Look again without the caches: another session may have just done it.
        data.clear_months()
        fresh = month_status(service, month_name, year)
        if fresh.log_unreadable or fresh.is_open:
            _turn_errors.pop(key, None)
            return None

        try:
            result = open_month(service, month_name, year)
        except Exception as exc:  # noqa: BLE001 - shown in the banner, retried later
            _turn_errors[key] = user_error_message(exc, "Could not open the month")
            return None

    # The attempt marker is NOT cleared on success. One automatic turn per month
    # per process is the most this should ever do; a genuine second run is a
    # deliberate act through "Open the month by hand".
    _turn_errors.pop(key, None)
    return result


def outstanding_strays(service: SheetsService, sheet_name: str, previous_sheet_name: str | None) -> list[Stray]:
    """Derived from the sheet, not remembered from the copy's report.

    Both of the copy's money-losing outcomes — a balance with no free FL slot,
    and a room whose occupant was renamed — look the same afterwards: somebody
    ended last month with money and is on no row this month. Recomputing it
    means the to-do list survives a restart and cannot go stale.
    """
    if not previous_sheet_name:
        return []
    here = {
        normalized_person_name(entry.name)
        for entry in data.personal_accounts(service, sheet_name)
        if entry.name
    }
    strays = []
    for entry in data.personal_accounts(service, previous_sheet_name):
        if not entry.name or not is_person_account_label(entry.label):
            continue
        if abs(float(entry.balance)) < 0.005:
            continue
        if normalized_person_name(entry.name) in here:
            continue
        strays.append(Stray(name=entry.name, balance=float(entry.balance)))
    return strays


def duplicate_people(service: SheetsService, sheet_name: str) -> list[str]:
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for entry in data.personal_accounts(service, sheet_name):
        if not entry.name or not is_person_account_label(entry.label):
            continue
        key = normalized_person_name(entry.name)
        first_seen = seen.get(key)
        if first_seen is not None and first_seen not in duplicates:
            # Report the name as the first row spells it, not the second.
            duplicates.append(first_seen)
        seen.setdefault(key, str(entry.name).strip())
    return duplicates


def render_status_banner(service: SheetsService, room: str = "", slug: str = "") -> None:
    """One line on every screen: the month is open, or it is not and why."""
    month_name, year = this_month()
    status = month_status(service, month_name, year)

    if not status.is_open:
        st.error(f"{month_name} {year} has not opened yet — balances are still last month's.")
        if status.error:
            st.caption(status.error)
        if st.button(f"Open {month_name} now", key="banner_open_month", type="primary"):
            try:
                open_month(service, month_name, year, by=room)
            except Exception as exc:  # noqa: BLE001
                st.error(user_error_message(exc, "Could not open the month"))
                return
            _turn_errors.pop(_key(month_name, year), None)
            st.rerun()
        return

    _render_planning_nudge(service, room, slug)
    _render_next_month_nudge(service)


def unanswered_planning_month(service: SheetsService, room: str) -> tuple[str, int] | None:
    """The month this person can still answer for, when they have not.

    It opens when next month's sheet is PREPARED — a copy has filled it, so
    there is a real roster and a real room to answer about, which is not true of
    a sheet holding one typed name. It closes the moment they answer, and by
    itself when the month starts, because next_month() has moved on by then and
    the month after it will not be prepared yet.

    Nobody is asked about a month they are not on the rota for. Someone whose
    row next month has no room is not expected to cook — _stored_availability
    keeps them off the schedule until they say otherwise — so nudging them would
    contradict the very default that protects them.

    Every read here is decoration. A nudge that takes the page down with it when
    the Planning sheet is briefly unreadable is worse than no nudge at all.
    """
    if not room:
        return None

    month_name, year = next_month()
    sheet_name = resolve_sheet_name(service, month_name, year)
    if not is_prepared(service, sheet_name):
        return None

    from .day_to_day import identity_room_entries
    from .plan import has_answered

    try:
        my_name = next(
            (entry.name for entry in identity_room_entries(service) if entry.label == room), ""
        )
        if not my_name:
            return None

        # Resolved through the NAME, for the reason _planning_room_entry gives:
        # rooms change hands at a rollover, so the room you claim this month is
        # not necessarily the one you are answering for.
        key = normalized_person_name(my_name)
        mine = [
            entry
            for entry in data.room_entries(service, sheet_name)
            if entry.name and normalized_person_name(entry.name) == key
        ]
        if len(mine) != 1 or not mine[0].label.isdigit():
            return None

        stored = {
            str(entry.room_number).strip(): entry
            for entry in data.planning_entries(service, month_name, year)
        }.get(mine[0].label)
    except Exception:  # noqa: BLE001 — see the docstring
        return None

    if has_answered(stored, (), year, MONTH_TO_NUMBER[month_name]):
        return None
    return month_name, year


def _render_planning_nudge(service: SheetsService, room: str, slug: str) -> None:
    # On Plan it is the same fact said twice, an inch from the answer itself.
    if slug == "plan":
        return
    upcoming = unanswered_planning_month(service, room)
    if upcoming is None:
        return
    # Accented rather than a second grey caption: this one is the reader's own
    # to-do, and two greys stacked read as one paragraph of house chatter. No
    # button — the Plan tab is in the bar directly above this line.
    st.markdown(
        f'<div class="kp-nudge">Say when you can cook in {upcoming[0]} — under Plan.</div>',
        unsafe_allow_html=True,
    )


def _render_next_month_nudge(service: SheetsService) -> None:
    # The nudge exists to send someone to Admin. On Admin it is the same fact
    # said twice, in different words, an inch apart.
    if st.session_state.get("house_section") == "admin":
        return
    upcoming_month, upcoming_year = next_month()
    days = days_until_the_first(upcoming_month, upcoming_year)
    if days > 7:
        return

    sheet_name = resolve_sheet_name(service, upcoming_month, upcoming_year)
    open_questions = 2
    if sheet_name:
        open_questions = len(unanswered_questions(service, sheet_name))
    if not open_questions:
        return

    when = "tomorrow" if days == 1 else ("today" if days <= 0 else f"in {days} days")
    st.caption(
        f"{upcoming_month} starts {when} · Admin has "
        f"{open_questions} question{'s' if open_questions != 1 else ''} left."
    )


def occupancy_is_confirmed(service: SheetsService, sheet_name: str) -> bool:
    return bool(_has_log_event(service, sheet_name, ("occupancy_confirmed",)))


def cooks_are_written(service: SheetsService, sheet_name: str) -> bool:
    try:
        return any(row.chef for row in data.day_rows(service, sheet_name))
    except Exception:  # noqa: BLE001
        return False


def unanswered_questions(service: SheetsService, sheet_name: str) -> list[str]:
    unanswered = []
    if not occupancy_is_confirmed(service, sheet_name):
        unanswered.append("moving")
    if not cooks_are_written(service, sheet_name):
        unanswered.append("cooking")
    return unanswered


def confirm_occupancy(service: SheetsService, sheet_name: str, *, by: str = "", summary: str = "") -> None:
    """The answer to "is anyone moving?", including when the answer is nobody."""
    service.append_log_entries(
        [
            LogEntry(
                event="occupancy_confirmed",
                summary=summary or f"Confirmed who lives in {sheet_name}.",
                action_id=f"occ-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                month_sheet=sheet_name,
                by=by,
            )
        ]
    )
    data.clear_people()
