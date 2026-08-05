from streamlit.testing.v1 import AppTest

def test_app_loads():
    at = AppTest.from_file("streamlit_app.py", default_timeout=30).run()
    assert not at.exception
