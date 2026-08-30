"""A month as seven columns, drawn the same way wherever it appears.

Plan and Dinner both want a month you can tap. Keeping one grid here means one
set of styles, and those styles live in nav.page_styles, which every page emits
— the whole reason the first calendar was invisible on phones was that its
stylesheet was written but never put on a page.

st.columns stacks below ~640px, so the seven columns are forced into a grid at
every width. The state of a day rides on its wrapper container's key, which
leaves the button's own key stable across a change of state.
"""
from __future__ import annotations

import calendar

import streamlit as st

from .month_setup import ENGLISH_WEEKDAY_NAMES, _weekday_label


def render_grid(
    *,
    key: str,
    year: int,
    month: int,
    day_state,
    day_label=None,
    on_click=None,
    args_for=None,
    disabled: bool = False,
) -> None:
    """day_state(day) -> a state name, or "" for a day that cannot be tapped."""
    with st.container(key=f"kpalcal_{key}"):
        header = st.columns(7)
        for index, weekday in enumerate(ENGLISH_WEEKDAY_NAMES):
            header[index].markdown(
                f"<div class='kpal-weekday'>{_weekday_label(weekday)}</div>", unsafe_allow_html=True
            )

        for week in calendar.Calendar(firstweekday=0).monthdayscalendar(year, month):
            columns = st.columns(7)
            for index, day in enumerate(week):
                with columns[index]:
                    if day == 0:
                        st.markdown("<div class='kpal-blank'></div>", unsafe_allow_html=True)
                        continue
                    state = day_state(day)
                    if not state:
                        st.markdown(f"<div class='kpal-off'>{day}</div>", unsafe_allow_html=True)
                        continue
                    label = day_label(day) if day_label else str(day)
                    with st.container(key=f"kpalday_{state}_{key}_{day}"):
                        st.button(
                            label,
                            key=f"{key}_day_{day}",
                            width="stretch",
                            disabled=disabled,
                            on_click=on_click,
                            args=args_for(day) if args_for else None,
                        )


def render_static_grid(*, year: int, month: int, day_state) -> None:
    """The same month, read-only: plain HTML rather than 31 dead buttons.

    An answer you have already given is a picture, not a form. Drawing it as
    markup keeps the colours honest (a disabled Streamlit button greys its own
    text) and drops thirty-one widgets from a screen that only has to be read.
    """
    cells = [f"<div class='kpal-s-wd'>{_weekday_label(name)}</div>" for name in ENGLISH_WEEKDAY_NAMES]
    for week in calendar.Calendar(firstweekday=0).monthdayscalendar(year, month):
        for day in week:
            if day == 0:
                cells.append("<div class='kpal-s-blank'></div>")
                continue
            state = day_state(day)
            if not state:
                cells.append(f"<div class='kpal-s-day kpal-s-off'>{day}</div>")
                continue
            cells.append(f"<div class='kpal-s-day kpal-s-{state}'>{day}</div>")
    st.markdown(f"<div class='kpal-static'>{''.join(cells)}</div>", unsafe_allow_html=True)


