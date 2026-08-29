from types import SimpleNamespace

from kitchenpal.sheets_service import PlanningEntry
from kitchenpal.ui import month_setup


def test_month_sheet_names_keeps_only_english_or_danish_month_year_names():
    sheet_names = ["Planning", "May 2026", "Maj 2026", "Bugs", "New Features", "May", "2026 May", "May 26"]

    assert month_setup._month_sheet_names(sheet_names) == ["May 2026", "Maj 2026"]


def test_month_sheet_for_accepts_english_and_danish_month_names():
    sheet_names = ["May 2026", "Juni 2026", "Planning"]

    assert month_setup._month_sheet_for(5, 2026, sheet_names) == "May 2026"
    assert month_setup._month_sheet_for(6, 2026, sheet_names) == "Juni 2026"
    assert month_setup._month_sheet_for(7, 2026, sheet_names) is None


def _planning_context(entries):
    return SimpleNamespace(
        year=2026, month=9, month_name="September", sheet_name="September 2026",
        room_entries=entries, stored_entries={}, possible_days=[], limit_days="",
    )


def _entry(label, name):
    return SimpleNamespace(label=label, name=name, signup_column=1)


def test_planning_answers_follow_the_person_into_next_months_room(monkeypatch):
    # In 356 this month, 350 next month: the answers belong to 350, and must not
    # land on the card of whoever takes 356.
    august = [_entry("356", "Julia"), _entry("350", "Thor")]
    september = [_entry("356", "Thor"), _entry("350", "Julia")]
    monkeypatch.setattr(month_setup, "current_room", lambda entries: "356")
    monkeypatch.setattr(
        "kitchenpal.ui.day_to_day.identity_room_entries", lambda service: august
    )

    entry, claimed = month_setup._planning_room_entry(object(), _planning_context(september))

    assert (entry.label, claimed) == ("350", "356")


def test_planning_refuses_to_answer_for_whoever_took_your_old_room(monkeypatch):
    august = [_entry("356", "Julia")]
    september = [_entry("356", "Thor")]
    monkeypatch.setattr(month_setup, "current_room", lambda entries: "356")
    monkeypatch.setattr(
        "kitchenpal.ui.day_to_day.identity_room_entries", lambda service: august
    )

    entry, claimed = month_setup._planning_room_entry(object(), _planning_context(september))

    assert entry is None
    assert claimed == "356"


def test_planning_falls_back_to_the_label_when_nothing_moved(monkeypatch):
    people = [_entry("356", "Julia")]
    monkeypatch.setattr(month_setup, "current_room", lambda entries: "356")
    monkeypatch.setattr(
        "kitchenpal.ui.day_to_day.identity_room_entries", lambda service: people
    )

    entry, _ = month_setup._planning_room_entry(object(), _planning_context(people))

    assert entry.label == "356"


def test_silence_from_someone_without_a_room_is_not_a_yes():
    # combine_availability reads an empty available list as "every day", so an
    # unanswered FL person would otherwise be a candidate for every dinner.
    context = SimpleNamespace(
        year=2026, month=9, month_name="September", sheet_name="September 2026",
        room_entries=[_entry("356", "Julia"), _entry("FL1", "Gustav")],
        stored_entries={}, possible_days=[1, 2, 3], limit_days="",
    )

    available, unavailable, preferences, limit_one_day, person_to_room = month_setup._stored_availability(context)

    assert unavailable["Gustav"] == ["1", "2", "3"]
    assert available["Gustav"] == []
    # Someone on the rota is untouched: silence still means every day.
    assert unavailable["Julia"] == []
    assert person_to_room == {"Julia": "356", "Gustav": "FL1"}


def test_an_answer_from_someone_without_a_room_is_used():
    from kitchenpal.sheets_service import PlanningEntry

    context = SimpleNamespace(
        year=2026, month=9, month_name="September", sheet_name="September 2026",
        room_entries=[_entry("FL1", "Gustav")],
        stored_entries={
            "FL1": PlanningEntry(
                person="Gustav", room_number="FL1", available_dates="2",
                unavailable_dates="", preferred_dates="2", limit_one_day=False,
            )
        },
        possible_days=[1, 2, 3], limit_days="",
    )

    available, unavailable, preferences, _, _ = month_setup._stored_availability(context)

    assert available["Gustav"] == ["2"]
    assert preferences["Gustav"] == [2]


