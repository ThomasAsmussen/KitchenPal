from __future__ import annotations

import importlib

import streamlit as st

from .config import AppConfig
from .sheets_service import SheetsService


SHEET_CACHE_VERSION_KEY = "kitchenpal_sheet_cache_version"


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


@st.cache_resource(show_spinner=False)
def _connect(_config: AppConfig) -> SheetsService:
    """One connection for the whole house, built once per process.

    _config is underscored so Streamlit does not try to hash it: it carries the
    service-account dict, which is not hashable, and there is only ever one
    configuration anyway.

    The service is stamped with the RoomEntry class it was built against, so
    get_cached_service can tell when the code underneath it has been replaced.
    """
    service = SheetsService(_config)
    service.model_class = _live_model_class()
    return service


def get_cached_service(config: AppConfig) -> SheetsService:
    """The connection, shared across sessions and rebuilt after a deploy.

    SHARED, because it used to live in st.session_state and that is per browser
    session: every resident, and every new tab, paid to build their own. Traced
    against a warm process, a second session made exactly two HTTP calls before
    it could show anything — a Drive lookup and a metadata fetch, 1.2 s — and
    then read every figure from st.cache_data, which was already shared. So the
    entire cold start of everybody after the first was connection setup that
    the house had already done. st.cache_resource is process-wide, which is
    what it was always meant to be. Being shared, it is also touched from every
    session's thread — gspread's AuthorizedSession is built for that, and
    SheetsService gives it a timeout so one stalled call cannot hold up the
    house.

    REBUILT, because Community Cloud does not restart the process when it
    deploys: Streamlit's watcher deletes every one of our modules from
    sys.modules and the next run re-imports the lot. A cached resource is keyed
    by the function, and that key survives the re-import — so the service
    handed back belongs to the OLD code and keeps minting dataclasses stamped
    with the OLD classes. st.cache_data then pickles one, checks that the name
    still points at the same class object, finds it does not, and the resident
    gets a traceback:

        PicklingError: Can't pickle <class '...RoomEntry'>:
        it's not the same object as kitchenpal.sheets.models.RoomEntry

    So: keep the class the service was built against, and when it is no longer
    the class in memory, throw the connection away and build another. Costs one
    rebuild, once, to whoever happens to be mid-session during a deploy.
    """
    service = _connect(config)
    if getattr(service, "model_class", None) is not _live_model_class():
        _connect.clear()
        service = _connect(config)
    return service
