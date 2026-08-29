import streamlit as st

from .config import AppConfig
from .runtime_state import get_cached_service
from .ui.day_to_day import (
    identity_room_entries,
    render_dinner_view,
    render_me_view,
)
from .ui.house import render_house_view
from .ui.identity import current_room, render_identity_chip, render_room_picker
from .ui.plan import render_planning_view
from .ui.nav import page_styles, render_bottom_nav, render_refresh_footer
from .ui.rollover import render_status_banner, turn_if_due


def _chrome(service, slug: str, title: str):
    """Everything every page wears: styles, who you are, and the page's name."""
    st.markdown(page_styles(slug), unsafe_allow_html=True)

    # Streamlit has no scheduler, so the month turns on the first page load on
    # or after the 1st. It is free once it has run, and it has to happen before
    # identity, which reads the very sheet it may be about to create.
    turn_if_due(service)

    room_entries = identity_room_entries(service)
    room = current_room(room_entries)
    if room_entries and not room:
        render_room_picker(room_entries)
        st.stop()

    if room:
        render_identity_chip(room_entries, room)
    if title:
        st.title(title)
    render_status_banner(service, room)
    return room


def _page(service, slug: str, title: str, render):
    def run():
        _chrome(service, slug, title)
        render(service)
        render_refresh_footer()

    return run


def _dinner_page(service):
    render_dinner_view(service)


def _me_page(service):
    render_me_view(service)


def _plan_page(service):
    render_planning_view(service)


def _house_page(service):
    render_house_view(service)


def _build_pages(service) -> dict:
    """Our own slug -> page map.

    Never key this on StreamlitPage.url_path: the default page reports "" there,
    so a nav built from url_path can switch away from Dinner but never back.
    """
    return {
        "dinner": st.Page(_page(service, "dinner", "", _dinner_page), title="Dinner", url_path="dinner", default=True),
        "me": st.Page(_page(service, "me", "Me", _me_page), title="Me", url_path="me"),
        "plan": st.Page(_page(service, "plan", "Plan", _plan_page), title="Plan", url_path="plan"),
        "house": st.Page(_page(service, "house", "House", _house_page), title="House", url_path="house"),
    }


def _active_slug(page_by_slug: dict, page) -> str:
    # st.navigation returns one of the pages it was given, so identity is enough
    # — and unlike .title it works before the page has run.
    for slug, candidate in page_by_slug.items():
        if candidate is page:
            return slug
    return next(iter(page_by_slug))


def run_app():
    st.set_page_config(
        page_title="KitchenPal",
        layout="centered",
        initial_sidebar_state="collapsed",
    )

    config = AppConfig()
    service = get_cached_service(config)

    # position="hidden" keeps one real URL per tab — bookmarkable, and the back
    # button works — while the visible tabs are drawn as a bottom bar, which
    # Streamlit's own navigation cannot do on a phone.
    page_by_slug = _build_pages(service)
    page = st.navigation(list(page_by_slug.values()), position="hidden")
    page.run()
    render_bottom_nav(_active_slug(page_by_slug, page), page_by_slug)
