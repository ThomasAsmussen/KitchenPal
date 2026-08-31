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


def test_the_bar_is_drawn_before_the_page_runs(monkeypatch):
    """Otherwise a tab click pays for a full re-run of the page you are LEAVING.

    st.button reports the click on the run that FOLLOWS it, and st.switch_page
    raises immediately — so whatever is drawn before the bar has already run by
    the time the app learns you wanted to go somewhere else. Measured on the
    real app with the month caches expired: 2.2s spent re-reading the page
    being left, against 15ms once the bar came first.
    """
    order = []

    class FakePage:
        def run(self):
            order.append("page")

    page = FakePage()
    monkeypatch.setattr(app.st, "set_page_config", lambda **kw: None)
    monkeypatch.setattr(app, "AppConfig", lambda: object())
    monkeypatch.setattr(app, "get_cached_service", lambda config: object())
    monkeypatch.setattr(app, "_build_pages", lambda service: {"dinner": page})
    monkeypatch.setattr(app.st, "navigation", lambda pages, **kw: page)
    monkeypatch.setattr(app, "render_bottom_nav", lambda *a, **kw: order.append("nav"))

    app.run_app()

    assert order == ["nav", "page"]
