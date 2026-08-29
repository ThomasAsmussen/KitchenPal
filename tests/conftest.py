from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


import pytest
import streamlit as st


@pytest.fixture(autouse=True)
def _clear_streamlit_caches():
    """ui/data.py hides the service from the cache key, so a stub's reads would
    otherwise be served to the next test that asks for the same month."""
    st.cache_data.clear()
    yield
    st.cache_data.clear()
