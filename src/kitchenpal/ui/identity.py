"""Who is using the app.

The app asks once which room you are and remembers it in the address of the
page, so a bookmark on a phone keeps working. It is a claim, not a login —
exactly like the Log's `By` column — so nothing is locked to it: anyone can
change rooms, and every form still shows the room it will write to.
"""
from __future__ import annotations

import streamlit as st

ROOM_QUERY_PARAM = "room"
ROOM_STATE_KEY = "kitchenpal_room"


def _known_labels(room_entries) -> list[str]:
    return [entry.label for entry in room_entries]


def current_room(room_entries) -> str:
    """The room this browser has claimed, or "" when nobody has said yet."""
    labels = _known_labels(room_entries)
    from_url = str(st.query_params.get(ROOM_QUERY_PARAM) or "").strip()
    if from_url in labels:
        st.session_state[ROOM_STATE_KEY] = from_url

    claimed = str(st.session_state.get(ROOM_STATE_KEY) or "").strip()
    if claimed not in labels:
        return ""

    # st.switch_page drops the query string, so put the room back on every run:
    # a shared link, or a refresh on another tab, still knows who you are.
    if str(st.query_params.get(ROOM_QUERY_PARAM) or "") != claimed:
        st.query_params[ROOM_QUERY_PARAM] = claimed
    return claimed


def set_room(label: str) -> None:
    st.session_state[ROOM_STATE_KEY] = label
    st.query_params[ROOM_QUERY_PARAM] = label


def clear_room() -> None:
    st.session_state.pop(ROOM_STATE_KEY, None)
    if ROOM_QUERY_PARAM in st.query_params:
        del st.query_params[ROOM_QUERY_PARAM]


def display_name(room_entries, room: str) -> str:
    for entry in room_entries:
        if entry.label == room:
            return entry.name or entry.label
    return room


def default_index(labels: list[str], room: str, fallback: int = 0) -> int:
    """Where a room selectbox should open: on you, when you are in the list."""
    if room in labels:
        return labels.index(room)
    return fallback


def render_room_picker(room_entries) -> None:
    st.subheader("Which room are you?")
    st.caption("Pick once. It stays in the address of this page, so a bookmark remembers you.")
    for entry in room_entries:
        label = f"{entry.label} — {entry.name}" if entry.name else entry.label
        if st.button(label, key=f"identity_pick_{entry.label}", use_container_width=True):
            set_room(entry.label)
            st.rerun()


def render_identity_chip(room_entries, room: str) -> None:
    """One compact line: who the app thinks you are, and a tap to change it.

    A popover rather than a label plus a button — on a phone that pair costs two
    rows and never lines up.
    """
    name = display_name(room_entries, room)
    label = f"You are {room}" + (f" · {name}" if name and name != room else "")
    with st.popover(label, use_container_width=False):
        st.caption("Tap your room to switch. Nothing is locked to it.")
        for entry in room_entries:
            entry_label = f"{entry.label} — {entry.name}" if entry.name else entry.label
            if st.button(entry_label, key=f"identity_switch_{entry.label}", use_container_width=True):
                set_room(entry.label)
                st.rerun()
