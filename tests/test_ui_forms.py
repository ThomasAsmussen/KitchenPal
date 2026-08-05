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
