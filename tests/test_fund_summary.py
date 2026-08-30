"""What the kitchen fund is worth, on House.

The sheet's own STATUS box computes it; the app names the parts and must not
recompute them. The one thing the app DOES decide is how to print the parts so
they add up on screen — the sheet's total is bank + cash MINUS the residents'
combined balance, which is negative while the house owes money.
"""
import pytest

from kitchenpal.sheets.utils import find_fund_status


def _block(residents="-kr 3.046,86", bank="kr 4.104,08", cash="kr 0,00", total="kr 7.150,94"):
    return [
        ["STATUS"],
        ["Brugernes samlede saldo hos køkkenkassen", "", "", "", residents],
        ["Bankkonto", "", "", "", bank],
        ["Kontantbeholdning", "", "", "", cash],
        ["Køkkenkassen I alt", "", "", "", total],
    ]


class TestReadingTheStatusBox:
    def test_the_four_figures_come_back_with_the_sheets_own_signs(self):
        assert find_fund_status(_block()) == {
            "bank": 4104.08,
            "cash": 0.0,
            "residents": -3046.86,
            "total": 7150.94,
        }

    def test_the_parts_add_up_to_the_sheets_total(self):
        """Pinned because it is the whole reason the residents' line is turned
        around on screen: bank + cash - residents == total."""
        found = find_fund_status(_block())

        assert round(found["bank"] + found["cash"] - found["residents"], 2) == found["total"]

    def test_the_total_row_is_not_mistaken_for_the_bank_row(self):
        """"Bankkonto" and "Køkkenkassen I alt" both have to match on their own
        words, or the fund's worth is reported as its cash."""
        found = find_fund_status(_block())

        assert found["bank"] == 4104.08 and found["total"] == 7150.94

    def test_a_block_without_a_bank_or_a_total_reports_nothing(self):
        """A house that reworded its sheet should see the rest of the app work
        rather than a wrong number."""
        assert find_fund_status([["STATUS"], ["Kontantbeholdning", "", "", "", "kr 5,00"]]) is None

    def test_a_missing_cash_row_is_zero_not_a_failure(self):
        found = find_fund_status(
            [["Bankkonto", "", "", "", "kr 10,00"], ["Køkkenkassen I alt", "", "", "", "kr 10,00"]]
        )

        assert found["cash"] == 0.0 and found["residents"] == 0.0

    @pytest.mark.parametrize("rows", [[], None, [[""], [None]]])
    def test_an_empty_block_reports_nothing(self, rows):
        assert find_fund_status(rows) is None


def _summary_script():
    def script():
        import streamlit as st

        from kitchenpal.sheets_service import KitchenFundStatus
        from kitchenpal.ui.house import render_fund_summary

        class Stub:
            def get_kitchen_fund_status(self, worksheet_name):
                figures = st.session_state["figures"]
                return None if figures is None else KitchenFundStatus(**figures)

        render_fund_summary(Stub(), "August 2026")

    return script


def _run(figures):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_function(_summary_script())
    at.session_state["figures"] = figures
    at.run()
    assert not at.exception
    return " ".join(block.value for block in at.markdown)


class TestTheCard:
    def test_it_shows_the_total_and_the_parts_that_make_it(self):
        text = _run({"bank": 4104.08, "cash": 0.0, "residents": -3046.86, "total": 7150.94})

        assert "7150.94 DKK" in text
        assert "In the bank" in text and "4104.08 DKK" in text
        # Turned around to face the fund: money the house owes is money coming in,
        # so the two printed parts add to the printed total.
        assert "Owed by the house" in text and "3046.86 DKK" in text
        assert "-3046.86" not in text

    def test_cash_is_left_out_when_there_is_none(self):
        text = _run({"bank": 4104.08, "cash": 0.0, "residents": -3046.86, "total": 7150.94})

        assert "Cash" not in text

    def test_cash_is_shown_when_the_house_holds_some(self):
        text = _run({"bank": 100.0, "cash": 50.0, "residents": 0.0, "total": 150.0})

        assert "Cash" in text and "50.00 DKK" in text

    def test_it_turns_around_when_the_fund_owes_the_house(self):
        text = _run({"bank": 5000.0, "cash": 0.0, "residents": 1200.0, "total": 3800.0})

        assert "Owed to the house" in text
        assert "less what it owes the house" in text

    def test_it_says_so_when_everyone_is_square(self):
        text = _run({"bank": 5000.0, "cash": 0.0, "residents": 0.0, "total": 5000.0})

        assert "nobody owes anybody" in text
        assert "Owed" not in text

    def test_nothing_is_drawn_when_the_sheet_has_no_status_box(self):
        assert _run(None) == ""
