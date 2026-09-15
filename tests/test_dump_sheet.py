from types import SimpleNamespace

from tools.dump_sheet import _open_spreadsheet


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
