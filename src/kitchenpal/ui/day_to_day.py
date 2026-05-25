from datetime import date, datetime

import streamlit as st

from ..a1 import range_end_row as _range_end_row, range_start_row as _range_start_row
from ..constants import DANISH_TO_ENGLISH_MONTH, ENGLISH_MONTHS, ENGLISH_TO_DANISH_MONTH, PURCHASE_LOOKUP_RANGE
from ..runtime_state import bump_cache_version, cache_key
from ..sheets.utils import parse_month_sheet_name
from ..sheets_service import SheetsService
from .errors import show_user_error


def _default_day_index() -> int:
    return max(0, min(datetime.now().day - 1, 30))


def _ordinal(n: int) -> str:
    n = int(n)
    if 10 <= (n % 100) <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _english_month(month_raw: str) -> str:
    if not month_raw:
        return ""
    m = month_raw.strip()
    for en in ENGLISH_MONTHS:
        if m.lower() == en.lower() or m.lower()[:3] == en.lower()[:3]:
            return en

    return DANISH_TO_ENGLISH_MONTH.get(m.title(), m)


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


def _month_entries_cache_key(worksheet_name: str) -> str:
    return cache_key("day_to_day_month_entries", worksheet_name)


def _get_cached_month_entries(service: SheetsService, worksheet_name: str, room_entries):
    key = _month_entries_cache_key(worksheet_name)
    if key not in st.session_state:
        st.session_state[key] = service.get_day_to_day_entries(worksheet_name, room_entries)
    return st.session_state[key]


def _invalidate_month_entries(worksheet_name: str):
    st.session_state.pop(_month_entries_cache_key(worksheet_name), None)


def _delete_confirmation_key(kind: str, worksheet_name: str) -> str:
    return f"day_to_day_confirm_delete_{kind}:{worksheet_name}"


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


def _format_amount_dkk(amount: float) -> str:
    return f"{amount:.2f} DKK"


def _table_rows(entries, amount_keys=None, exclude_keys=None):
    amount_keys = amount_keys or []
    exclude_keys = set(exclude_keys or [])
    rows = []
    for entry in entries:
        row = {key: value for key, value in entry.__dict__.items() if key not in exclude_keys}
        for key in amount_keys:
            if key in row:
                row[key] = _format_amount_dkk(float(row[key]))
        rows.append(row)
    return rows


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


def _transaction_date_for_edit(value: str, worksheet_name: str) -> date:
    text = str(value or "").strip()
    if not text:
        return datetime.now().date()

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m"):
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt == "%d/%m":
                return parsed.replace(year=_sheet_year(worksheet_name)).date()
            return parsed.date()
        except ValueError:
            continue

    return datetime.now().date()


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


