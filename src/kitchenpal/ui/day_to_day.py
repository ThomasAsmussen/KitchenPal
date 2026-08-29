import calendar
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

import streamlit as st

from ..a1 import range_end_row as _range_end_row, range_start_row as _range_start_row
from ..constants import (
    DANISH_TO_ENGLISH_MONTH,
    ENGLISH_MONTHS,
    ENGLISH_TO_DANISH_MONTH,
    PURCHASE_LOOKUP_RANGE,
    PURCHASE_ROW_CAPACITY,
    TRANSACTION_ROW_CAPACITY,
)
from ..runtime_state import bump_cache_version, cache_key, get_cache_version
from ..sheets.utils import parse_month_sheet_name
from ..sheets_service import SheetsService
from .errors import show_user_error


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


def _room_display_factory(room_name_by_label: dict[str, str]):
    def room_display(label: str) -> str:
        room_name = room_name_by_label.get(label, "")
        return f"{label} — {room_name}" if room_name else label

    return room_display


def _render_refresh_button(key: str):
    loaded_at_key = f"{key}_loaded_at:{get_cache_version()}"
    if loaded_at_key not in st.session_state:
        st.session_state[loaded_at_key] = datetime.now(ZoneInfo("Europe/Copenhagen")).strftime("%H:%M")
    col1, col2 = st.columns([1, 4])
    if col1.button("Refresh data", key=key):
        bump_cache_version()
        st.rerun()
    col2.caption(f"Loaded from Google Sheets at {st.session_state[loaded_at_key]}.")


def _load_context(service: SheetsService, *, include_month_entries: bool, refresh_key: str) -> DayToDayContext | None:
    _render_refresh_button(refresh_key)

    sheets_list = _month_sheet_names(_get_cached_sheet_names(service))
    if not sheets_list:
        st.warning("No month sheets are available yet.")
        return None

    selected_sheet_name = st.selectbox("Month", sheets_list, index=_default_sheet_index(sheets_list))
    room_entries = _get_cached_room_entries(service, selected_sheet_name)
    if not room_entries:
        st.warning("No room mapping is available on this sheet.")
        return None

    signup_room_entries = [entry for entry in room_entries if entry.signup_column is not None]
    room_name_by_label = {entry.label: entry.name for entry in room_entries}
    room_labels = [entry.label for entry in room_entries]
    signup_room_labels = [entry.label for entry in signup_room_entries]
    month_entries = _get_cached_month_entries(service, selected_sheet_name, room_entries) if include_month_entries else None

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


def render_today_view(service: SheetsService):
    st.title("Today")
    context = _load_context(service, include_month_entries=False, refresh_key="today_refresh")
    if context is None:
        return

    if not context.signup_room_labels:
        st.warning("No rooms can sign up on this sheet.")
        return

    selected_day = _day_selectbox("Day", context.selected_sheet_name, key="today_signup_day")
    day_details = service.get_day_details(context.selected_sheet_name, selected_day)
    selected_day_display = _day_display(context.selected_sheet_name, selected_day)

    _render_meal_metrics(day_details, selected_day_display, context.room_name_by_label)
    _render_menu_box(day_details)

    room_display = _room_display_factory(context.room_name_by_label)
    with st.form(key="today_signup_form"):
        account_number = st.selectbox(
            "Room signing up",
            context.signup_room_labels,
            format_func=room_display,
            key="today_signup_room",
        )
        num_people = st.number_input(
            "People eating from this room",
            min_value=0,
            step=1,
            key="today_signup_people",
            value=1,
            help="This replaces the current signup count for the room. Use 0 to cancel a signup.",
        )
        submitted = st.form_submit_button("Save signup")

    if submitted:
        try:
            service.update_dish_signup(context.selected_sheet_name, selected_day, account_number, num_people)
            bump_cache_version()
            st.success(f"Saved {num_people} signed up for {room_display(account_number)}.")
            st.rerun()
        except ValueError as exc:
            show_user_error(st, exc, "Could not save signup")

    signed_people = service.get_signed_up_people(context.selected_sheet_name, selected_day, context.signup_room_entries)
    st.subheader("Signed up")
    if signed_people:
        for name in signed_people:
            st.markdown(f"- {name}")
    else:
        st.caption("No one is signed up yet.")


