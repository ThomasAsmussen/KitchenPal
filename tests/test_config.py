import sys
from types import SimpleNamespace

from kitchenpal import config


def test_app_config_reads_google_credentials_json_env(monkeypatch):
    monkeypatch.setenv(
        "GOOGLE_CREDENTIALS_JSON",
        '{"type":"service_account","private_key":"line1\\\\nline2","client_email":"kitchen@example.com"}',
    )

    app_config = config.AppConfig()

    assert app_config.google_credentials_info["client_email"] == "kitchen@example.com"
    assert app_config.google_credentials_info["private_key"] == "line1\nline2"


def test_app_config_reads_streamlit_secrets(monkeypatch):
    fake_streamlit = SimpleNamespace(
        secrets={
            "app": {
                "spreadsheet_name": "KitchenPal Sheet",
                "template_sheet_name": "Template Sheet",
            },
            "google_service_account": {
                "type": "service_account",
                "private_key": "line1\\nline2",
                "client_email": "kitchen@example.com",
            },
        }
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)
    monkeypatch.delenv("GOOGLE_CREDENTIALS_JSON", raising=False)
    monkeypatch.delenv("KITCHEN_SPREADSHEET_NAME", raising=False)
    monkeypatch.delenv("KITCHEN_TEMPLATE_SHEET", raising=False)

    app_config = config.AppConfig()

    assert app_config.spreadsheet_name == "KitchenPal Sheet"
    assert app_config.template_sheet_name == "Template Sheet"
    assert app_config.google_credentials_info["private_key"] == "line1\nline2"
