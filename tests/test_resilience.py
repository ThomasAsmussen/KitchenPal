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

    def test_a_request_waits_for_the_shared_lock(self, monkeypatch):
        """The connection is shared by the whole house now, so the
        requests.Session under gspread is touched from every session's thread.
        Holding the lock elsewhere must hold the request too."""
        import threading

        from kitchenpal.sheets_service import SheetsService

        opened, client = self._fake_gspread(monkeypatch)
        service = SheetsService(self._config("sheet-id-123"))

        started, finished = threading.Event(), threading.Event()

        def call():
            started.set()
            client.http_client.request("get", "anything")
            finished.set()

        worker = threading.Thread(target=call, daemon=True)
        with service._http_lock:
            worker.start()
            assert started.wait(2)
            assert not finished.wait(0.2)
            assert opened["requests"] == 0

        worker.join(2)
        assert finished.is_set()
        assert opened["requests"] == 1
