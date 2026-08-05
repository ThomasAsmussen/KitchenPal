import os
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "streamlit_app.py"
HAS_CREDS = (ROOT / ".streamlit" / "secrets.toml").exists() or bool(
    os.environ.get("GOOGLE_CREDENTIALS_JSON")
)


@pytest.mark.skipif(not HAS_CREDS, reason="needs Sheets credentials; local only")
def test_app_loads():
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not at.exception
