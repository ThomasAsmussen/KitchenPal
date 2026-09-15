import importlib.util
from types import SimpleNamespace
from pathlib import Path


_SPEC = importlib.util.spec_from_file_location("dump_sheet", Path(__file__).parents[1] / "tools" / "dump_sheet.py")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
_open_spreadsheet = _MODULE._open_spreadsheet


class FakeClient:
    def __init__(self):
        self.calls = []

    def open_by_key(self, spreadsheet_id):
        self.calls.append(("open_by_key", spreadsheet_id))
        return "by-id"

    def open(self, spreadsheet_name):
        self.calls.append(("open", spreadsheet_name))
        return "by-name"


def test_open_spreadsheet_prefers_id():
    client = FakeClient()
    config = SimpleNamespace(spreadsheet_id="dev-id", spreadsheet_name="KitchenPal DEV")

    assert _open_spreadsheet(client, config) == "by-id"
    assert client.calls == [("open_by_key", "dev-id")]


def test_open_spreadsheet_falls_back_to_name():
    client = FakeClient()
    config = SimpleNamespace(spreadsheet_id="", spreadsheet_name="KitchenPal DEV")

    assert _open_spreadsheet(client, config) == "by-name"
    assert client.calls == [("open", "KitchenPal DEV")]