def render_host_dinner_view(service: SheetsService):
    st.title("Host Dinner")
    context = _load_context(service, include_month_entries=False, refresh_key="host_dinner_refresh")
    if context is None:
        return

    selected_day = _day_selectbox("Dinner date", context.selected_sheet_name, key="host_dinner_day")
    if st.session_state.pop(_meal_details_saved_key(context.selected_sheet_name, selected_day), False):
        st.success("Dinner details have been updated.")

    day_details = service.get_day_details(context.selected_sheet_name, selected_day)
    selected_day_display = _day_display(context.selected_sheet_name, selected_day)
    _render_meal_metrics(day_details, selected_day_display, context.room_name_by_label)

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
        submitted = st.form_submit_button("Save dinner details")

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
            bump_cache_version()
            st.session_state[_meal_details_saved_key(context.selected_sheet_name, selected_day)] = True
            st.rerun()
        except ValueError as exc:
            show_user_error(st, exc, "Could not save dinner details")


def render_drinks_purchases_view(service: SheetsService):
    st.title("Record Drinks & Purchases")
    context = _load_context(service, include_month_entries=True, refresh_key="drinks_purchases_refresh")
    if context is None or context.month_entries is None:
        return

    drinks_tab, purchases_tab = st.tabs(["Drinks", "Shared purchases"])
    with drinks_tab:
        _render_drinks_section(service, context)
    with purchases_tab:
        _render_purchases_section(service, context)


def _render_drinks_section(service: SheetsService, context: DayToDayContext):
    st.header("Drinks")
    room_display = _room_display_factory(context.room_name_by_label)
    with st.form(key="drinks_form"):
        room_number = st.selectbox("Room", context.room_labels, format_func=room_display, key="drinks_room")
        beer_quantity = st.number_input("Beers or sodas to add", min_value=0, step=1, key="drinks_beer")
        wine_quantity = st.number_input("Wine bottles to add", min_value=0, step=1, key="drinks_wine")
        st.caption("These numbers are added to the room's current drink totals.")
        submitted = st.form_submit_button("Add drinks")

    if submitted:
        if beer_quantity == 0 and wine_quantity == 0:
            st.error("Add at least one drink before saving.")
            return
        try:
            drink_entry = next((entry for entry in context.month_entries.drinks if entry.room == room_number), None)
            if drink_entry is None:
                new_beer, new_wine = service.add_drinks(
                    context.selected_sheet_name, room_number, beer_quantity, wine_quantity
                )
            else:
                new_beer = drink_entry.beer_soda + beer_quantity
                new_wine = drink_entry.wine + wine_quantity
                service.update_drinks(context.selected_sheet_name, drink_entry.row_number, new_beer, new_wine)
            _invalidate_month_entries(context.selected_sheet_name)
            st.success(f"Updated totals for {room_display(room_number)}: {new_beer} beers/sodas and {new_wine} wines.")
            st.rerun()
        except ValueError as exc:
            show_user_error(st, exc, "Could not update drinks")

    st.subheader("Drink totals")
    drink_entries = context.month_entries.drinks
    if drink_entries:
        st.table(_table_rows(drink_entries, exclude_keys=["row_number"]))
    else:
        st.caption("No drink rows found.")


def _table_usage_caption(used: int, capacity: int, noun: str) -> str:
    # The sheet's own formulas only sum the rows inside the table, so running
    # out is a real limit rather than a formality — say so before it bites.
    remaining = capacity - used
    if remaining <= 0:
        return f"The {noun} table is full ({used} of {capacity} rows). Edit or delete one before adding another."
    if remaining <= 5:
        return f"{used} of {capacity} {noun} rows used this month — {remaining} left."
    return f"{used} of {capacity} {noun} rows used this month."


