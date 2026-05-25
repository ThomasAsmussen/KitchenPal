import streamlit as st

from .config import AppConfig
from .runtime_state import get_cached_service
from .ui.day_to_day import render_day_to_day_view
from .ui.feedback import render_feedback_view
from .ui.month_setup import render_month_setup_view


def run_app():
    st.set_page_config(page_title="KitchenPal", layout="wide")

    config = AppConfig()
    service = get_cached_service(config)

    pane = st.sidebar.radio("Choose purpose", ("Day to day", "Create new month", "Feedback"))

    if pane == "Day to day":
        render_day_to_day_view(service)
    elif pane == "Create new month":
        render_month_setup_view(service)
    else:
        render_feedback_view(service)