def test_the_rota_is_rooms_with_people_in_them():
    context = _planning_context([_entry("356", "Julia"), _entry("350", ""), _entry("FL1", "Gustav")])

    assert [entry.label for entry in month_setup._rota_entries(context)] == ["356"]


def test_unassigned_people_with_room_numbers_filters_non_room_accounts():
    people = month_setup._unassigned_people_with_room_numbers(
        ["Julia", "Gustav", "Missing"],
        {
            "Julia": "357",
            "Gustav": "FL1",
        },
    )

    assert people == ["Julia (357)"]









def test_default_cannot_host_false_for_non_room_with_saved_available_day():
    stored_entry = PlanningEntry(
        person="Gustav",
        room_number="FL1",
        available_dates="7",
        unavailable_dates="",
        preferred_dates="",
        limit_one_day=False,
    )

    assert month_setup._default_cannot_host_this_month("FL1", stored_entry, [1, 2, 7], 2026, 6) is False


def test_default_cannot_host_true_for_non_room_without_saved_choices():
    assert month_setup._default_cannot_host_this_month("FL1", None, [1, 2, 7], 2026, 6) is True


def test_default_date_category_uses_unavailable_when_only_cannot_dates_are_saved():
    stored_entry = PlanningEntry(
        person="Philip",
        room_number="354",
        available_dates="",
        unavailable_dates="1, 2, 3, 24",
        preferred_dates="",
        limit_one_day=False,
    )

    assert month_setup._default_date_category(stored_entry, 2026, 6) == "unavailable"



def test_weekday_label_uses_one_letter():
    assert month_setup._weekday_label("Monday") == "M"
    assert month_setup._weekday_label("Thursday") == "T"


def test_planning_overview_rows_show_current_choices():
    rows = month_setup.planning_overview_rows(
        people_list=["Julia", "Gustav"],
        person_to_room={"Julia": "346", "Gustav": "FL1"},
        available={"Julia": ["2", "4"], "Gustav": []},
        unavailable={"Julia": [], "Gustav": ["1", "2", "3"]},
        preferences={"Julia": [4], "Gustav": []},
        limit_one_day_per_person={"Julia": True, "Gustav": False},
    )

    assert rows == [
        {
            "Person": "Julia",
            "Room": "346",
            "Can host": "2, 4",
            "Cannot host": "None",
            "Preferred": "4",
            "Host at most once": "Yes",
        },
        {
            "Person": "Gustav",
            "Room": "FL1",
            "Can host": "None",
            "Cannot host": "1, 2, 3",
            "Preferred": "None",
            "Host at most once": "No",
        },
    ]


def test_planning_overview_rows_show_empty_availability_as_all_possible_dates():
    rows = month_setup.planning_overview_rows(
        people_list=["Julia"],
        person_to_room={"Julia": "346"},
        available={"Julia": []},
        unavailable={"Julia": []},
        preferences={"Julia": []},
        limit_one_day_per_person={"Julia": False},
    )

    assert rows[0]["Can host"] == "All possible dates"


def _planner_app():
    import streamlit as st

    from kitchenpal.ui.plan import render_planning_view

    render_planning_view(st.session_state["planner_service"])


class _FakeSheet:
    """Just enough of a gspread worksheet for the Planning/Possible Days reads."""

    def __init__(self, rows=()):
        self.rows = [list(row) for row in rows]

    def get_all_values(self):
        return [list(row) for row in self.rows]

    def clear(self):
        self.rows = []

    def update(self, range_name, values):
        start_row = int("".join(character for character in range_name.split(":")[0] if character.isdigit()))
        while len(self.rows) < start_row - 1 + len(values):
            self.rows.append([""] * 8)
        for offset, row in enumerate(values):
            self.rows[start_row - 1 + offset] = [str(cell) for cell in row]


