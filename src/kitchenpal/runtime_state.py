from __future__ import annotations

import streamlit as st

from .config import AppConfig
from .sheets_service import SheetsService


SHEET_CACHE_VERSION_KEY = "kitchenpal_sheet_cache_version"
SERVICE_STATE_KEY = "kitchenpal_sheets_service"


def get_cache_version() -> int:
    return int(st.session_state.get(SHEET_CACHE_VERSION_KEY, 0))


def bump_cache_version() -> int:
    new_version = get_cache_version() + 1
    st.session_state[SHEET_CACHE_VERSION_KEY] = new_version
    return new_version


def cache_key(prefix: str, *parts: object) -> str:
    suffix = ":".join(str(part) for part in parts)
    if suffix:
        return f"{prefix}:{get_cache_version()}:{suffix}"
    return f"{prefix}:{get_cache_version()}"


def get_cached_service(config: AppConfig) -> SheetsService:
    if SERVICE_STATE_KEY not in st.session_state:
        st.session_state[SERVICE_STATE_KEY] = SheetsService(config)
    return st.session_state[SERVICE_STATE_KEY]