from datetime import datetime

import streamlit as st

from ..constants import ENGLISH_MONTHS
from ..runtime_state import bump_cache_version, cache_key
from ..sheets_service import SheetsService


def _default_day_index() -> int:
    return max(0, min(datetime.now().day - 1, 30))


def _ordinal(n: int) -> str:
    n = int(n)
    if 10 <= (n % 100) <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


_DANISH_TO_ENGLISH = {
    "januar": "January",
    "februar": "February",
    "marts": "March",
    "april": "April",
    "maj": "May",
    "juni": "June",
    "juli": "July",
    "august": "August",
    "september": "September",
    "oktober": "October",
    "november": "November",
    "december": "December",
}


def _english_month(month_raw: str) -> str:
    if not month_raw:
        return ""
    m = month_raw.strip()
    # If already English, return normalized name from ENGLISH_MONTHS
    for en in ENGLISH_MONTHS:
        if m.lower() == en.lower() or m.lower()[:3] == en.lower()[:3]:
            return en

    # Try Danish lookup
    return _DANISH_TO_ENGLISH.get(m.lower(), m)


def _get_cached_room_entries(service: SheetsService, worksheet_name: str):
    key = cache_key("day_to_day_room_entries", worksheet_name)
    if key not in st.session_state:
        st.session_state[key] = service.get_room_entries(worksheet_name)
    return st.session_state[key]


def _get_cached_sheet_names(service: SheetsService):
    key = cache_key("day_to_day_sheet_names")
    if key not in st.session_state:
        st.session_state[key] = service.list_sheets()
    return st.session_state[key]


