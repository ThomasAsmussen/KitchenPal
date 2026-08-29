from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from ..runtime_state import bump_cache_version, cache_key, get_cache_version
from ..sheets_service import SheetsService
from . import data
from .errors import show_user_error


FEEDBACK_SECTIONS = {
    "feature": {
        "title": "Suggested new features",
        "active_title": "Open suggestions",
        "done_title": "Done suggestions",
        "empty": "No suggested features yet.",
        "done_empty": "No completed suggestions yet.",
        "success": "Feature suggestion added.",
        "form_key": "new_feature_form",
        "done_button": "Mark done",
        "done_status": "Done",
    },
    "bug": {
        "title": "Bugs",
        "active_title": "Open bugs",
        "done_title": "Fixed bugs",
        "empty": "No bugs reported yet.",
        "done_empty": "No fixed bugs yet.",
        "success": "Bug report added.",
        "form_key": "new_bug_form",
        "done_button": "Mark fixed",
        "done_status": "Fixed",
    },
}


def render_feedback_view(service: SheetsService):

    feature_tab, bug_tab = st.tabs([FEEDBACK_SECTIONS["feature"]["title"], FEEDBACK_SECTIONS["bug"]["title"]])

    with feature_tab:
        render_feedback_section(service, "feature")

    with bug_tab:
        render_feedback_section(service, "bug")


def render_feedback_section(service: SheetsService, feedback_type: str):
    config = FEEDBACK_SECTIONS[feedback_type]
    entries = data.feedback_entries(service, feedback_type)
    active_entries = [entry for entry in entries if entry.status.lower() not in ("done", "fixed")]
    done_entries = [entry for entry in entries if entry.status.lower() in ("done", "fixed")]

    st.subheader(config["title"])
    render_feedback_form(service, feedback_type, config)
    render_feedback_entries(
        service=service,
        feedback_type=feedback_type,
        entries=active_entries,
        title=config["active_title"],
        empty_message=config["empty"],
        action_label=config["done_button"],
        action="done",
    )
    render_feedback_entries(
        service=service,
        feedback_type=feedback_type,
        entries=done_entries,
        title=config["done_title"],
        empty_message=config["done_empty"],
        action_label="Delete",
        action="delete",
    )


def render_feedback_form(service: SheetsService, feedback_type: str, config: dict):
    with st.form(key=config["form_key"], clear_on_submit=True):
        name = st.text_input("Your name", key=f"{feedback_type}_name")
        title = st.text_input("Short title", key=f"{feedback_type}_title")
        details = st.text_area(
            "What were you trying to do, and what happened?",
            key=f"{feedback_type}_details",
        )

        if st.form_submit_button("Add"):
            if not title.strip() or not details.strip():
                st.error("Add a title and details before submitting.")
                return
            try:
                service.add_feedback_entry(feedback_type, name, title, details)
                data.clear_feedback()
                bump_cache_version()
                st.success(config["success"])
                st.rerun()
            except ValueError as exc:
                show_user_error(st, exc, f"Could not add {config['title'].lower()}")


def render_feedback_entries(
    service: SheetsService,
    feedback_type: str,
    entries,
    title: str,
    empty_message: str,
    action_label: str,
    action: str,
):
    st.markdown(f"**{title}**")
    if not entries:
        st.caption(empty_message)
        return

    for entry in entries:
        label = f"{entry.title} — {entry.name} · {entry.created_at}"
        with st.expander(label):
            st.write(entry.details)
            if st.button(action_label, key=f"feedback_{feedback_type}_{action}_{entry.row_number}"):
                try:
                    if action == "done":
                        service.mark_feedback_entry_done(feedback_type, entry.row_number)
                    elif action == "delete":
                        service.delete_feedback_entry(feedback_type, entry.row_number)
                    data.clear_feedback()
                    bump_cache_version()
                    st.rerun()
                except ValueError as exc:
                    show_user_error(st, exc, "Could not update feedback")
