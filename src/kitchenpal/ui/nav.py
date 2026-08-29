"""The four-tab bottom bar.

Streamlit's own top navigation collapses into a hamburger on a phone, which is
the hiding this restructure exists to end, so routing is st.navigation(hidden)
and the bar is drawn here: a keyed container pinned with position: fixed.

Three details keep it working on real phones:
  * st.columns stack below ~640px, so the horizontal block is forced back to a
    four-up grid.
  * iOS home indicators eat the bottom of the screen — env(safe-area-inset-*).
  * The on-screen keyboard would shove a fixed bar over the field being typed
    in, so it hides while an input has focus.

The bar is matched with `.st-key-kpalnav` exactly, never `[class*=...]`: the
buttons' own containers are `st-key-kpalnav_dinner` and friends, and a
substring match pins every one of them instead.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from ..runtime_state import bump_cache_version, get_cache_version
from . import data
from .calendar_grid import grid_styles

TABS = [
    ("Dinner", "dinner", ":material/restaurant:"),
    ("Me", "me", ":material/account_circle:"),
    ("Plan", "plan", ":material/calendar_month:"),
    ("House", "house", ":material/holiday_village:"),
]


def _theme_is_dark() -> bool:
    theme = getattr(getattr(st, "context", None), "theme", None)
    return getattr(theme, "type", "light") == "dark"


def page_styles(active_slug: str) -> str:
    dark = _theme_is_dark()
    bar_bg = "#141B1A" if dark else "#FFFFFF"
    line = "rgba(255,255,255,.14)" if dark else "rgba(20,32,30,.13)"
    idle = "#8B9895" if dark else "#6C7A77"
    active = "#6ECFC2" if dark else "#0E514C"
    hover = "rgba(110,207,194,.14)" if dark else "rgba(14,81,76,.09)"
    shadow = "0 -2px 18px rgba(0,0,0,.45)" if dark else "0 -2px 14px rgba(20,32,30,.08)"
    bad = "#E28A7C" if dark else "#A33A2C"

    grid = grid_styles(dark)

    return f"""
