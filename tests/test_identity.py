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