def _planner_service(month_sheet_name, planning_rows, room_names):
    from kitchenpal.constants import PLANNING_HEADERS
    from kitchenpal.sheets.planning import PlanningSheetsMixin
    from kitchenpal.sheets_service import RoomEntry

    class _Service(PlanningSheetsMixin):
        def __init__(self):
            self.sheets = {
                "Planning": _FakeSheet([list(PLANNING_HEADERS)] + list(planning_rows)),
                "Possible Days": _FakeSheet([["Year", "Month", "Limit days"]]),
                month_sheet_name: _FakeSheet(),
            }

        def list_sheets(self):
            return list(self.sheets)

        def get_worksheet(self, worksheet_name):
            return self.sheets[worksheet_name]

        def get_room_entries(self, worksheet_name):
            return [
                RoomEntry(label=label, name=room_names.get(label, ""), account_row=45 + index, signup_column=9 + index)
                for index, label in enumerate(["348", "350", "352"])
            ]

        def planning_rows(self):
            return [row for row in self.sheets["Planning"].get_all_values()[1:] if any(row)]

    return _Service()


def _day_button(at, label, month_name, year, day):
    key = f"planning_days_{year}_{month_name}_{label}_day_{day}"
    matches = [button for button in at.button if button.key == key]
    assert len(matches) == 1, (key, [button.key for button in at.button])
    return matches[0]


def _day_states(at, label, month_name, year):
    return at.session_state[f"planning_days_{year}_{month_name}_{label}"]


def test_planner_updates_the_stored_room_row_when_the_month_sheet_name_changes():
    # Reproduces the September corruption: the sign-ups were written while the
    # month sheet had no names, so the Planning rows are keyed by room number.
    # Once the names come back, editing must reload and update those rows
    # instead of orphaning them behind a duplicate.
    from datetime import datetime, timedelta

    from streamlit.testing.v1 import AppTest

    from kitchenpal.constants import ENGLISH_MONTHS
    from kitchenpal.scheduler import get_weekdays_in_month

    planned = datetime.now().replace(day=1) + timedelta(days=32)
    month_name = ENGLISH_MONTHS[planned.month - 1]
    month_sheet_name = f"{month_name} {planned.year}"
    possible_days = get_weekdays_in_month(planned.year, planned.month)
    stored_days, added_day = possible_days[:3], possible_days[3]

    service = _planner_service(
        month_sheet_name=month_sheet_name,
        planning_rows=[
            [str(planned.year), month_name, "348", "348", ", ".join(str(day) for day in possible_days[:2]), "", "", "FALSE"],
            [str(planned.year), month_name, "350", "350", ", ".join(str(day) for day in stored_days), "", "", "FALSE"],
        ],
        room_names={"348": "Alberte", "350": "Josefine", "352": "Asta"},
    )

    at = AppTest.from_function(_planner_app)
    at.session_state["planner_service"] = service
    # the app knows who you are, so Plan shows one card: yours
    at.query_params["room"] = "350"
    at.run()
    assert not at.exception

    # Her answer loads even though the row was saved under the room number, and
    # an old whitelist answer keeps its meaning: the days she did not list were
    # her no.
    at.button(key="planning_edit").click().run()
    states = _day_states(at, "350", month_name, planned.year)
    assert [day for day, state in states.items() if state == "can"] == stored_days

    _day_button(at, "350", month_name, planned.year, added_day).click().run()
    at.button(key="planning_save").click().run()
    assert not at.exception

    rows = service.planning_rows()
    assert len(rows) == 2, rows
    assert rows[0][2:4] == ["348", "348"]
    # Her row is still keyed on the room and is now named, not duplicated.
    assert rows[1][2:4] == ["Josefine", "350"]
    assert str(added_day) in rows[1][4]


def test_upcoming_dinners_lists_only_days_someone_is_cooking():
    from kitchenpal.sheets_service import DayRow
    from kitchenpal.ui.day_to_day import upcoming_dinners

    rows = [
        DayRow(day=1, chef="346", menu="", menu_description="", signed_up=3, meal_price=0.0, signups={}),
        DayRow(day=2, chef="", menu="", menu_description="", signed_up=0, meal_price=0.0, signups={}),
        DayRow(day=3, chef="", menu="Rester", menu_description="", signed_up=0, meal_price=0.0, signups={}),
        DayRow(day=4, chef="350", menu="", menu_description="", signed_up=0, meal_price=0.0, signups={}),
        DayRow(day=5, chef="352", menu="", menu_description="", signed_up=0, meal_price=0.0, signups={}),
    ]

    assert [row.day for row in upcoming_dinners(rows, from_day=1)] == [3, 4, 5]
    assert [row.day for row in upcoming_dinners(rows, from_day=1, limit=1)] == [3]
    assert upcoming_dinners(rows, from_day=5) == []


