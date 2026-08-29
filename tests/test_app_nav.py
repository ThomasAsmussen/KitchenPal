import streamlit as st

from kitchenpal import app
from kitchenpal.ui.nav import TABS


def _noop():
    return None


def test_the_default_page_reports_an_empty_url_path():
    # The trap the bottom bar fell into: the default page's url_path is "", so a
    # nav keyed on url_path can leave Dinner but never come back to it.
    default_page = st.Page(_noop, title="Dinner", url_path="dinner", default=True)

    assert default_page.url_path == ""


def test_every_tab_in_the_bar_can_be_switched_to():
    page_by_slug = app._build_pages(service=None)

    # one page per tab in the bar, keyed by the same slug the bar uses
    assert list(page_by_slug) == [slug for _, slug, _ in TABS]


def test_active_slug_finds_the_running_page_including_the_default_one():
    page_by_slug = app._build_pages(service=None)

    for slug, page in page_by_slug.items():
        assert app._active_slug(page_by_slug, page) == slug