def _render_purchases_section(service: SheetsService, context: DayToDayContext):
    st.header("Shared kitchen purchase")
    room_display = _room_display_factory(context.room_name_by_label)
    with st.form(key="purchase_form"):
        purchase_room = st.selectbox("Room paid", context.room_labels, format_func=room_display, key="purchase_room")
        purchase_item = st.text_input("What was bought?", key="purchase_item")
        purchase_date = st.date_input("Date", key="purchase_date")
        purchase_cost = st.number_input(
            "Total price (negative for refunds like pant)", step=0.01, key="purchase_cost"
        )
        submitted = st.form_submit_button("Register purchase")

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
            _invalidate_month_entries(context.selected_sheet_name)
            st.success(f"Registered purchase: {purchase_item} ({_format_amount_dkk(purchase_cost)}).")
            st.rerun()
        except ValueError as exc:
            show_user_error(st, exc, "Could not register purchase")

    st.subheader("Registered purchases")
    purchase_entries = context.month_entries.purchases
    st.caption(_table_usage_caption(len(purchase_entries), PURCHASE_ROW_CAPACITY, "purchase"))
    if not purchase_entries:
        st.caption("No purchases yet.")
        return

    st.table(_table_rows(purchase_entries, amount_keys=["amount"], exclude_keys=["row_number"]))
    st.subheader("Edit a purchase")
    selected_purchase = st.selectbox(
        "Purchase",
        purchase_entries,
        format_func=lambda entry: f"{entry.date} · {entry.room} · {entry.item} · {_format_amount_dkk(entry.amount)}",
        key="edit_purchase_entry",
    )

    edit_purchase_room_labels = list(context.room_labels)
    if selected_purchase.room and selected_purchase.room not in edit_purchase_room_labels:
        edit_purchase_room_labels.append(selected_purchase.room)

    with st.form(key=f"edit_purchase_form_{selected_purchase.row_number}"):
        edited_purchase_room = st.selectbox(
            "Room paid",
            edit_purchase_room_labels,
            index=edit_purchase_room_labels.index(selected_purchase.room)
            if selected_purchase.room in edit_purchase_room_labels
            else 0,
            format_func=room_display,
            key=f"edit_purchase_room_{selected_purchase.row_number}",
        )
        edited_purchase_item = st.text_input(
            "What was bought?",
            value=selected_purchase.item,
            key=f"edit_purchase_item_{selected_purchase.row_number}",
        )
        edited_purchase_date = st.date_input(
            "Date",
            value=_purchase_date_for_edit(selected_purchase.date, context.selected_sheet_name),
            key=f"edit_purchase_date_{selected_purchase.row_number}",
        )
        edited_purchase_cost = st.number_input(
            "Total price (negative for refunds like pant)",
            step=0.01,
            value=float(selected_purchase.amount),
            key=f"edit_purchase_cost_{selected_purchase.row_number}",
        )
        save_purchase = st.form_submit_button("Save purchase")
        delete_purchase = st.form_submit_button("Delete purchase")

    if save_purchase:
        if not edited_purchase_item.strip():
            st.error("Add what was bought before saving.")
            return
        if edited_purchase_cost == 0:
            st.error("Add a non-zero price before saving (negative for refunds).")
            return
        try:
            st.session_state.pop(_delete_confirmation_key("purchase", context.selected_sheet_name), None)
            service.update_purchase(
                context.selected_sheet_name,
                selected_purchase.row_number,
                edited_purchase_room,
                edited_purchase_date,
                edited_purchase_item,
                edited_purchase_cost,
            )
            _invalidate_month_entries(context.selected_sheet_name)
            st.success("Purchase updated.")
            st.rerun()
        except ValueError as exc:
            show_user_error(st, exc, "Could not update purchase")

    if delete_purchase:
        st.session_state[_delete_confirmation_key("purchase", context.selected_sheet_name)] = selected_purchase.row_number

    if st.session_state.get(_delete_confirmation_key("purchase", context.selected_sheet_name)) == selected_purchase.row_number:
        st.warning("Are you sure you want to delete this purchase?")
        confirm_col, cancel_col = st.columns(2)
        if confirm_col.button(
            "Yes, delete purchase",
            key=f"confirm_delete_purchase_{selected_purchase.row_number}",
        ):
            try:
                service.delete_purchase(context.selected_sheet_name, selected_purchase.row_number)
                st.session_state.pop(_delete_confirmation_key("purchase", context.selected_sheet_name), None)
                _invalidate_month_entries(context.selected_sheet_name)
                st.success("Purchase deleted.")
                st.rerun()
            except ValueError as exc:
                show_user_error(st, exc, "Could not delete purchase")
        if cancel_col.button("Cancel", key=f"cancel_delete_purchase_{selected_purchase.row_number}"):
            st.session_state.pop(_delete_confirmation_key("purchase", context.selected_sheet_name), None)
            st.rerun()


