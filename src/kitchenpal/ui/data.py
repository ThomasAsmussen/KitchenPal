"""Every read the app makes, cached once for the whole house.

Session state was the wrong place for these: twenty residents looking at the
same August sheet fetched it twenty times, and the Sheets API's read budget is
per service account — one budget shared by everyone. st.cache_data is
process-wide, so the first person to open a tab pays for the read and everyone
else that minute is served from memory.

Freshness is handled by clearing, not by short timeouts: a write clears the
caches it touched, so your own change is never stale to you. The TTLs are only
a backstop for edits people make in the spreadsheet directly.
"""
from __future__ import annotations

import streamlit as st

# Month data changes while people are using the app; the sheet list and the
# people in it change a few times a year.
MONTH_TTL = 45
DIRECTORY_TTL = 300


@st.cache_data(ttl=DIRECTORY_TTL, show_spinner=False)
def sheet_names(_service) -> list[str]:
    return _service.list_sheets()


@st.cache_data(ttl=DIRECTORY_TTL, show_spinner=False)
def room_entries(_service, worksheet_name: str):
    return _service.get_room_entries(worksheet_name)


@st.cache_data(ttl=MONTH_TTL, show_spinner=False)
def day_rows(_service, worksheet_name: str):
    return _service.get_day_rows(worksheet_name, room_entries(_service, worksheet_name))


@st.cache_data(ttl=MONTH_TTL, show_spinner=False)
def andet_rows(_service, worksheet_name: str):
    return _service.get_andet_rows(worksheet_name, room_entries(_service, worksheet_name))


@st.cache_data(ttl=MONTH_TTL, show_spinner=False)
def month_entries(_service, worksheet_name: str):
    return _service.get_day_to_day_entries(worksheet_name, room_entries(_service, worksheet_name))


@st.cache_data(ttl=MONTH_TTL, show_spinner=False)
def account_statement(_service, worksheet_name: str, room_label: str):
    entry = next((item for item in room_entries(_service, worksheet_name) if item.label == room_label), None)
    if entry is None:
        return None
    return _service.get_account_statement(worksheet_name, entry)


@st.cache_data(ttl=MONTH_TTL, show_spinner=False)
def personal_accounts(_service, worksheet_name: str):
    return _service.get_personal_account_entries(worksheet_name)


@st.cache_data(ttl=MONTH_TTL, show_spinner=False)
def planning_entries(_service, month_name: str, year: int):
    return _service.get_planning_entries(month_name, year)


@st.cache_data(ttl=MONTH_TTL, show_spinner=False)
def bank_details(_service, worksheet_name: str):
    return _service.get_kitchen_fund_bank_details(worksheet_name)


@st.cache_data(ttl=MONTH_TTL, show_spinner=False)
def fund_status(_service, worksheet_name: str):
    return _service.get_kitchen_fund_status(worksheet_name)


@st.cache_data(ttl=MONTH_TTL, show_spinner=False)
def possible_days_limit(_service, month_name: str, year: int) -> str:
    return _service.get_possible_days_limit(month_name, year)


@st.cache_data(ttl=MONTH_TTL, show_spinner=False)
def feedback_entries(_service, feedback_type: str):
    return _service.get_feedback_entries(feedback_type)


@st.cache_data(ttl=DIRECTORY_TTL, show_spinner=False)
def log_entries(_service):
    """The whole event history — appended to rarely, read on Admin only."""
    return _service.get_log_entries()


def clear_dinners() -> None:
    """A signup, a menu, a cook: the day table changed."""
    day_rows.clear()
    account_statement.clear()
    personal_accounts.clear()


def clear_money() -> None:
    """Drinks, purchases, payments and shared costs all move balances."""
    month_entries.clear()
    andet_rows.clear()
    day_rows.clear()
    account_statement.clear()
    personal_accounts.clear()


def clear_people() -> None:
    """Someone moved in, out or between accounts — every one of those is logged."""
    room_entries.clear()
    personal_accounts.clear()
    account_statement.clear()
    log_entries.clear()


def clear_planning() -> None:
    planning_entries.clear()
    possible_days_limit.clear()


def clear_feedback() -> None:
    feedback_entries.clear()


def clear_months() -> None:
    """A month sheet was created — the sheet list itself changed."""
    sheet_names.clear()
    bank_details.clear()
    fund_status.clear()
    clear_people()
    clear_dinners()
    clear_money()


def clear_everything() -> None:
    """What the Refresh button does."""
    st.cache_data.clear()
