from streamlit.testing.v1 import AppTest

from kitchenpal.sheets_service import RoomEntry
from kitchenpal.ui import identity  # noqa: F401


ROOMS = [
    RoomEntry(label="346", name="Julia", account_row=56, signup_column=9),
    RoomEntry(label="350", name="Josefine", account_row=60, signup_column=13),
    RoomEntry(label="FL1", name="", account_row=71, signup_column=24),
]


def test_default_index_opens_a_selectbox_on_you():
    assert identity.default_index(["346", "350", "FL1"], "350") == 1
    # someone whose room is not in this particular list still gets a usable box
    assert identity.default_index(["346", "350"], "FL1") == 0
    assert identity.default_index([], "350") == 0


def test_display_name_falls_back_to_the_room_number():
    assert identity.display_name(ROOMS, "350") == "Josefine"
    assert identity.display_name(ROOMS, "FL1") == "FL1"
    assert identity.display_name(ROOMS, "999") == "999"


def _room_param(at):
    # AppTest hands query params back as lists
    value = at.query_params.get("room")
    return value[0] if isinstance(value, list) else value


def _identity_app():
    import streamlit as st

    from kitchenpal.sheets_service import RoomEntry
    from kitchenpal.ui.identity import current_room, render_identity_chip, render_room_picker

    rooms = [
        RoomEntry(label="346", name="Julia", account_row=56, signup_column=9),
        RoomEntry(label="350", name="Josefine", account_row=60, signup_column=13),
    ]
    room = current_room(rooms)
    if not room:
        render_room_picker(rooms)
        st.stop()
    render_identity_chip(rooms, room)
    st.write(f"claimed:{room}")


def test_picker_claims_a_room_and_puts_it_in_the_url():
    at = AppTest.from_function(_identity_app).run()

    assert not at.exception
    assert any("Which room are you?" in block.value for block in at.subheader)

    at.button(key="identity_pick_350").click().run()

    assert not at.exception
    assert _room_param(at) == "350"
    assert any("claimed:350" in element.value for element in at.markdown)


def test_a_room_in_the_url_is_recognised_without_asking():
    at = AppTest.from_function(_identity_app)
    at.query_params["room"] = "346"
    at.run()

    assert not at.exception
    assert any("claimed:346" in element.value for element in at.markdown)


def test_an_unknown_room_in_the_url_is_ignored():
    at = AppTest.from_function(_identity_app)
    at.query_params["room"] = "999"
    at.run()

    assert not at.exception
    assert any("Which room are you?" in block.value for block in at.subheader)


def test_the_chip_can_switch_to_another_room():
    at = AppTest.from_function(_identity_app)
    at.query_params["room"] = "350"
    at.run()

    assert any("claimed:350" in element.value for element in at.markdown)

    at.button(key="identity_switch_346").click().run()

    assert not at.exception
    assert _room_param(at) == "346"
    assert any("claimed:346" in element.value for element in at.markdown)


def test_choosing_a_room_shuts_the_panel():
    """Otherwise you have to tap somewhere else to get rid of it. A popover does
    not close because something inside it was clicked, and st.rerun() does not
    close it either — its open state is a widget value, written here before the
    widget is instantiated, which is only possible from a callback."""
    from kitchenpal.ui.identity import ROOM_POPOVER_KEY

    at = AppTest.from_function(_identity_app)
    at.query_params["room"] = "350"
    at.run()
    at.session_state[ROOM_POPOVER_KEY] = True

    at.button(key="identity_switch_346").click().run()

    assert not at.exception
    assert at.session_state[ROOM_POPOVER_KEY] is False
    assert _room_param(at) == "346"


def _cookie_app():
    """The identity screen, with a cookie the browser 'sent' with the request.

    AppTest has no cookie support and st.context needs a real request behind
    it, so the script swaps in a stand-in and puts the real one back — this
    runs in the pytest process, and leaving it would follow every later test.
    """
    import streamlit as st

    from kitchenpal.sheets_service import RoomEntry
    from kitchenpal.ui import identity

    class FakeContext:
        def __init__(self, cookies):
            self._cookies = cookies

        @property
        def cookies(self):
            if self._cookies == "explode":
                raise RuntimeError("no request context")
            return self._cookies

    rooms = [
        RoomEntry(label="346", name="Julia", account_row=56, signup_column=9),
        RoomEntry(label="350", name="Josefine", account_row=60, signup_column=13),
    ]

    written = []
    real_context = st.context
    real_writer = identity._write_room_cookie
    identity._write_room_cookie = lambda value, max_age: written.append((value, max_age))
    cookies = st.session_state.get("cookies", {})
    st.context = FakeContext(cookies) if cookies is not None else real_context
    try:
        room = identity.current_room(rooms)
        if room:
            identity.render_identity_chip(rooms, room)
        st.session_state["claimed"] = room
        st.session_state["written"] = list(written)
    finally:
        st.context = real_context
        identity._write_room_cookie = real_writer


def _run_cookie_app(cookies, **state):
    at = AppTest.from_function(_cookie_app)
    at.session_state["cookies"] = cookies
    for key, value in state.items():
        at.session_state[key] = value
    at.run()
    assert not at.exception, at.exception
    return at


class TestTheBrowserRemembersYou:
    """Residents were re-picking their room on every visit: the claim only
    lived in the URL and in the session, so a bookmark worked and a fresh
    visit did not."""

    def test_a_cookie_answers_the_question_so_nobody_is_asked_again(self):
        at = _run_cookie_app({"kitchenpal_room": "350"})

        assert at.session_state["claimed"] == "350"

    def test_a_shared_link_still_wins_over_the_cookie(self):
        """Otherwise a link somebody sent you would quietly rewrite itself to
        your own room."""
        at = AppTest.from_function(_cookie_app)
        at.session_state["cookies"] = {"kitchenpal_room": "350"}
        at.query_params["room"] = "346"
        at.run()

        assert at.session_state["claimed"] == "346"

    def test_a_room_that_has_left_the_house_is_ignored(self):
        """People move out. A cookie naming a room that is no longer on the
        sheet has to fall back to asking, not to a room nobody lives in."""
        at = _run_cookie_app({"kitchenpal_room": "999"})

        assert at.session_state["claimed"] == ""

    def test_no_cookie_at_all_is_not_an_error(self):
        assert _run_cookie_app({}).session_state["claimed"] == ""

    def test_a_context_that_cannot_be_read_is_not_an_error(self):
        """st.context needs a real request behind it, and a page can render
        without one. Not knowing who you are is a question, never a crash."""
        at = _run_cookie_app("explode")

        assert at.session_state["claimed"] == ""

    def test_the_cookie_is_written_once_per_session(self):
        at = _run_cookie_app({"kitchenpal_room": "350"})

        assert at.session_state["written"] == [("350", identity.ROOM_COOKIE_MAX_AGE)]

        at.run()

        # Already in the browser: rendering the iframe again on every run would
        # cost an element on every page for nothing.
        assert at.session_state["written"] == []