def render_kitchen_fund_view(service: SheetsService, embedded: bool = False):
    if embedded:
        st.header("Kitchen fund payments")
    else:
        st.title("Kitchen Fund Payments")
    context = _load_context(service, include_month_entries=True, refresh_key="kitchen_fund_refresh")
    if context is None or context.month_entries is None:
        return
    _render_transfers_section(service, context, show_header=not embedded)


def _render_transfers_section(service: SheetsService, context: DayToDayContext, show_header: bool = True):
    if show_header:
        st.header("Kitchen fund payments")
    room_display = _room_display_factory(context.room_name_by_label)
    with st.form(key="transaction_form"):
        transaction_room = st.selectbox("Room", context.room_labels, format_func=room_display, key="tx_room")
        transaction_type = st.selectbox(
            "Payment type",
            ["Payment to kitchen fund", "Payout from kitchen fund"],
            key="tx_type",
        )
        transaction_amount = st.number_input("Amount", min_value=0.0, step=0.01, key="tx_amount")
        transaction_date = st.date_input("Date", value=datetime.now(), key="tx_date")
        submitted = st.form_submit_button("Register payment")

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
            _invalidate_month_entries(context.selected_sheet_name)
            st.success("Kitchen fund payment registered.")
            st.rerun()
        except ValueError as exc:
            show_user_error(st, exc, "Could not register kitchen fund payment")

    st.subheader("Registered kitchen fund payments")
    transaction_entries = context.month_entries.transactions
    st.caption(_table_usage_caption(len(transaction_entries), TRANSACTION_ROW_CAPACITY, "payment"))
    if not transaction_entries:
        st.caption("No payments yet.")
        return

    st.table(_table_rows(transaction_entries, amount_keys=["amount"], exclude_keys=["row_number"]))
    st.subheader("Edit a payment")
    selected_transaction = st.selectbox(
        "Payment",
        transaction_entries,
        format_func=lambda entry: (
            f"{entry.date} · {entry.room} · {entry.transaction_type} · {_format_amount_dkk(entry.amount)}"
        ),
        key="edit_tx_entry",
    )

    edit_room_labels = list(context.room_labels)
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
            "Payment type",
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
            value=_transaction_date_for_edit(selected_transaction.date, context.selected_sheet_name),
            key=f"edit_tx_date_{selected_transaction.row_number}",
        )
        save_transfer = st.form_submit_button("Save payment")
        delete_transfer = st.form_submit_button("Delete payment")

    if save_transfer:
        if edited_amount <= 0:
            st.error("Add an amount greater than 0 before saving.")
            return
        try:
            st.session_state.pop(_delete_confirmation_key("transfer", context.selected_sheet_name), None)
            service.update_transaction(
                context.selected_sheet_name,
                selected_transaction.row_number,
                edited_room,
                edited_type,
                edited_amount,
                edited_date,
            )
            _invalidate_month_entries(context.selected_sheet_name)
            st.success("Kitchen fund payment updated.")
            st.rerun()
        except ValueError as exc:
            show_user_error(st, exc, "Could not update kitchen fund payment")

    if delete_transfer:
        st.session_state[_delete_confirmation_key("transfer", context.selected_sheet_name)] = selected_transaction.row_number

    if st.session_state.get(_delete_confirmation_key("transfer", context.selected_sheet_name)) == selected_transaction.row_number:
        st.warning("Are you sure you want to delete this payment?")
        confirm_col, cancel_col = st.columns(2)
        if confirm_col.button(
            "Yes, delete payment",
            key=f"confirm_delete_transfer_{selected_transaction.row_number}",
        ):
            try:
                service.delete_transaction(context.selected_sheet_name, selected_transaction.row_number)
                st.session_state.pop(_delete_confirmation_key("transfer", context.selected_sheet_name), None)
                _invalidate_month_entries(context.selected_sheet_name)
                st.success("Kitchen fund payment deleted.")
                st.rerun()
            except ValueError as exc:
                show_user_error(st, exc, "Could not delete kitchen fund payment")
        if cancel_col.button("Cancel", key=f"cancel_delete_transfer_{selected_transaction.row_number}"):
            st.session_state.pop(_delete_confirmation_key("transfer", context.selected_sheet_name), None)
            st.rerun()


def render_day_to_day_view(service: SheetsService):
    render_today_view(service)
