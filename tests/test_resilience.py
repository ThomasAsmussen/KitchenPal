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
            runtime_state._connect.clear()
            try:
                first = runtime_state.get_cached_service("config")

                # Asking again changes nothing: one connection for the process.
                assert runtime_state.get_cached_service("config") is first

                # Now the deploy: same name, a brand new class object.
                models.RoomEntry = dataclasses.make_dataclass("RoomEntry", ["label"])
                rebuilt = runtime_state.get_cached_service("config")

                st.session_state["built"] = len(built)
                st.session_state["replaced"] = rebuilt is not first
            finally:
                # This runs in the pytest process: leaving either patch in place
                # would hand a fake class to every test that follows, and the
                # cached resource outlives this script.
                runtime_state.SheetsService = real_service
                models.RoomEntry = real_entry
                runtime_state._connect.clear()

        at = AppTest.from_function(script).run()
        assert not at.exception
        assert at.session_state["built"] == 2
        assert at.session_state["replaced"] is True


def _sources_containing(needle: str) -> list[str]:
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src"
    return [
        str(path.relative_to(src))
        for path in src.rglob("*.py")
        if needle in path.read_text()
    ]


def test_no_deprecated_container_width_argument_remains():
    """Streamlit removes use_container_width after 2025-12-31; width= replaced it."""
    assert _sources_containing("use_container_width") == []


def test_no_deprecated_components_html_remains():
    """st.components.v1.html goes after 2026-06-01 and st.iframe replaced it.
    Cloud logs the warning long before the call stops working — that is the
    whole warning we get, so it is worth failing a test over."""
    # the open bracket, so that prose about why it is gone does not trip it
    assert _sources_containing("components.html(") == []
    # declare_component is NOT deprecated: only html and iframe are, and the
    # identity component needs it.
    assert _sources_containing("declare_component") == ["kitchenpal/ui/identity.py"]


class TestBuildingTheConnection:
    """Opening the spreadsheet, and what it costs before a single figure is read."""

    @staticmethod
    def _fake_gspread(monkeypatch):
        """A gspread stand-in that records how the spreadsheet was opened."""
        import kitchenpal.sheets_service as sheets_service

        opened = {"by_key": [], "by_name": [], "requests": 0}

        class FakeHTTPClient:
            def __init__(self):
                self.timeout = None

            def set_timeout(self, timeout):
                self.timeout = timeout

            def request(self, *a, **kw):
                opened["requests"] += 1
                return None

        class FakeClient:
            def __init__(self):
                self.http_client = FakeHTTPClient()

            def open_by_key(self, key):
                opened["by_key"].append(key)
                return f"spreadsheet:{key}"

            def open(self, name):
                opened["by_name"].append(name)
                return f"spreadsheet:{name}"

        client = FakeClient()
        monkeypatch.setattr(sheets_service.gspread, "authorize", lambda creds: client)
        monkeypatch.setattr(
            sheets_service.ServiceAccountCredentials,
            "from_json_keyfile_dict",
            staticmethod(lambda info, scope: "creds"),
        )
        return opened, client

    def _config(self, spreadsheet_id):
        from types import SimpleNamespace

        return SimpleNamespace(
            google_credentials_info={"private_key": "x"},
            credentials_file="",
            spreadsheet_id=spreadsheet_id,
            spreadsheet_name="Køkkenregnskab 3D ny",
            template_sheet_name="Skabelon",
        )

    def test_an_id_opens_the_spreadsheet_without_a_single_request(self, monkeypatch):
        """gspread's open_by_key just wraps the id. Opening by NAME costs two
        round trips instead — a Drive search for a file with that title, then
        the metadata — measured at 850 ms + 415 ms on a cold session."""
        from kitchenpal.sheets_service import SheetsService

        opened, _ = self._fake_gspread(monkeypatch)

        service = SheetsService(self._config("sheet-id-123"))

        assert opened["by_key"] == ["sheet-id-123"]
        assert opened["by_name"] == []
        assert opened["requests"] == 0
        assert service._spreadsheet == "spreadsheet:sheet-id-123"

    def test_without_an_id_it_still_opens_by_name(self, monkeypatch):
        """Production has no id configured until somebody adds one, and the app
        must not stop working while it waits."""
        from kitchenpal.sheets_service import SheetsService

        opened, _ = self._fake_gspread(monkeypatch)

        SheetsService(self._config(""))

        assert opened["by_name"] == ["Køkkenregnskab 3D ny"]
        assert opened["by_key"] == []

    def test_the_connection_is_given_a_timeout(self, monkeypatch):
        """gspread ships with none at all, so a stalled socket waits as long as
        the network allows — and one connection now serves the whole house
        behind a lock, where that stalls everybody's page, not just one."""
        from kitchenpal.sheets_service import REQUEST_TIMEOUT_SECONDS, SheetsService

        _, client = self._fake_gspread(monkeypatch)
        SheetsService(self._config("sheet-id-123"))

        connect, read = REQUEST_TIMEOUT_SECONDS
        assert client.http_client.timeout == (connect, read)
        assert 0 < connect <= 30 and 0 < read <= 60