<style>
  [data-testid="stMainBlockContainer"] {{
    padding-bottom: calc(5.6rem + env(safe-area-inset-bottom)) !important;
  }}

  /* Streamlit's header is 60px tall, absolutely positioned and painted over the
     page. Below 400px Streamlit itself drops the main container's top padding to
     2.2rem — 35px — so the first thing on every screen, the identity chip, loses
     its ascenders behind the header. Measured, not guessed: the chip's top sat
     at y=51 under a header ending at y=60.

     Their rule uses this exact selector and !important, so an identical
     selector only ties and loses on order. Hence the extra ancestor: specificity
     is the only way to win, and it must stay ahead of theirs. */
  @media (max-width: 400px) {{
    [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] {{
      padding-top: 4.5rem !important;
    }}
  }}

  /* Streamlit Community Cloud floats its own badge in the bottom-right corner,
     exactly over the House tab. Its class names are hashed and change between
     Cloud releases, so this casts wide: the known test ids, anything whose class
     mentions a badge or the manage button, and any element appended straight to
     <body>. That last one is safe here — with a dialog and a popover open, this
     app's <body> still holds only <noscript> and <div id="root">, because
     Streamlit portals inside its own root. */
  [data-testid="stStatusWidget"],
  [data-testid="manage-app-button"],
  [data-testid="stAppViewBadge"],
  [class*="viewerBadge"],
  [class*="_viewerBadge"],
  [class*="_profileContainer"],
  [class*="_manageAppButton"],
  [class*="_terminalButton"],
  body > div:not(#root):not([data-testid]) {{
    display: none !important;
  }}

  .kp-kicker {{
    font-size: .68rem;
    letter-spacing: .12em;
    text-transform: uppercase;
    color: {idle};
  }}
  .kp-dish {{
    font-size: 1.3rem;
    font-weight: 700;
    line-height: 1.25;
    margin: .2rem 0 .35rem;
  }}
  .kp-note {{ color: {idle}; font-variant-numeric: tabular-nums; }}
  /* amounts stay on one line; the label beside them is what wraps */
  .kp-line .kp-note {{ white-space: nowrap; }}
  .kp-money {{
    font-size: 2rem;
    font-weight: 700;
    letter-spacing: -.02em;
    line-height: 1.15;
    font-variant-numeric: tabular-nums;
    margin: .15rem 0 .1rem;
  }}
  .kp-line {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: .75rem;
    padding: .5rem 0;
    border-bottom: 1px solid {line};
    font-size: .95rem;
  }}
  .kp-line > span:first-child {{ min-width: 0; }}
  .kp-past {{ opacity: .55; }}
  .kp-owed {{ color: {bad} !important; }}
  .kp-credit {{ color: {idle} !important; }}
  .kp-clamp {{
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }}
  .kp-sub {{
    display: block;
    font-size: .78rem;
    color: {idle};
    margin-top: .05rem;
    line-height: 1.3;
  }}
  .kp-money.kp-small {{ font-size: 1.45rem; margin: .1rem 0 .35rem; }}
  /* ledger rows: the text fills the line, the pencil sits at its end */
  /* a long name must wrap inside the line, never push the pencil off it */
  [class*="st-key-kpalrow_"] {{ gap: .25rem; flex-wrap: nowrap !important; }}
  [class*="st-key-kpalrow_"] > [data-testid="stElementContainer"]:first-child {{
    flex: 1 1 auto !important;
    min-width: 0;
  }}
  [class*="st-key-kpalrow_"] > [data-testid="stElementContainer"]:last-child {{ flex: 0 0 auto !important; }}
  [class*="st-key-kpalrow_"] .kp-line {{ padding: .4rem 0; }}
  /* Me lists a handful of your own rows — hairlines there would be noise */
  [class*="st-key-kpalrow_my_"] .kp-line {{ border-bottom: 0; padding: .35rem 0; }}

  /* the three add buttons on Me sit on one row, never stacked */
  .st-key-kpaladd {{ gap: .4rem; }}
  .st-key-kpaladd button p {{ font-size: .85rem !important; }}
  .kp-mine {{ font-weight: 600; }}

