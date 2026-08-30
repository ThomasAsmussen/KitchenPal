"""The House tab: everything that belongs to everyone.

One section at a time, chosen from an index. Streamlit runs the body of a
collapsed expander anyway, so six expanders meant six sections' worth of reads
before you had opened anything — thirty-four round trips to show one list.
"""
from __future__ import annotations

import streamlit as st

from ..sheets_service import SheetsService
from .day_to_day import (
    build_month_context,
    my_cooking_nights,
    render_andet_list,
    render_drink_totals,
    render_payment_ledger,
    render_purchase_ledger,
    _format_amount_dkk,
    _host_caption,
    _short_day,
)
from . import data
from .feedback import render_feedback_view
from .identity import current_room
from .month import current_month_sheet, render_month_picker
from .admin import render_admin_view
from .month_setup import render_availability_overview

NON_PERSON_LABELS = {"Spotify"}
SECTION_KEY = "house_section"

SECTIONS = [
    ("balances", "Balances", ":material/account_balance_wallet:", "What everyone owes the kitchen fund"),
    ("schedule", "Cooking schedule", ":material/restaurant:", "Who cooks this month"),
    ("costs", "Shared costs", ":material/group:", "Dinners and buys with no date"),
    ("when", "Who can cook when", ":material/event_available:", "Everyone's answers for next month"),
    ("ledgers", "Drinks, purchases and payments", ":material/receipt_long:", "The full lists, and fixing a row"),
    ("ideas", "Bugs and ideas", ":material/lightbulb:", "What people have reported"),
    ("admin", "Admin", ":material/settings:", "Months, people and the host schedule"),
]


def _balance_row(name: str, amount: float, *, mine: bool) -> None:
    tone = "kp-owed" if amount < 0 else ("kp-good" if amount > 0 else "kp-credit")
    classes = "kp-line" + (" kp-mine" if mine else "")
    st.markdown(
        f'<div class="{classes}"><span>{name}</span>'
        f'<span class="kp-note {tone}">{_format_amount_dkk(amount)}</span></div>',
        unsafe_allow_html=True,
    )


def render_balances(service: SheetsService, worksheet_name: str, room: str) -> None:
    """Everyone's balance, the people furthest behind first."""
    accounts = [
        entry
        for entry in data.personal_accounts(service, worksheet_name)
        if entry.name and entry.label not in NON_PERSON_LABELS
    ]
    if not accounts:
        st.caption("No accounts on this sheet yet.")
        return

    owing = [entry for entry in accounts if entry.balance < 0]
    total_owed = sum(entry.balance for entry in owing)
    if owing:
        st.caption(
            f"{len(owing)} of {len(accounts)} owe the kitchen fund, "
            f"{_format_amount_dkk(abs(total_owed))} in total."
        )
    else:
        st.caption("Nobody owes the kitchen fund right now.")

    for entry in sorted(accounts, key=lambda item: item.balance):
        _balance_row(f"{entry.name} · {entry.label}", entry.balance, mine=entry.label == room)


def render_cooking_schedule(service: SheetsService, context, worksheet_name: str, room: str) -> None:
    rows = data.day_rows(service, worksheet_name)
    cooked = [row for row in rows if row.chef]
    if not cooked:
        st.caption("Nobody is down to cook this month yet.")
        return

    mine = len(my_cooking_nights(rows, room))
    st.caption(
        f"{len(cooked)} dinner{'s' if len(cooked) != 1 else ''} this month"
        + (f" · {mine} of them yours" if mine else "")
    )
    for row in cooked:
        note = f"{row.signed_up} eating" if row.signed_up else "—"
        st.markdown(
            f'<div class="kp-line{" kp-mine" if row.chef == room else ""}">'
            f'<span>{_short_day(worksheet_name, row.day)} · {_host_caption(row.chef, context.room_name_by_label)}</span>'
            f'<span class="kp-note">{note}</span></div>',
            unsafe_allow_html=True,
        )


def _render_index(worksheet_name: str) -> None:
    st.caption(worksheet_name)
    for slug, title, icon, subtitle in SECTIONS:
        if st.button(title, icon=icon, key=f"house_open_{slug}", help=subtitle, width="stretch"):
            st.session_state[SECTION_KEY] = slug
            st.rerun()


def _render_section(service: SheetsService, slug: str, worksheet_name: str) -> None:
    title = next((item[1] for item in SECTIONS if item[0] == slug), "House")
    if st.button("All sections", icon=":material/arrow_back:", key="house_back", type="tertiary"):
        st.session_state.pop(SECTION_KEY, None)
        st.rerun()
    st.subheader(title)

    # Each section loads only what it needs; nothing else is read.
    if slug == "ideas":
        render_feedback_view(service)
        return
    if slug == "admin":
        render_admin_view(service)
        return
    if slug == "when":
        render_availability_overview(service)
        return

    context = build_month_context(service, worksheet_name, include_month_entries=slug == "ledgers")
    if context is None:
        return
    room = current_room(context.room_entries)

    if slug == "balances":
        render_balances(service, worksheet_name, room)
    elif slug == "schedule":
        render_cooking_schedule(service, context, worksheet_name, room)
    elif slug == "costs":
        st.caption("Dinners and buys with no date — everyone marked pays a share.")
        render_andet_list(service, context, room)
    elif slug == "ledgers":
        drinks_tab, purchases_tab, payments_tab = st.tabs(["Drinks", "Purchases", "Payments"])
        with drinks_tab:
            render_drink_totals(service, context, room)
        with purchases_tab:
            render_purchase_ledger(service, context, room)
        with payments_tab:
            render_payment_ledger(service, context, room)


def render_house_view(service: SheetsService) -> None:
    worksheet_name = current_month_sheet(service)
    if worksheet_name is None:
        st.warning("No month sheets are available yet.")
        return

    slug = st.session_state.get(SECTION_KEY)
    if slug is None:
        _render_index(worksheet_name)
    else:
        _render_section(service, slug, worksheet_name)


    # Admin and the idea list are not about a month you can pick here: Admin
    # keeps its own, and a second picker beside it just poses a question with no
    # answer.
    if slug not in ("admin", "ideas"):
        with st.expander("Choose month"):
            render_month_picker(service)
