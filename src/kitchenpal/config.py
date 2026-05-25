from dataclasses import dataclass, field
import json
import os


def _secret_value(section: str, key: str):
    try:
        import streamlit as st

        if section in st.secrets and key in st.secrets[section]:
            return st.secrets[section][key]
    except Exception:
        return None
    return None


def _config_value(env_key: str, secrets_section: str, secrets_key: str, default: str) -> str:
    return os.getenv(env_key) or _secret_value(secrets_section, secrets_key) or default


def _google_credentials_info() -> dict | None:
    raw_credentials = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if raw_credentials:
        credentials = json.loads(raw_credentials)
    else:
        try:
            import streamlit as st

            credentials = dict(st.secrets["google_service_account"]) if "google_service_account" in st.secrets else None
        except Exception:
            credentials = None

    if credentials and "private_key" in credentials:
        credentials["private_key"] = credentials["private_key"].replace("\\n", "\n")
    return credentials


@dataclass(frozen=True)
class AppConfig:
    credentials_file: str = field(
        default_factory=lambda: _config_value(
            "GOOGLE_CREDENTIALS_FILE",
            "app",
            "credentials_file",
            "koekkenregnskab-3d-ny-040a2ee5b105.json",
        )
    )
    spreadsheet_name: str = field(
        default_factory=lambda: _config_value(
            "KITCHEN_SPREADSHEET_NAME",
            "app",
            "spreadsheet_name",
            "Køkkenregnskab 3D ny",
        )
    )
    template_sheet_name: str = field(
        default_factory=lambda: _config_value("KITCHEN_TEMPLATE_SHEET", "app", "template_sheet_name", "Skabelon")
    )
    google_credentials_info: dict | None = field(default_factory=_google_credentials_info)


GOOGLE_SHEETS_SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
]
