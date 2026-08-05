# Dev loop

- Start app: `./run-dev.sh` (port 8501, logs to /tmp/streamlit.log)
- Streamlit hot-reloads on save. Only re-run run-dev.sh if imports change or the process died.
- After ANY change: `tail -50 /tmp/streamlit.log` and check for exceptions.
- After any UI change: load http://localhost:8501 in the browser and verify visually before saying it works.

# Data

- Backend is a Google Sheet. Local snapshot lives in .cache/*.csv.
- Refresh it with `python tools/dump_sheet.py` (read-only, cannot write).
- .cache/ is a snapshot, not live. Types differ from the API: gspread returns strings, CSV parsing may infer. Don't chase type bugs against the CSVs.
- The app points at "KitchenPal DEV", a disposable copy. Writing to it through the app is expected and encouraged — that's what it's for. Verify write paths end to end rather than stopping at the UI layer. Never point secrets.toml back at the production sheet.
- The roster (Kopi af In-House Liste) is masked in .cache/ only. Real values ARE available at runtime via SheetsService — build features that use them normally.

# Tests

- `python -m pytest tests/ -q` — AppTest harness, runs headless.
- Prefer AppTest for logic/state bugs. Use the browser only for layout and rendering.

# UI selectors

- Target Streamlit data-testid attributes (stButton, stTextInput, stDataFrame) or get_by_label.
- Never use generated class names.

# Constraints

- Mobile-first. Most residents use this on a phone. Any UI change must be checked at a
  narrow viewport (~390px) in the browser before it's considered done. Looking fine on
  desktop is not enough.
- UI language is English.
- Do not build: e-mail notifications, feedback voting, or anything about "James".