def render_day_to_day_view(service: SheetsService):
    refresh_clicked = st.sidebar.button("Refresh data", key="day_to_day_refresh")
    if refresh_clicked:
        bump_cache_version()
        st.rerun()

    sheets_list = _month_sheet_names(_get_cached_sheet_names(service))
    if not sheets_list:
        st.warning("No month sheets are available yet.")
        return

    selected_sheet_name = st.selectbox("Choose month", sheets_list, index=_default_sheet_index(sheets_list))
    room_entries = _get_cached_room_entries(service, selected_sheet_name)
    if not room_entries:
        st.warning("No room mapping is available on this sheet.")
        return

    signup_room_entries = [entry for entry in room_entries if entry.signup_column is not None]
    room_name_by_label = {entry.label: entry.name for entry in room_entries}
    room_labels = [entry.label for entry in room_entries]
    signup_room_labels = [entry.label for entry in signup_room_entries]
    month_entries = _get_cached_month_entries(service, selected_sheet_name, room_entries)

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
        selected_day_display = _selected_day_display(month_part, selected_day)

        summary_col1, summary_col2, summary_col3 = st.columns(3)
        summary_col1.metric("Date", selected_day_display)
        summary_col2.metric("Signed up", signed_up_num)
        summary_col3.metric("Budget", f"{int(signed_up_num) * 35} DKK")

        detail_col1, detail_col2, detail_col3 = st.columns(3)
        detail_col1.metric("Menu", menu or "No menu yet")
        detail_col2.metric("Chef", _display_chef(chef, room_name_by_label))
        detail_col3.empty()

        with st.form(key="signup_form"):
            account_number = st.selectbox(
                "Choose room to sign up",
                signup_room_labels,
                format_func=room_display,
                key="signup_room",
            )
            num_people = st.number_input("Number of people", min_value=0, step=1, key="signup_people", value=1)

            if st.form_submit_button("Sign up"):
                try:
                    service.update_dish_signup(selected_sheet_name, selected_day, account_number, num_people)
                    bump_cache_version()
                    st.success(f"Added {num_people} person(s) to room {account_number}.")
                except ValueError as exc:
                    show_user_error(st, exc, "Could not update signup")

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
        selected_day_display = _selected_day_display(month_part, selected_day)

        info_col1, info_col2, info_col3 = st.columns(3)
        info_col1.metric("Date", selected_day_display)
        info_col2.metric("Signed up", signed_up_num)
        info_col3.metric("Chef", _display_chef(chef, room_name_by_label))

        st.caption(f"Current menu: {menu or 'No menu yet'}")

        with st.form(key="dish_form"):
            dish_name = st.text_input("Dish", key="dish_name")
            if st.form_submit_button("Save dish"):
                try:
                    service.update_dish_name(selected_sheet_name, selected_day, dish_name)
                    bump_cache_version()
                    st.success("Today's dish has been updated.")
                except ValueError as exc:
                    show_user_error(st, exc, "Could not save dish")

    with expenses_tab:
        st.header("Add purchase")
        with st.form(key="purchase_form"):
            purchase_room = st.selectbox("Room", room_labels, format_func=room_display, key="purchase_room")
            purchase_item = st.text_input("Item", key="purchase_item")
            purchase_date = st.date_input("Date", key="purchase_date")
            purchase_cost = st.number_input("Price", min_value=0.0, step=0.01, key="purchase_cost")

            if st.form_submit_button("Add item"):
                try:
                    target_row = _next_available_row(
                        month_entries.purchases,
                        _range_start_row(PURCHASE_LOOKUP_RANGE) + 1,
                        _range_end_row(PURCHASE_LOOKUP_RANGE),
                    )
                    if target_row is None:
                        service.add_purchase(selected_sheet_name, purchase_room, purchase_date, purchase_item, purchase_cost)
                    else:
                        service.update_purchase(
                            selected_sheet_name,
                            target_row,
                            purchase_room,
                            purchase_date,
                            purchase_item,
                            purchase_cost,
                        )
                    _invalidate_month_entries(selected_sheet_name)
                    st.success(f"Added purchase: {purchase_item} ({_format_amount_dkk(purchase_cost)}).")
                    st.rerun()
                except ValueError as exc:
                    show_user_error(st, exc, "Could not add purchase")

        st.subheader("Purchase list")
        purchase_entries = month_entries.purchases
        if purchase_entries:
            st.table(_table_rows(purchase_entries, amount_keys=["amount"], exclude_keys=["row_number"]))

            st.subheader("Edit registered purchase")
            selected_purchase = st.selectbox(
                "Choose purchase",
                purchase_entries,
                format_func=lambda entry: f"{entry.date} · {entry.room} · {entry.item} · {_format_amount_dkk(entry.amount)}",
                key="edit_purchase_entry",
            )

            edit_purchase_room_labels = list(room_labels)
            if selected_purchase.room and selected_purchase.room not in edit_purchase_room_labels:
                edit_purchase_room_labels.append(selected_purchase.room)

            with st.form(key=f"edit_purchase_form_{selected_purchase.row_number}"):
                edited_purchase_room = st.selectbox(
                    "Room",
                    edit_purchase_room_labels,
                    index=edit_purchase_room_labels.index(selected_purchase.room)
                    if selected_purchase.room in edit_purchase_room_labels
                    else 0,
                    format_func=room_display,
                    key=f"edit_purchase_room_{selected_purchase.row_number}",
                )
                edited_purchase_item = st.text_input(
                    "Item",
                    value=selected_purchase.item,
                    key=f"edit_purchase_item_{selected_purchase.row_number}",
                )
                edited_purchase_date = st.date_input(
                    "Date",
                    value=_purchase_date_for_edit(selected_purchase.date, selected_sheet_name),
                    key=f"edit_purchase_date_{selected_purchase.row_number}",
                )
                edited_purchase_cost = st.number_input(
                    "Price",
                    min_value=0.0,
                    step=0.01,
                    value=max(0.0, float(selected_purchase.amount)),
                    key=f"edit_purchase_cost_{selected_purchase.row_number}",
                )

                save_purchase = st.form_submit_button("Save purchase")
                delete_purchase = st.form_submit_button("Delete purchase")

                if save_purchase:
                    try:
                        st.session_state.pop(_delete_confirmation_key("purchase", selected_sheet_name), None)
                        service.update_purchase(
                            selected_sheet_name,
                            selected_purchase.row_number,
                            edited_purchase_room,
                            edited_purchase_date,
                            edited_purchase_item,
                            edited_purchase_cost,
                        )
                        _invalidate_month_entries(selected_sheet_name)
                        st.success("Purchase updated.")
                        st.rerun()
                    except ValueError as exc:
                        show_user_error(st, exc, "Could not update purchase")

                if delete_purchase:
                    st.session_state[_delete_confirmation_key("purchase", selected_sheet_name)] = selected_purchase.row_number

            if st.session_state.get(_delete_confirmation_key("purchase", selected_sheet_name)) == selected_purchase.row_number:
                st.warning("Are you sure you want to delete this purchase?")
                confirm_col, cancel_col = st.columns(2)
                if confirm_col.button(
                    "Yes, delete purchase",
                    key=f"confirm_delete_purchase_{selected_purchase.row_number}",
                ):
                    try:
                        service.delete_purchase(selected_sheet_name, selected_purchase.row_number)
                        st.session_state.pop(_delete_confirmation_key("purchase", selected_sheet_name), None)
                        _invalidate_month_entries(selected_sheet_name)
                        st.success("Purchase deleted.")
                        st.rerun()
                    except ValueError as exc:
                        show_user_error(st, exc, "Could not delete purchase")
                if cancel_col.button("Cancel", key=f"cancel_delete_purchase_{selected_purchase.row_number}"):
                    st.session_state.pop(_delete_confirmation_key("purchase", selected_sheet_name), None)
                    st.rerun()
        else:
            st.caption("No purchases yet.")

    with drinks_tab:
        st.header("Drinks")
        with st.form(key="drinks_form"):
            room_number = st.selectbox("Room", room_labels, format_func=room_display, key="drinks_room")
            beer_quantity = st.number_input("Number of beers", min_value=0, step=1, key="drinks_beer")
            wine_quantity = st.number_input("Number of wines", min_value=0, step=1, key="drinks_wine")

            if st.form_submit_button("Add drinks"):
                try:
                    drink_entry = next((entry for entry in month_entries.drinks if entry.room == room_number), None)
                    if drink_entry is None:
                        new_beer, new_wine = service.add_drinks(
                            selected_sheet_name, room_number, beer_quantity, wine_quantity
                        )
                    else:
                        new_beer = drink_entry.beer_soda + beer_quantity
                        new_wine = drink_entry.wine + wine_quantity
                        service.update_drinks(selected_sheet_name, drink_entry.row_number, new_beer, new_wine)
                    _invalidate_month_entries(selected_sheet_name)
                    st.success(f"Updated: {new_beer} beers and {new_wine} wines total.")
                    st.rerun()
                except ValueError as exc:
                    show_user_error(st, exc, "Could not update drinks")

        st.subheader("Drinks list")
        drink_entries = month_entries.drinks
        if drink_entries:
            st.table(_table_rows(drink_entries, exclude_keys=["row_number"]))
        else:
            st.caption("No drink rows found.")

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
                try:
                    target_row = _next_available_row(month_entries.transactions, 44)
                    if target_row is None:
                        service.add_transaction(
                            selected_sheet_name, transaction_room, transaction_type, transaction_amount, transaction_date
                        )
                    else:
                        service.update_transaction(
                            selected_sheet_name,
                            target_row,
                            transaction_room,
                            transaction_type,
                            transaction_amount,
                            transaction_date,
                        )
                    _invalidate_month_entries(selected_sheet_name)
                    st.success("Transfer registered.")
                    st.rerun()
                except ValueError as exc:
                    show_user_error(st, exc, "Could not add transfer")

        st.subheader("Transfers list")
        transaction_entries = month_entries.transactions
        if transaction_entries:
            st.table(_table_rows(transaction_entries, amount_keys=["amount"], exclude_keys=["row_number"]))

            st.subheader("Edit registered transfer")
            selected_transaction = st.selectbox(
                "Choose transfer",
                transaction_entries,
                format_func=lambda entry: (
                    f"{entry.date} · {entry.room} · {entry.transaction_type} · {_format_amount_dkk(entry.amount)}"
                ),
                key="edit_tx_entry",
            )

            edit_room_labels = list(room_labels)
            if selected_transaction.room and selected_transaction.room not in edit_room_labels:
                edit_room_labels.append(selected_transaction.room)

            edit_type_options = ["Payment to kitchen fund", "Payout from kitchen fund"]
            if selected_transaction.transaction_type and selected_transaction.transaction_type not in edit_type_options:
                edit_type_options.append(selected_transaction.transaction_type)

            with st.form(key=f"edit_transaction_form_{selected_transaction.row_number}"):
                edited_room = st.selectbox(
                    "Room",
                    edit_room_labels,
                    index=edit_room_labels.index(selected_transaction.room)
                    if selected_transaction.room in edit_room_labels
                    else 0,
                    format_func=room_display,
                    key=f"edit_tx_room_{selected_transaction.row_number}",
                )
                edited_type = st.selectbox(
                    "Type",
                    edit_type_options,
                    index=edit_type_options.index(selected_transaction.transaction_type)
                    if selected_transaction.transaction_type in edit_type_options
                    else 0,
                    key=f"edit_tx_type_{selected_transaction.row_number}",
                )
                edited_amount = st.number_input(
                    "Amount",
                    min_value=0.0,
                    step=0.01,
                    value=abs(float(selected_transaction.amount)),
                    key=f"edit_tx_amount_{selected_transaction.row_number}",
                )
                edited_date = st.date_input(
                    "Date",
                    value=_transaction_date_for_edit(selected_transaction.date, selected_sheet_name),
                    key=f"edit_tx_date_{selected_transaction.row_number}",
                )

                save_transfer = st.form_submit_button("Save transfer")
                delete_transfer = st.form_submit_button("Delete transfer")

                if save_transfer:
                    try:
                        st.session_state.pop(_delete_confirmation_key("transfer", selected_sheet_name), None)
                        service.update_transaction(
                            selected_sheet_name,
                            selected_transaction.row_number,
                            edited_room,
                            edited_type,
                            edited_amount,
                            edited_date,
                        )
                        _invalidate_month_entries(selected_sheet_name)
                        st.success("Transfer updated.")
                        st.rerun()
                    except ValueError as exc:
                        show_user_error(st, exc, "Could not update transfer")

                if delete_transfer:
                    st.session_state[_delete_confirmation_key("transfer", selected_sheet_name)] = selected_transaction.row_number

            if st.session_state.get(_delete_confirmation_key("transfer", selected_sheet_name)) == selected_transaction.row_number:
                st.warning("Are you sure you want to delete this transfer?")
                confirm_col, cancel_col = st.columns(2)
                if confirm_col.button(
                    "Yes, delete transfer",
                    key=f"confirm_delete_transfer_{selected_transaction.row_number}",
                ):
                    try:
                        service.delete_transaction(selected_sheet_name, selected_transaction.row_number)
                        st.session_state.pop(_delete_confirmation_key("transfer", selected_sheet_name), None)
                        _invalidate_month_entries(selected_sheet_name)
                        st.success("Transfer deleted.")
                        st.rerun()
                    except ValueError as exc:
                        show_user_error(st, exc, "Could not delete transfer")
                if cancel_col.button("Cancel", key=f"cancel_delete_transfer_{selected_transaction.row_number}"):
                    st.session_state.pop(_delete_confirmation_key("transfer", selected_sheet_name), None)
                    st.rerun()
        else:
            st.caption("No transfers yet.")
