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

    from kitchenpal.ui.day_to_day import add_purchase_form

    class StubService:
        def add_purchase(self, worksheet_name, room_number, purchase_date, item, cost):
            st.session_state["stub_purchase"] = ("add", item, cost)

        def update_purchase(self, worksheet_name, row_number, room_number, purchase_date, item, cost):
            st.session_state["stub_purchase"] = ("update", item, cost)

    existing = st.session_state.get("app_existing_purchases", [])
    context = SimpleNamespace(
        selected_sheet_name="June 2026",
        room_entries=[],
        room_labels=["346"],
        room_name_by_label={"346": "Julia"},
        month_entries=SimpleNamespace(purchases=list(existing)),
    )
    add_purchase_form(StubService(), context, "346")


def test_purchase_form_accepts_negative_amount_for_deposit_refund():
    at = AppTest.from_function(_purchases_app).run()

    # no "who paid" question: the form acts as the room the app already knows
    assert not at.selectbox
    at.text_input(key="purchase_item").input("Pant retur")
    at.number_input(key="purchase_cost").set_value(-25.0)
    at.button[0].click().run()

    assert not at.exception
    assert not at.error
    assert at.session_state["stub_purchase"][1:] == ("Pant retur", -25.0)


def _purchase_ledger_app():
    # AppTest ships only this function's own source, so it builds its world inline.
    from types import SimpleNamespace

    import streamlit as st

    class StubService:
        def update_purchase(self, worksheet_name, row_number, room_number, purchase_date, item, cost):
            st.session_state["stub_purchase"] = ("update", item, cost)

        def delete_purchase(self, worksheet_name, row_number):
            st.session_state["stub_purchase"] = ("delete", row_number)

    context = SimpleNamespace(
        selected_sheet_name="June 2026",
        room_entries=[],
        room_labels=["346"],
        room_name_by_label={"346": "Julia"},
        month_entries=SimpleNamespace(purchases=list(st.session_state.get("app_existing_purchases", []))),
    )

    from kitchenpal.ui.day_to_day import render_purchase_ledger

    render_purchase_ledger(StubService(), context)


def _purchase_dialog_app():
    # AppTest ships only this function's own source, so it builds its world inline.
    from types import SimpleNamespace

    import streamlit as st

    class StubService:
        def update_purchase(self, worksheet_name, row_number, room_number, purchase_date, item, cost):
            st.session_state["stub_purchase"] = ("update", item, cost)

        def delete_purchase(self, worksheet_name, row_number):
            st.session_state["stub_purchase"] = ("delete", row_number)

    context = SimpleNamespace(
        selected_sheet_name="June 2026",
        room_entries=[],
        room_labels=["346"],
        room_name_by_label={"346": "Julia"},
        month_entries=SimpleNamespace(purchases=list(st.session_state.get("app_existing_purchases", []))),
    )

    from kitchenpal.ui.day_to_day import _edit_purchase_dialog

    _edit_purchase_dialog(StubService(), context, context.month_entries.purchases[0], True)


def _pant_entry():
    from types import SimpleNamespace

    return SimpleNamespace(row_number=29, room="346", item="Pant retur", date="2026-06-03", amount=-14.0)


def test_purchase_ledger_lists_the_row_with_an_edit_button():
    at = AppTest.from_function(_purchase_ledger_app)
    at.session_state["app_existing_purchases"] = [_pant_entry()]
    at.run()

    assert not at.exception
    assert any("Pant retur" in element.value for element in at.markdown)
    assert at.button(key="edit_purchase_29")


def test_purchase_edit_dialog_prefills_negative_amount():
    at = AppTest.from_function(_purchase_dialog_app)
    at.session_state["app_existing_purchases"] = [_pant_entry()]
    at.run()

    assert not at.exception
    assert at.number_input(key="edit_purchase_cost_29").value == -14.0


def test_purchase_delete_asks_before_it_deletes():
    at = AppTest.from_function(_purchase_dialog_app)
    at.session_state["app_existing_purchases"] = [_pant_entry()]
    at.run()

    at.button(key="arm_delete_purchase_29").click().run()
    assert "stub_purchase" not in at.session_state
    assert at.warning

    at.button(key="confirm_delete_purchase_29").click().run()
    assert at.session_state["stub_purchase"] == ("delete", 29)
