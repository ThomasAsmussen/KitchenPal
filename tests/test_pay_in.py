"""Where to send money to the kitchen fund.

Me answered "what do you owe" and then stopped; the account number was only in
the spreadsheet, which is the thing the app exists to spare people from opening.
"""
import pytest

from kitchenpal.sheets.utils import find_bank_details, parse_bank_details
from kitchenpal.ui.day_to_day import _danish_amount, _transfer_message


STATUS_BLOCK = [
    "STATUS",
    "Brugernes samlede saldo hos køkkenkassen",
    "Bankkonto",
    "Kontantbeholdning",
    "Køkkenkassen I alt",
    "",
    "",
    "REG.NR: 0400 KONTONR.: 4032345684",
]


class TestParsing:
    def test_the_line_the_sheet_actually_holds(self):
        assert parse_bank_details("REG.NR: 0400 KONTONR.: 4032345684") == (
            "0400", "4032345684", "REG.NR: 0400 KONTONR.: 4032345684",
        )

    def test_an_account_number_written_in_groups(self):
        reg, account, _ = parse_bank_details("Reg. nr. 0400  Kontonr. 4032 34 56 84")
        assert (reg, account) == ("0400", "4032345684")

    def test_english_labels_are_read_too(self):
        reg, account, _ = parse_bank_details("Reg no 0400, account number 4032345684")
        assert (reg, account) == ("0400", "4032345684")

    @pytest.mark.parametrize(
        "line", ["Ask Thomas", "Account no 12345", "4032345684"],
    )
    def test_a_line_it_cannot_split_comes_back_whole(self, line):
        """Half a guess is worse than none: a resident typing a wrong account
        number into a bank app has no way back. The raw line is still correct."""
        reg, account, text = parse_bank_details(line)
        assert (reg, account) == ("", "")
        assert text == line

    @pytest.mark.parametrize("blank", ["", "   ", None])
    def test_nothing_at_all_is_not_an_error(self, blank):
        """A house that has not filled the cell in should see the app work."""
        assert parse_bank_details(blank) is None


class TestFindingItInTheBlock:
    def test_the_bank_line_is_picked_out_of_the_status_box(self):
        assert find_bank_details(STATUS_BLOCK)[0:2] == ("0400", "4032345684")

    def test_bankkonto_is_a_label_and_not_somewhere_to_send_money(self):
        """It is the fund's own figure, and it would match a looser pattern."""
        assert find_bank_details(["STATUS", "Bankkonto", "Kontantbeholdning"]) is None

    def test_a_block_with_no_bank_line_finds_nothing(self):
        assert find_bank_details(["STATUS", "", ""]) is None

    def test_an_unsplittable_line_is_still_found_and_returned_whole(self):
        found = find_bank_details(["STATUS", "Bankkonto", "Konto 4032 34 56 84 hos Danske"])
        assert found is not None
        assert found[2] == "Konto 4032 34 56 84 hos Danske"


class TestWhatGoesInTheTransfer:
    def test_the_amount_carries_a_decimal_comma(self):
        """It is pasted into a Danish banking app, which expects a comma."""
        assert _danish_amount(115.1) == "115,10"
        assert _danish_amount(1234.5) == "1234,50"

    def test_the_message_is_the_room_then_the_first_name(self):
        """The room is what the accounts are keyed on; the name is what a human
        recognises reading down a bank statement."""
        assert _transfer_message("354", "Philip Andersen") == "354 Philip"

    def test_the_room_alone_when_there_is_no_name(self):
        assert _transfer_message("FL2", "") == "FL2"


def _card_script():
    def script():
        from types import SimpleNamespace

        import streamlit as st

        from kitchenpal.ui.day_to_day import DayToDayContext, render_transfer_card

        class Stub:
            def get_kitchen_fund_bank_details(self, worksheet_name):
                return st.session_state["bank"]

        context = DayToDayContext(
            selected_sheet_name="August 2026",
            room_entries=[],
            signup_room_entries=[],
            room_name_by_label={},
            room_labels=[],
            signup_room_labels=[],
        )
        statement = SimpleNamespace(
            label="354", name="Philip Andersen", balance=st.session_state["balance"], components={}
        )
        render_transfer_card(Stub(), context, statement, "354")
        from kitchenpal.ui.day_to_day import take_armed_transfer

        st.session_state["returned"] = take_armed_transfer()

    return script


def _bank():
    from kitchenpal.sheets_service import BankDetails

    return BankDetails("0400", "4032345684", "REG.NR: 0400 KONTONR.: 4032345684")


def _run_card(balance, bank=None):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_function(_card_script())
    at.session_state["balance"] = balance
    at.session_state["bank"] = bank if bank is not None else _bank()
    at.run()
    assert not at.exception
    return at


class TestWhenTheCardAppears:
    def test_it_shows_what_a_transfer_needs_when_you_owe_a_lot(self):
        at = _run_card(-1306.73)

        values = [block.value for block in at.code]
        assert values == ["1306,73", "0400", "4032345684", "354 Philip"]
        assert at.button(key="kpal_transferred")

    def test_nothing_for_the_dip_everyone_lives_in(self):
        """Dues on the 1st and one dinner put most people slightly under. A card
        that appears the day after somebody eats is one people scroll past."""
        at = _run_card(-115.10)

        assert len(at.code) == 0

    def test_the_threshold_itself_is_not_enough(self):
        assert len(_run_card(-500.0).code) == 0
        assert len(_run_card(-500.01).code) == 3 + 1

    def test_nothing_when_the_fund_owes_you(self):
        at = _run_card(495.99)

        assert len(at.code) == 0

    @pytest.mark.parametrize("balance", [495.99, -115.10, 0.0])
    def test_a_card_that_is_not_drawn_records_nothing(self, balance):
        """The reported bug: the card returned `float | None` while its early
        returns still said `return False`, and `False is not None`. Every run
        that did NOT draw the card opened the payment dialog — switching to
        anyone in credit did it."""
        assert _run_card(balance).session_state["returned"] is None

    def test_nothing_when_the_sheet_has_no_account_on_it(self):
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_function(_card_script())
        at.session_state["balance"] = -1306.73
        at.session_state["bank"] = None
        at.run()

        assert not at.exception
        assert len(at.code) == 0

    def test_a_line_it_could_not_split_is_shown_whole(self):
        from kitchenpal.sheets_service import BankDetails

        at = _run_card(-1306.73, BankDetails("", "", "Ask Thomas, reg 0400"))

        assert [block.value for block in at.code] == [
            "1306,73", "Ask Thomas, reg 0400", "354 Philip",
        ]


class TestChangingTheAmount:
    """Paying part of a big balance is a normal thing to do."""

    def test_it_starts_at_everything_you_owe(self):
        at = _run_card(-1306.73)

        assert at.number_input[0].value == 1306.73

    def test_what_you_type_is_what_you_copy(self):
        at = _run_card(-1306.73)

        at.number_input[0].set_value(1000.0).run()

        assert at.code[0].value == "1000,00"

    def test_the_recorded_payment_is_the_amount_you_chose(self):
        at = _run_card(-1306.73)
        at.number_input[0].set_value(1000.0).run()

        at.button(key="kpal_transferred").click().run()

        assert at.session_state["returned"] == 1000.0

    def test_nothing_is_recorded_until_the_button_is_pressed(self):
        at = _run_card(-1306.73)

        assert at.session_state["returned"] is None
