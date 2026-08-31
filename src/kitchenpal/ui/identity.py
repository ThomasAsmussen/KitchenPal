"""Who is using the app.

The app asks once which room you are and then stops asking: the claim goes in
the address of the page, so a shared link carries it, AND in a cookie, so
opening the app fresh still knows you. It is a claim, not a login — exactly
like the Log's `By` column — so nothing is locked to it: anyone can change
rooms, and every form still shows the room it will write to.
"""
from __future__ import annotations

import json
import pathlib

import streamlit as st
import streamlit.components.v1 as components

ROOM_QUERY_PARAM = "room"
ROOM_STATE_KEY = "kitchenpal_room"
ROOM_COOKIE = "kitchenpal_room"
# A year. The claim is a room label, not a credential, and a house changes
# rooms about once a term — anything shorter just asks the question again.
ROOM_COOKIE_MAX_AGE = 60 * 60 * 24 * 365
COOKIE_WRITTEN_KEY = "kitchenpal_room_remembered"


def _known_labels(room_entries) -> list[str]:
    return [entry.label for entry in room_entries]


def _room_from_cookie(labels: list[str]) -> str:
    """What the browser said it was, last time it was here.

    st.context.cookies holds what came with THIS session's opening request, so
    it answers "who was this browser before", never "what did we just write".
    Every read is defensive: no cookie, an unreadable context and a room that
    has since left the house all mean the same thing — ask.
    """
    try:
        remembered = str(st.context.cookies.get(ROOM_COOKIE) or "").strip()
    except Exception:  # noqa: BLE001 - no context at all is just "we do not know"
        return ""
    return remembered if remembered in labels else ""


def current_room(room_entries) -> str:
    """The room this browser has claimed, or "" when nobody has said yet.

    Three places it can come from, in this order: the address of the page, this
    session, and the cookie. The URL comes FIRST so that a link somebody shared
    still shows you their room rather than quietly rewriting itself to yours.
    """
    labels = _known_labels(room_entries)
    from_url = str(st.query_params.get(ROOM_QUERY_PARAM) or "").strip()
    if from_url in labels:
        st.session_state[ROOM_STATE_KEY] = from_url

    claimed = str(st.session_state.get(ROOM_STATE_KEY) or "").strip()
    if claimed not in labels:
        claimed = _room_from_cookie(labels)
        if claimed:
            st.session_state[ROOM_STATE_KEY] = claimed
    if claimed not in labels:
        return ""

    # st.switch_page drops the query string, so put the room back on every run:
    # a shared link, or a refresh on another tab, still knows who you are.
    if str(st.query_params.get(ROOM_QUERY_PARAM) or "") != claimed:
        st.query_params[ROOM_QUERY_PARAM] = claimed
    return claimed


ROOM_STORAGE_KEY = "kitchenpal_room"
REDIRECT_TRIED_KEY = "kitchenpal_room_redirected"


def _browser_script(body: str) -> None:
    """Run a little JavaScript in the page, invisibly.

    Streamlit strips <script> out of st.markdown, so the only way to reach the
    browser is a component iframe. Streamlit sandboxes those with
    allow-same-origin — measured on the running app — so it shares the app's
    origin and can touch the app document's storage and address. height=0, and
    measured at zero: it costs nothing on the page.
    """
    components.html(f"<script>{body}</script>", height=0)


def _write_room_cookie(value: str, max_age: int) -> None:
    """Remember the room in the browser, two ways, because one is not enough.

    The COOKIE is the quiet one: st.context.cookies lets the server read it
    straight out of the next request, so the app simply knows who you are and
    nothing else happens. But the server can only READ cookies — Streamlit has
    no way to set one — so the write has to happen out here, and out here is
    where it can be refused. Community Cloud serves the app inside an iframe on
    its own host page; a Lax cookie is not sent with a cross-site frame, so on
    https it is written SameSite=None; Secure, and a browser blocking
    third-party cookies drops it regardless of what we ask for.

    LOCAL STORAGE is the loud one, and it is the fallback: nothing on the
    server can see it, so the page has to put the room back into its own
    address before Python gets a look (see _restore_room_from_storage). That
    costs one reload, which is why it is the second choice and not the first.

    What is stored is a room number. Identity here is a claim with nothing
    locked to it, so neither of these gives anything away.
    """
    cookie = f"{ROOM_COOKIE}={value}; path=/; max-age={max_age}"
    _browser_script(
        f"var base = {json.dumps(cookie)};"
        'var https = location.protocol === "https:";'
        'try { document.cookie = base + (https ? "; SameSite=None; Secure" : "; SameSite=Lax"); }'
        "catch (e) {}"
        f"try {{ var s = window.parent.localStorage; var v = {json.dumps(value)};"
        f"  if (v) {{ s.setItem({json.dumps(ROOM_STORAGE_KEY)}, v); }}"
        f"  else {{ s.removeItem({json.dumps(ROOM_STORAGE_KEY)}); }}"
        f"  window.parent.sessionStorage.removeItem({json.dumps(REDIRECT_TRIED_KEY)}); }}"
        "catch (e) {}"
    )


