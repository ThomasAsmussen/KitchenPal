"""What the app does when Google is unavailable, and when its own code is swapped.

Both of these were found in production on 2026-08-30: four APIError 503s that
each showed a resident a traceback, and one PicklingError that arrived in the
same second as a deploy.
"""
from types import SimpleNamespace

import gspread
import pytest
from streamlit.testing.v1 import AppTest

from kitchenpal.sheets.transient import is_transient, retry_reads, status_code


def _api_error(code: int, message: str = "boom") -> gspread.exceptions.APIError:
    response = SimpleNamespace(
        status_code=code,
        text=message,
        json=lambda: {"error": {"code": code, "message": message, "status": "ERROR"}},
    )
    return gspread.exceptions.APIError(response)


def _unparseable_error(code: int) -> gspread.exceptions.APIError:
    """A proxy's HTML error page: the body is not JSON, so gspread reports -1."""

    def _raise():
        raise ValueError("not json")

    response = SimpleNamespace(status_code=code, text="<html>502</html>", json=_raise)
    return gspread.exceptions.APIError(response)


class TestIsTransient:
    @pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
    def test_a_google_outage_is_worth_retrying(self, code):
        assert is_transient(_api_error(code))

    @pytest.mark.parametrize("code", [400, 403, 404])
    def test_our_own_mistake_is_not(self, code):
        """403 and 404 will still be true in half a second. Retrying only hides them."""
        assert not is_transient(_api_error(code))

    def test_a_plain_exception_is_not_transient(self):
        assert not is_transient(ValueError("nope"))

    def test_the_status_is_read_from_the_response_when_the_body_is_not_json(self):
        exc = _unparseable_error(502)
        assert exc.code == -1
        assert status_code(exc) == 502
        assert is_transient(exc)


class TestRetryReads:
    def test_a_read_that_recovers_returns_its_answer(self):
        calls = []

        def call():
            calls.append(1)
            if len(calls) < 3:
                raise _api_error(503)
            return "the sheet"

        assert retry_reads(call, delay=0) == "the sheet"
        assert len(calls) == 3

    def test_it_gives_up_and_re_raises_the_last_failure(self):
        calls = []

        def call():
            calls.append(1)
            raise _api_error(503)

        with pytest.raises(gspread.exceptions.APIError):
            retry_reads(call, attempts=3, delay=0)
        assert len(calls) == 3

    def test_a_permanent_error_is_raised_on_the_first_try(self):
        calls = []

        def call():
            calls.append(1)
            raise _api_error(403)

        with pytest.raises(gspread.exceptions.APIError):
            retry_reads(call, delay=0)
        assert len(calls) == 1


class TestServiceSurvivesAReload:
    """Community Cloud deploys by deleting our modules from sys.modules and
    re-importing them, WITHOUT restarting the process. st.session_state lives
    through that, so the connection in it belongs to the previous copy of the
    code and mints dataclasses that st.cache_data can no longer pickle."""

    def test_the_connection_is_rebuilt_when_the_classes_change(self):
        def script():
            import dataclasses

            import streamlit as st

            from kitchenpal import runtime_state
            from kitchenpal.sheets import models

            built = []

            class FakeService:
                def __init__(self, config):
                    built.append(config)

            real_service = runtime_state.SheetsService
            real_entry = models.RoomEntry
            runtime_state.SheetsService = FakeService
            try:
                runtime_state.get_cached_service("config")
                first = st.session_state[runtime_state.SERVICE_STATE_KEY]

                # Asking again changes nothing: one connection per session.
                runtime_state.get_cached_service("config")
                assert st.session_state[runtime_state.SERVICE_STATE_KEY] is first

                # Now the deploy: same name, a brand new class object.
                models.RoomEntry = dataclasses.make_dataclass("RoomEntry", ["label"])
                runtime_state.get_cached_service("config")

                st.session_state["built"] = len(built)
                st.session_state["replaced"] = (
                    st.session_state[runtime_state.SERVICE_STATE_KEY] is not first
                )
            finally:
                # This runs in the pytest process: leaving either patch in place
                # would hand a fake class to every test that follows.
                runtime_state.SheetsService = real_service
                models.RoomEntry = real_entry

        at = AppTest.from_function(script).run()
        assert not at.exception
        assert at.session_state["built"] == 2
        assert at.session_state["replaced"] is True


def test_no_deprecated_container_width_argument_remains():
    """Streamlit removes use_container_width after 2025-12-31; width= replaced it."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src"
    offenders = [
        str(path.relative_to(src))
        for path in src.rglob("*.py")
        if "use_container_width" in path.read_text()
    ]
    assert offenders == []
