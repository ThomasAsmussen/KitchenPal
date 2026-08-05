# Dev loop

- Start app: `./run-dev.sh` (port 8501, logs to /tmp/streamlit.log)
- Streamlit hot-reloads on save. Only re-run run-dev.sh if imports change or the process died.
- After ANY change: `tail -50 /tmp/streamlit.log` and check for exceptions.
- After any UI change: load http://localhost:8501 in the browser and verify visually before saying it works.

# Data

- Backend is a Google Sheet. Local snapshot lives in .cache/*.csv.
- Refresh it with `python tools/dump_sheet.py` (read-only, cannot write).
- .cache/ is a snapshot, not live. Types differ from the API: gspread returns strings, CSV parsing may infer. Don't chase type bugs against the CSVs.
- Never write to the sheet without asking me first.

# Tests

- `python -m pytest tests/ -q` — AppTest harness, runs headless.
- Prefer AppTest for logic/state bugs. Use the browser only for layout and rendering.

# UI selectors

- Target Streamlit data-testid attributes (stButton, stTextInput, stDataFrame) or get_by_label.
- Never use generated class names.