_COMPONENT_DIR = pathlib.Path(__file__).parent / "identity_component"
_ask_the_browser = components.declare_component("kitchenpal_identity", path=str(_COMPONENT_DIR))


def room_from_storage(labels: list[str]) -> str:
    """Ask the BROWSER what it remembers, when the request did not say.

    A declared component is the only thing that can answer back: Streamlit
    sandboxes component iframes without allow-top-navigation, so nothing in
    there can put the room in the address and reload, and nothing in there can
    reach the server on its own. Its value arrives on the run after it renders,
    which costs one rerun and no reload — nobody sees it.

    Drawn only on the screen that is about to ask, so a visit that already
    knows who you are pays nothing for it.
    """
    try:
        remembered = str(_ask_the_browser(key="kitchenpal_identity_probe") or "").strip()
    except Exception:  # noqa: BLE001 - a component that will not load is just "we do not know"
        return ""
    return remembered if remembered in labels else ""


def remember_room(room: str) -> None:
    """Keep the claim in the browser, so opening the app does not ask again.

    Once per session per room: it is already in the browser after the first
    write, and re-rendering the iframe on every run would cost an element on
    every page for nothing. Writing it again when this session ADOPTED a stored
    room is deliberate, though — it pushes the expiry a year out from the last
    visit rather than from whenever the room was first picked.
    """
    if not room or st.session_state.get(COOKIE_WRITTEN_KEY) == room:
        return
    st.session_state[COOKIE_WRITTEN_KEY] = room
    _write_room_cookie(room, ROOM_COOKIE_MAX_AGE)


def set_room(label: str) -> None:
    st.session_state[ROOM_STATE_KEY] = label
    st.query_params[ROOM_QUERY_PARAM] = label


def clear_room() -> None:
    st.session_state.pop(ROOM_STATE_KEY, None)
    st.session_state.pop(COOKIE_WRITTEN_KEY, None)
    if ROOM_QUERY_PARAM in st.query_params:
        del st.query_params[ROOM_QUERY_PARAM]
    # max-age=0 is how a browser is told to drop one.
    _write_room_cookie("", 0)


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
    """Ask — but only after the browser has had its chance to answer."""
    remembered = room_from_storage(_known_labels(room_entries))
    if remembered:
        set_room(remembered)
        st.rerun()

    st.subheader("Which room are you?")
    st.caption("Pick once. This browser remembers you, so the app opens as you next time.")
    for entry in room_entries:
        label = f"{entry.label} — {entry.name}" if entry.name else entry.label
        if st.button(label, key=f"identity_pick_{entry.label}", width="stretch"):
            set_room(entry.label)
            st.rerun()


ROOM_POPOVER_KEY = "kitchenpal_identity_open"


def _switch_room(label: str) -> None:
    """Take the room and shut the panel, both before the script body runs.

    A popover does not close because something inside it was clicked, and
    st.rerun() does not close it either: its open state is a WIDGET VALUE, so
    the only way to shut it from here is to write False to that value — and a
    widget value may only be written before the widget is instantiated. An
    on_click callback is exactly that moment, which is why this is a callback
    and not the body of an `if st.button(...)`.
    """
    set_room(label)
    st.session_state[ROOM_POPOVER_KEY] = False


def render_identity_chip(room_entries, room: str) -> None:
    """One compact line: who the app thinks you are, and a tap to change it.

    A popover rather than a label plus a button — on a phone that pair costs two
    rows and never lines up. It is given on_change because that is what makes it
    stateful (is_stateful = on_change != "ignore" in Streamlit's own layouts.py);
    without it the open state lives only in the browser and nothing here can
    reach it.
    """
    remember_room(room)
    name = display_name(room_entries, room)
    label = f"You are {room}" + (f" · {name}" if name and name != room else "")
    with st.popover(label, width="content", key=ROOM_POPOVER_KEY, on_change="rerun"):
        st.caption("Tap your room to switch. Nothing is locked to it.")
        for entry in room_entries:
            entry_label = f"{entry.label} — {entry.name}" if entry.name else entry.label
            st.button(
                entry_label,
                key=f"identity_switch_{entry.label}",
                width="stretch",
                on_click=_switch_room,
                args=(entry.label,),
            )
