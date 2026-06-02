import streamlit as st

from .config import AppConfig
from .runtime_state import get_cached_service
from .ui.day_to_day import render_drinks_purchases_view, render_host_dinner_view, render_today_view
from .ui.feedback import render_feedback_view
from .ui.month_setup import render_admin_view, render_planning_view


def run_app():
    st.set_page_config(page_title="KitchenPal", layout="wide")

    config = AppConfig()
    service = get_cached_service(config)

    pane = st.sidebar.radio(
        "What do you want to do?",
        ("Today", "Record drinks & purchases", "Host dinner", "Planning", "Admin", "Feedback"),
    )

    if pane == "Today":
        render_today_view(service)
    elif pane == "Record drinks & purchases":
        render_drinks_purchases_view(service)
    elif pane == "Host dinner":
        render_host_dinner_view(service)
    elif pane == "Planning":
        render_planning_view(service)
    elif pane == "Admin":
        render_admin_view(service)
    elif pane == "Feedback":
        render_feedback_view(service)