def grid_styles(dark: bool) -> str:
    line = "rgba(255,255,255,.14)" if dark else "rgba(20,32,30,.13)"
    muted = "#8B9895" if dark else "#6C7A77"
    ink = "#E9EFED" if dark else "#14201E"
    can_bg = "rgba(110,207,194,.16)" if dark else "rgba(14,81,76,.10)"
    cant_bg = "rgba(226,138,124,.18)" if dark else "rgba(163,58,44,.11)"
    cant_ink = "#E28A7C" if dark else "#A33A2C"
    pref_bg = "rgba(224,182,94,.22)" if dark else "rgba(180,128,31,.18)"
    pref_ink = "#E0B65E" if dark else "#8A6014"
    mine_bg = "#6ECFC2" if dark else "#0E514C"
    mine_ink = "#101614" if dark else "#FFFFFF"

    return f"""
  /* Seven across at every width: st.columns stacks below ~640px, which once
     turned the calendar into a 5,600px column of checkboxes. */
  [class*="st-key-kpalcal_"] [data-testid="stHorizontalBlock"] {{
    display: grid !important;
    grid-template-columns: repeat(7, minmax(0, 1fr)) !important;
    gap: .22rem !important;
    flex-wrap: nowrap !important;
  }}
  [class*="st-key-kpalcal_"] [data-testid="stColumn"] {{
    width: auto !important; min-width: 0 !important; flex: unset !important;
  }}
  .kpal-weekday {{
    text-align: center; font-size: .64rem; font-weight: 600;
    letter-spacing: .04em; color: {muted}; padding-bottom: .1rem;
  }}
  .kpal-blank {{ min-height: 2.4rem; }}
  .kpal-off {{
    min-height: 2.4rem; display: flex; align-items: center; justify-content: center;
    font-size: .8rem; color: {muted}; opacity: .4; font-variant-numeric: tabular-nums;
  }}
  [class*="st-key-kpalday_"] button {{
    min-height: 2.4rem; padding: .1rem !important;
    border: 1px solid {line} !important; border-radius: 8px !important;
  }}
  [class*="st-key-kpalday_"] button p {{
    font-size: .8rem !important; font-variant-numeric: tabular-nums;
    line-height: 1.1; color: {ink};
  }}
  [class*="st-key-kpalday_can_"] button {{ background: {can_bg} !important; border-color: transparent !important; }}
  [class*="st-key-kpalday_cant_"] button {{ background: {cant_bg} !important; border-color: transparent !important; }}
  [class*="st-key-kpalday_cant_"] button p {{ color: {cant_ink} !important; text-decoration: line-through; }}
  [class*="st-key-kpalday_pref_"] button {{ background: {pref_bg} !important; border-color: transparent !important; }}
  [class*="st-key-kpalday_pref_"] button p {{ color: {pref_ink} !important; font-weight: 600; }}
  /* Dinner: the night you are cooking, and the day you are looking at. */
  [class*="st-key-kpalday_mine_"] button {{ background: {mine_bg} !important; border-color: transparent !important; }}
  [class*="st-key-kpalday_mine_"] button p {{ color: {mine_ink} !important; font-weight: 600; }}
  [class*="st-key-kpalday_cook_"] button {{ background: {can_bg} !important; border-color: transparent !important; }}
  /* "free" keeps the plain outline — a night nobody has taken. */
  [class*="st-key-kpalday_here_"] button {{ border-color: {mine_bg} !important; border-width: 2px !important; }}
  [class*="st-key-kpalday_here_"] button p {{ font-weight: 600; }}

  /* the read-only month: same colours, no widgets */
  .kpal-static {{
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    gap: .22rem;
    margin: .2rem 0 .1rem;
    /* square cells would balloon to 100px on a desktop column */
    max-width: 23rem;
  }}
  .kpal-s-wd {{
    text-align: center; font-size: .64rem; font-weight: 600;
    letter-spacing: .04em; color: {muted}; padding-bottom: .1rem;
  }}
  .kpal-s-blank {{ aspect-ratio: 1 / 1; }}
  .kpal-s-day {{
    aspect-ratio: 1 / 1;
    display: flex; align-items: center; justify-content: center;
    border: 1px solid {line}; border-radius: 8px;
    font-size: .8rem; font-variant-numeric: tabular-nums; color: {ink};
  }}
  .kpal-s-off {{ border-color: transparent; color: {muted}; opacity: .4; }}
  .kpal-s-can {{ background: {can_bg}; border-color: transparent; }}
  .kpal-s-cant {{
    background: {cant_bg}; border-color: transparent;
    color: {cant_ink}; text-decoration: line-through;
  }}
  .kpal-s-pref {{ background: {pref_bg}; border-color: transparent; color: {pref_ink}; font-weight: 600; }}

  .kpal-legend {{
    display: flex; flex-wrap: wrap; gap: .4rem .9rem;
    margin: .6rem 0 .2rem; font-size: .76rem; color: {muted};
  }}
  .kpal-legend span {{ display: inline-flex; align-items: center; gap: .3rem; }}
  .kpal-sw {{ width: .85rem; height: .85rem; border-radius: 4px; display: inline-block; }}
  .kpal-sw-can {{ background: {can_bg}; }}
  .kpal-sw-cant {{ background: {cant_bg}; }}
  .kpal-sw-pref {{ background: {pref_bg}; }}
  .kpal-sw-mine {{ background: {mine_bg}; }}
  .kpal-sw-off {{ border: 1px solid {line}; }}
"""