class TestAStalledNetworkIsNotACrash:
    """A read that timed out says nothing about the sheet, so it is worth
    another go — and it must never reach a resident as a traceback."""

    def test_a_timeout_is_worth_retrying(self):
        import requests

        from kitchenpal.sheets.transient import is_transient

        assert is_transient(requests.exceptions.ReadTimeout("took too long"))
        assert is_transient(requests.exceptions.ConnectTimeout("no answer"))
        assert is_transient(requests.exceptions.ConnectionError("refused"))

    def test_a_read_that_times_out_once_is_tried_again(self):
        import requests

        from kitchenpal.sheets.transient import retry_reads

        attempts = []

        def flaky():
            attempts.append(1)
            if len(attempts) < 2:
                raise requests.exceptions.ReadTimeout("took too long")
            return "the rows"

        assert retry_reads(flaky, delay=0) == "the rows"
        assert len(attempts) == 2

    def test_the_app_shows_a_sentence_rather_than_a_traceback(self):
        """run_app caught gspread's APIError only, so a timeout — which is not
        one — went to the page as a Python traceback."""
        from streamlit.testing.v1 import AppTest

        def script():
            import requests

            from kitchenpal import app

            def boom(config):
                raise requests.exceptions.ReadTimeout("took too long")

            real = app.get_cached_service
            app.get_cached_service = boom
            try:
                app.run_app()
            finally:
                app.get_cached_service = real

        at = AppTest.from_function(script)
        at.run()

        assert not at.exception
        assert any("not answering" in block.value for block in at.error)
        assert at.button(key="kitchenpal_retry")


class TestRetryingHasATimeBudget:
    """Attempts alone are the wrong budget once a timeout counts as transient.
    A read holds the lock st.cache_data puts around a cache miss, so a slow
    retry loop is not one person waiting — it is everybody who wants the same
    figure. Two browsers on one phone froze together on 2026-08-31."""

    def test_a_fast_failure_still_gets_every_attempt(self):
        """A 503 comes back in milliseconds; retrying costs nothing."""
        import gspread

        from kitchenpal.sheets.transient import retry_reads

        attempts = []

        def always_503():
            attempts.append(1)
            raise _api_error(503)

        with pytest.raises(gspread.exceptions.APIError):
            retry_reads(always_503, delay=0)

        assert len(attempts) == 3

    def test_a_slow_failure_is_not_tried_again(self):
        import requests

        from kitchenpal.sheets.transient import retry_reads

        attempts = []

        def slow_stall():
            import time

            attempts.append(1)
            time.sleep(0.05)
            raise requests.exceptions.ReadTimeout("took too long")

        with pytest.raises(requests.exceptions.ReadTimeout):
            retry_reads(slow_stall, delay=0, deadline=0.01)

        # the budget was spent by the first attempt
        assert len(attempts) == 1

    def test_the_default_budget_is_shorter_than_three_timeouts(self):
        from kitchenpal.sheets.transient import RETRY_DEADLINE_SECONDS
        from kitchenpal.sheets_service import REQUEST_TIMEOUT_SECONDS

        _, read_timeout = REQUEST_TIMEOUT_SECONDS
        assert RETRY_DEADLINE_SECONDS < read_timeout * 3