def render_day_to_day_view(service: SheetsService):
    refresh_clicked = st.sidebar.button("Refresh data", key="day_to_day_refresh")
    if refresh_clicked:
        bump_cache_version()
        st.rerun()

    sheets_list = _get_cached_sheet_names(service)
    if not sheets_list:
        st.warning("No sheets are available yet.")
        return

    selected_sheet_name = st.selectbox("Choose month", sheets_list, index=0)
    room_entries = _get_cached_room_entries(service, selected_sheet_name)
    if not room_entries:
        st.warning("No room mapping is available on this sheet.")
        return

    signup_room_entries = [entry for entry in room_entries if entry.signup_column is not None]
    room_name_by_label = {entry.label: entry.name for entry in room_entries}
    room_labels = [entry.label for entry in room_entries]
    signup_room_labels = [entry.label for entry in signup_room_entries]

    def room_display(label: str) -> str:
        room_name = room_name_by_label.get(label, "")
        return f"{label} — {room_name}" if room_name else label

    sign_up_tab, drinks_tab, hold_club_tab, transaction_tab, expenses_tab = st.tabs(
        ["Sign up for food club", "Drinks", "Host food club", "KitchenPal transfers", "Add purchase"]
    )

    with sign_up_tab:
        st.header("Sign up for today's dish")
        selected_day = st.selectbox("Choose day", [i for i in range(1, 32)], index=_default_day_index(), key="signup_day")
        chef, menu, signed_up_num = service.get_day_summary(selected_sheet_name, selected_day)
        month_part_raw = selected_sheet_name.split()[0] if selected_sheet_name else ""
        month_part = _english_month(month_part_raw)
        selected_day_display = f"{month_part} {selected_day}{_ordinal(selected_day)}"

        summary_col1, summary_col2, summary_col3 = st.columns(3)
        summary_col1.metric("Date", selected_day_display)
        summary_col2.metric("Signed up", signed_up_num)
        summary_col3.metric("Budget", f"{int(signed_up_num) * 35} DKK")

        st.caption(f"Menu: {menu or 'No menu yet'}")
        st.caption(f"Chef: {chef or 'Not assigned'}")

        with st.form(key="signup_form"):
            account_number = st.selectbox(
                "Choose room to sign up",
                signup_room_labels,
                format_func=room_display,
                key="signup_room",
            )
            num_people = st.number_input("Number of people", min_value=0, step=1, key="signup_people", value=1)

            if st.form_submit_button("Sign up"):
                service.update_dish_signup(selected_sheet_name, selected_day, account_number, num_people)
                bump_cache_version()
                st.success(f"Added {num_people} person(s) to room {account_number}.")

        signed_people = service.get_signed_up_people(selected_sheet_name, selected_day, signup_room_entries)
        if signed_people:
            st.markdown("**People signed up:**")
            for name in signed_people:
                st.markdown(f"- {name}")
        else:
            st.markdown("**People signed up:** None")

    with hold_club_tab:
        st.header("Add today's dish")
        selected_day = st.selectbox("Choose day", [i for i in range(1, 32)], index=_default_day_index(), key="dish_day")
        chef, menu, signed_up_num = service.get_day_summary(selected_sheet_name, selected_day)
        month_part_raw = selected_sheet_name.split()[0] if selected_sheet_name else ""
        month_part = _english_month(month_part_raw)
        selected_day_display = f"{month_part} {selected_day}<sup>{_ordinal(selected_day)}</sup>"

        info_col1, info_col2, info_col3 = st.columns(3)
        info_col1.markdown(f"**{selected_day_display}**", unsafe_allow_html=True)
        info_col2.metric("Signed up", signed_up_num)
        info_col3.metric("Chef", chef or "None")

        st.caption(f"Current menu: {menu or 'No menu yet'}")

        with st.form(key="dish_form"):
            dish_name = st.text_input("Dish", key="dish_name")
            if st.form_submit_button("Save dish"):
                service.update_dish_name(selected_sheet_name, selected_day, dish_name)
                bump_cache_version()
                st.success("Today's dish has been updated.")

    with expenses_tab:
        st.header("Add purchase")
        with st.form(key="purchase_form"):
            purchase_room = st.selectbox("Room", room_labels, format_func=room_display, key="purchase_room")
            purchase_item = st.text_input("Item", key="purchase_item")
            purchase_date = st.date_input("Date", key="purchase_date")
            purchase_cost = st.number_input("Price", min_value=0.0, step=0.01, key="purchase_cost")

            if st.form_submit_button("Add item"):
                service.add_purchase(selected_sheet_name, purchase_room, purchase_date, purchase_item, purchase_cost)
                bump_cache_version()
                st.success(f"Added purchase: {purchase_item} ({purchase_cost} DKK).")

    with drinks_tab:
        st.header("Drinks")
        with st.form(key="drinks_form"):
            room_number = st.selectbox("Room", room_labels, format_func=room_display, key="drinks_room")
            beer_quantity = st.number_input("Number of beers", min_value=0, step=1, key="drinks_beer")
            wine_quantity = st.number_input("Number of wines", min_value=0, step=1, key="drinks_wine")

            if st.form_submit_button("Add drinks"):
                new_beer, new_wine = service.add_drinks(selected_sheet_name, room_number, beer_quantity, wine_quantity)
                bump_cache_version()
                st.success(f"Updated: {new_beer} beers and {new_wine} wines total.")

    with transaction_tab:
        st.header("Transfers")
        with st.form(key="transaction_form"):
            transaction_room = st.selectbox("Room", room_labels, format_func=room_display, key="tx_room")
            transaction_type = st.selectbox(
                "Type",
                ["Payment to kitchen fund", "Payout from kitchen fund"],
                key="tx_type",
            )
            transaction_amount = st.number_input("Amount", min_value=0.0, step=0.01, key="tx_amount")
            transaction_date = st.date_input("Date", value=datetime.now(), key="tx_date")

            if st.form_submit_button("Add transfer"):
                service.add_transaction(selected_sheet_name, transaction_room, transaction_type, transaction_amount, transaction_date)
                bump_cache_version()
                st.success("Transfer registered.")
