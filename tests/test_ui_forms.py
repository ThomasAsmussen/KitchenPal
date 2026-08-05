from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Block


def _form_blocks(node):
    if isinstance(node, Block):
        proto = getattr(node, "proto", None)
        if proto is not None and proto.WhichOneof("type") == "form":
            yield proto.form
    for child in getattr(node, "children", {}).values():
        yield from _form_blocks(child)


def _feedback_form_app():
    import streamlit as st

    from kitchenpal.ui.feedback import FEEDBACK_SECTIONS, render_feedback_form

    class StubService:
        def add_feedback_entry(self, feedback_type, name, title, details):
            st.session_state["stub_added"] = (feedback_type, name, title, details)
            return None

    render_feedback_form(StubService(), "bug", FEEDBACK_SECTIONS["bug"])


def test_feedback_form_clears_fields_after_submit():
    # clear_on_submit is applied by the frontend, so AppTest cannot observe the
    # cleared values directly; assert the form requests it and the submit still
    # reaches the service with the entered values.
    at = AppTest.from_function(_feedback_form_app).run()

    forms = list(_form_blocks(at._tree))
    assert len(forms) == 1
    assert forms[0].clear_on_submit

    at.text_input(key="bug_name").input("Julia")
    at.text_input(key="bug_title").input("Broken thing")
    at.text_area(key="bug_details").input("It broke when I clicked save.")
    at.button[0].click().run()

    assert not at.exception
    assert at.session_state["stub_added"] == ("bug", "Julia", "Broken thing", "It broke when I clicked save.")


def _purchases_app():
    from types import SimpleNamespace

    import streamlit as st

    from kitchenpal.ui.day_to_day import _render_purchases_section

    class StubService:
        def add_purchase(self, worksheet_name, room_number, purchase_date, item, cost):
            st.session_state["stub_purchase"] = ("add", item, cost)

        def update_purchase(self, worksheet_name, row_number, room_number, purchase_date, item, cost):
            st.session_state["stub_purchase"] = ("update", item, cost)

    existing = st.session_state.get("app_existing_purchases", [])
    context = SimpleNamespace(
        selected_sheet_name="June 2026",
        room_labels=["346"],
        room_name_by_label={"346": "Julia"},
        month_entries=SimpleNamespace(purchases=list(existing)),
    )
    _render_purchases_section(StubService(), context)


def test_purchase_form_accepts_negative_amount_for_deposit_refund():
    at = AppTest.from_function(_purchases_app).run()

    at.text_input(key="purchase_item").input("Pant retur")
    at.number_input(key="purchase_cost").set_value(-25.0)
    at.button[0].click().run()

    assert not at.exception
    assert not at.error
    assert at.session_state["stub_purchase"][1:] == ("Pant retur", -25.0)


def _month_setup_app():
    from types import SimpleNamespace

    import streamlit as st

    from kitchenpal.ui.month_setup import render_month_creation_section

    class StubService:
        def create_month_sheet(self, month_name, year):
            pass

        def copy_balances_from_previous_month(self, month_name, year):
            st.session_state["stub_copied"] = (month_name, year)
            return SimpleNamespace(
                chased=st.session_state.get("stub_chased", []),
                unplaced=st.session_state.get("stub_unplaced", []),
                suspected_renames=st.session_state.get("stub_renames", []),
                duplicate_names=st.session_state.get("stub_duplicates", []),
            )

    render_month_creation_section(StubService())


def test_copy_balances_controls_react_outside_a_form():
    # Widgets inside st.form do not rerun the script until submit, so an
    # in-form confirmation checkbox can never re-enable a submit button that
    # was rendered disabled — the flow deadlocks. These controls must be
    # regular reactive widgets.
    at = AppTest.from_function(_month_setup_app).run()

    assert at.selectbox(key="update_month").form_id == ""
    assert at.selectbox(key="update_year").form_id == ""
    assert at.checkbox(key="confirm_copy_balances").form_id == ""


def test_copy_balances_label_names_source_month_with_year_rollover():
    at = AppTest.from_function(_month_setup_app).run()

    at.selectbox(key="update_month").select("January")
    at.selectbox(key="update_year").select(2027).run()

    label = at.checkbox(key="confirm_copy_balances").label
    assert "January 2027" in label
    assert "December 2026" in label


def test_copy_balances_ui_surfaces_the_report():
    at = AppTest.from_function(_month_setup_app)
    at.session_state["stub_chased"] = [("Alberte", -150.0, "FL5")]
    at.session_state["stub_unplaced"] = [("Asta", -201.0)]
    at.session_state["stub_renames"] = [("352", "Asta", "Astaa")]
    at.run()

    at.selectbox(key="update_month").select("February").run()
    at.checkbox(key="confirm_copy_balances").check().run()
    at.button(key="copy_balances_button").click().run()

    assert not at.exception
    info_text = " ".join(block.value for block in at.info)
    warning_text = " ".join(block.value for block in at.warning)
    assert "Alberte" in info_text and "FL5" in info_text
    assert "Asta" in warning_text and "-201.00" in warning_text
    assert "Astaa" in warning_text


def test_copy_balances_button_runs_copy_after_confirmation():
    at = AppTest.from_function(_month_setup_app).run()

    at.selectbox(key="update_month").select("July").run()
    at.checkbox(key="confirm_copy_balances").check().run()
    at.button(key="copy_balances_button").click().run()

    assert not at.exception
    assert at.session_state["stub_copied"] == ("July", 2026)


def test_purchase_edit_form_prefills_negative_amount():
    from types import SimpleNamespace

    entry = SimpleNamespace(row_number=29, room="346", item="Pant retur", date="2026-06-03", amount=-14.0)
    at = AppTest.from_function(_purchases_app)
    at.session_state["app_existing_purchases"] = [entry]
    at.run()

    assert not at.exception
    assert at.number_input(key="edit_purchase_cost_29").value == -14.0
