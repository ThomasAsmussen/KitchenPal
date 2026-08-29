"""Which month the app is showing.

One choice for the whole app instead of a picker per screen: if you go to look
at last month's dinners, your balance should be last month's too.
"""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from ..constants import ENGLISH_MONTHS, ENGLISH_TO_DANISH_MONTH
from ..sheets.utils import parse_month_sheet_name
from . import data

MONTH_STATE_KEY = "kitchenpal_month"


def cached_sheet_names(service):
    return data.sheet_names(service)


def month_sheet_names(sheet_names: list[str]) -> list[str]:
    return [name for name in sheet_names if parse_month_sheet_name(name) is not None]


def default_month_index(sheets_list: list[str]) -> int:
    """This month if it exists, otherwise the first sheet."""
    now = datetime.now()
    english = ENGLISH_MONTHS[now.month - 1]
    candidates = [f"{english} {now.year}"]
    danish = ENGLISH_TO_DANISH_MONTH.get(english)
    if danish:
        candidates.append(f"{danish} {now.year}")
    for candidate in candidates:
        if candidate in sheets_list:
            return sheets_list.index(candidate)
    return 0


def available_months(service) -> list[str]:
    return month_sheet_names(cached_sheet_names(service))


def current_month_sheet(service) -> str | None:
    sheets_list = available_months(service)
    if not sheets_list:
        return None
    if st.session_state.get(MONTH_STATE_KEY) not in sheets_list:
        st.session_state.pop(MONTH_STATE_KEY, None)
    return st.session_state.get(MONTH_STATE_KEY, sheets_list[default_month_index(sheets_list)])


def is_current_month(worksheet_name: str) -> bool:
    now = datetime.now()
    return parse_month_sheet_name(worksheet_name) == (now.month, now.year)


def render_month_picker(service, label: str = "Month") -> str | None:
    """The one control that changes the month, wherever it is drawn."""
    sheets_list = available_months(service)
    if not sheets_list:
        return None
    current = current_month_sheet(service)
    st.selectbox(label, sheets_list, index=sheets_list.index(current), key=MONTH_STATE_KEY)
    return st.session_state.get(MONTH_STATE_KEY, current)
