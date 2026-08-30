from __future__ import annotations

import importlib

import streamlit as st

from .config import AppConfig
from .sheets_service import SheetsService


SHEET_CACHE_VERSION_KEY = "kitchenpal_sheet_cache_version"
SERVICE_STATE_KEY = "kitchenpal_sheets_service"
SERVICE_CODE_KEY = "kitchenpal_service_code"


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


def _live_model_class():
    """The RoomEntry class that pickle would resolve the name to, right now.

    Deliberately looked up through sys.modules rather than imported at the top
    of this file, because that lookup IS what pickle does — so the comparison
    below cannot drift away from the thing it is testing.
    """
    return importlib.import_module("kitchenpal.sheets.models").RoomEntry


def get_cached_service(config: AppConfig) -> SheetsService:
    """The connection, rebuilt when the code underneath it has been replaced.

    Community Cloud does not restart the process when it deploys: Streamlit's
    watcher deletes every one of our modules from sys.modules and the next run
    re-imports the lot. st.session_state survives that, so the SheetsService
    living in it belongs to the OLD code and keeps handing out dataclasses
    stamped with the OLD classes. st.cache_data then pickles one, checks that
    the name still points at the same class object, finds it does not, and the
    resident gets a traceback:

        PicklingError: Can't pickle <class '...RoomEntry'>:
        it's not the same object as kitchenpal.sheets.models.RoomEntry

    So: keep the class the service was built against, and when it is no longer
    the class in memory, throw the service away. Costs one API call, once, to
    whoever happened to be mid-session during a deploy.
    """
    live = _live_model_class()
    if st.session_state.get(SERVICE_CODE_KEY) is not live:
        st.session_state.pop(SERVICE_STATE_KEY, None)

    if SERVICE_STATE_KEY not in st.session_state:
        st.session_state[SERVICE_STATE_KEY] = SheetsService(config)
        st.session_state[SERVICE_CODE_KEY] = live
    return st.session_state[SERVICE_STATE_KEY]