def test_my_cooking_nights_picks_out_your_own_days():
    from kitchenpal.sheets_service import DayRow
    from kitchenpal.ui.day_to_day import my_cooking_nights

    rows = [
        DayRow(day=1, chef="346", menu="", menu_description="", signed_up=0, meal_price=0.0, signups={}),
        DayRow(day=7, chef="350", menu="", menu_description="", signed_up=0, meal_price=0.0, signups={}),
        DayRow(day=9, chef="350", menu="", menu_description="", signed_up=0, meal_price=0.0, signups={}),
    ]

    assert [row.day for row in my_cooking_nights(rows, "350")] == [7, 9]
    # nobody has claimed a room yet: no list at all, rather than everyone's
    assert my_cooking_nights(rows, "") == []


def test_statement_detail_counts_what_the_app_can_know():
    from kitchenpal.sheets_service import DayRow, DrinkEntry, PurchaseEntry
    from kitchenpal.ui.day_to_day import statement_detail

    day_rows = [
        DayRow(day=1, chef="350", menu="", menu_description="", signed_up=4, meal_price=0.0, signups={"350": 2}),
        DayRow(day=2, chef="346", menu="", menu_description="", signed_up=1, meal_price=0.0, signups={"350": 1}),
        DayRow(day=3, chef="350", menu="", menu_description="", signed_up=0, meal_price=0.0, signups={}),
    ]
    drinks = [DrinkEntry(row_number=5, room="350", name="Josefine", beer_soda=4, wine=1)]
    purchases = [
        PurchaseEntry(row_number=3, room="350", date="2026-08-02", item="Milk", amount=20.0),
        PurchaseEntry(row_number=4, room="346", date="2026-08-03", item="Coffee", amount=30.0),
    ]
    detail = lambda key: statement_detail(key, day_rows=day_rows, room="350", drinks=drinks, purchases=purchases)

    assert detail("dinners") == "3 meals"
    assert detail("cooked") == "2 nights"
    assert detail("drinks") == "4 beer/soda, 1 wine"
    assert detail("purchases") == "1 purchase"
    assert detail("dues") == ""


def test_statement_detail_is_quiet_when_there_is_nothing_to_count():
    from kitchenpal.ui.day_to_day import statement_detail

    detail = lambda key: statement_detail(key, day_rows=[], room="350", drinks=[], purchases=[])

    assert detail("dinners") == "0 meals"
    assert detail("drinks") == ""
    assert detail("purchases") == ""


def _account_entries():
    from kitchenpal.sheets_service import RoomEntry

    return [
        RoomEntry(label="346", name="Julia", account_row=56, signup_column=9),
        RoomEntry(label="347", name="", account_row=57, signup_column=10),        # room stands empty
        RoomEntry(label="360", name="Sylvester", account_row=70, signup_column=23),
        RoomEntry(label="FL1", name="Gustav", account_row=71, signup_column=24),  # parked, has a name
        RoomEntry(label="FL4", name="", account_row=74, signup_column=27),        # a placeholder
        RoomEntry(label="Spotify", name="Daniel", account_row=76, signup_column=None),
    ]


def test_people_labels_leave_out_empty_slots_and_accounting_rows():
    from kitchenpal.ui.day_to_day import people_labels

    # named FL people stay addable; empty FL slots and Spotify never appear
    assert people_labels(_account_entries()) == ["346", "360", "FL1"]
    assert people_labels(_account_entries(), signup_only=True) == ["346", "360", "FL1"]


def test_resident_labels_are_the_numbered_rooms_someone_lives_in():
    from kitchenpal.ui.day_to_day import resident_labels

    # "Everyone in the house" is rooms 346-360 only: no FL, no empty room
    assert resident_labels(_account_entries()) == ["346", "360"]