{grid}
  .st-key-kpalnav {{
    position: fixed;
    left: 0; right: 0; bottom: 0;
    /* the top of the stack: a badge we failed to hide must still lose */
    z-index: 2147483647;
    background: {bar_bg};
    border-top: 1px solid {line};
    box-shadow: {shadow};
    padding: .25rem max(.35rem, env(safe-area-inset-left))
             calc(.25rem + env(safe-area-inset-bottom))
             max(.35rem, env(safe-area-inset-right));
  }}

  .st-key-kpalnav [data-testid="stHorizontalBlock"] {{
    display: grid !important;
    grid-template-columns: repeat({len(TABS)}, minmax(0, 1fr)) !important;
    gap: .1rem !important;
    max-width: 46rem;
    margin: 0 auto;
    flex-wrap: nowrap !important;
  }}
  .st-key-kpalnav [data-testid="stColumn"] {{
    width: auto !important; min-width: 0 !important; flex: unset !important;
  }}
  .st-key-kpalnav [data-testid="stColumn"] > div {{ position: relative; }}

  .st-key-kpalnav button {{
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    gap: .1rem !important;
    min-height: 52px;
    padding: .3rem .1rem !important;
    border: none !important;
    background: transparent !important;
    color: {idle} !important;
    border-radius: 10px !important;
  }}
  /* button markup is button > div > span > (icon span + markdown div): the row
     that has to become a column is the inner span, not the button. */
  .st-key-kpalnav button > div,
  .st-key-kpalnav button > div > span {{
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    gap: .12rem !important;
    width: 100% !important;
    min-width: 0 !important;
  }}
  .st-key-kpalnav button p {{
    font-size: .7rem !important;
    line-height: 1.1 !important;
    font-weight: 500 !important;
    margin: 0 !important;
    white-space: nowrap;
  }}
  .st-key-kpalnav button span[data-testid="stIconMaterial"] {{
    font-size: 1.32rem !important;
    width: 1.32rem !important;
    height: 1.32rem !important;
    margin: 0 !important;
  }}
  .st-key-kpalnav button:hover,
  .st-key-kpalnav button:focus-visible {{
    color: {active} !important;
    background: {hover} !important;
  }}

  .st-key-kpalnav_{active_slug} button {{ color: {active} !important; }}
  .st-key-kpalnav_{active_slug} button p {{ font-weight: 600 !important; }}
  .st-key-kpalnav_{active_slug} button::before {{
    content: "";
    position: absolute;
    top: 0;
    left: 50%;
    transform: translateX(-50%);
    width: 26px;
    height: 3px;
    border-radius: 0 0 3px 3px;
    background: {active};
  }}

  /* landscape: a 61px bar would eat a sixth of the screen */
  @media (max-height: 460px) {{
    .st-key-kpalnav button {{ min-height: 40px; }}
    .st-key-kpalnav button p {{ display: none !important; }}
    [data-testid="stMainBlockContainer"] {{
      padding-bottom: calc(3.8rem + env(safe-area-inset-bottom)) !important;
    }}
  }}

  /* the identity popover trigger: quiet, one line, tappable */
  [data-testid="stPopover"] > div > button {{
    border: none !important;
    background: transparent !important;
    color: {idle} !important;
    font-size: .82rem !important;
    padding: 0 !important;
    min-height: 0 !important;
  }}

  /* on a small phone the primary action has to stay above the fold */
  @media (max-width: 400px) {{
    [data-testid="stMainBlockContainer"] h1 {{ font-size: 2.1rem !important; padding-top: .2rem !important; }}
    [data-testid="stMainBlockContainer"] {{ padding-top: 2.2rem !important; }}
  }}

  /* the smallest phones still in use, and folded ones */
  @media (max-width: 344px) {{
    .st-key-kpalnav button p {{ font-size: .62rem !important; }}
    .st-key-kpalnav button span[data-testid="stIconMaterial"] {{
      font-size: 1.15rem !important; width: 1.15rem !important; height: 1.15rem !important;
    }}
  }}

  /* the keyboard would push the bar over the field being typed in */
  body:has(input:focus, textarea:focus) .st-key-kpalnav {{ display: none !important; }}

  @media (prefers-reduced-motion: no-preference) {{
    .st-key-kpalnav button {{ transition: color .12s ease, background .12s ease; }}
  }}
</style>
"""


def render_bottom_nav(active_slug: str, page_by_slug: dict) -> None:
    with st.container(key="kpalnav"):
        columns = st.columns(len(TABS), gap=None)
        for column, (title, slug, icon) in zip(columns, TABS):
            with column:
                clicked = st.button(
                    title,
                    key=f"kpalnav_{slug}",
                    icon=icon,
                    use_container_width=True,
                )
                if clicked and slug != active_slug and slug in page_by_slug:
                    st.switch_page(page_by_slug[slug])


def render_refresh_footer() -> None:
    """One refresh for the whole app, at the end of the page instead of the top."""
    loaded_at_key = f"kitchenpal_loaded_at:{get_cache_version()}"
    if loaded_at_key not in st.session_state:
        st.session_state[loaded_at_key] = datetime.now(ZoneInfo("Europe/Copenhagen")).strftime("%H:%M")

    st.divider()
    left, right = st.columns([1, 3], vertical_alignment="center")
    if left.button("Refresh data", key="kitchenpal_refresh", use_container_width=True):
        data.clear_everything()
        bump_cache_version()
        st.rerun()
    right.caption(f"Loaded from the spreadsheet at {st.session_state[loaded_at_key]}.")
