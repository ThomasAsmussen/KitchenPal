# Dev loop

- Start app: `./run-dev.sh` (port 8501, logs to /tmp/streamlit.log)
- Streamlit hot-reloads on save. Only re-run run-dev.sh if imports change or the process died.
- After ANY change: `tail -50 /tmp/streamlit.log` and check for exceptions.
- After any UI change: load http://localhost:8501 in the browser and verify visually before saying it works.

# Data

- Backend is a Google Sheet. Local snapshot lives in ~/.cache/kitchenpal/*.csv.
- Refresh it with `python tools/dump_sheet.py` (read-only, cannot write).
- ~/.cache/kitchenpal/ is a snapshot, not live. Types differ from the API: gspread returns strings, CSV parsing may infer. Don't chase type bugs against the CSVs.
- The app points at "KitchenPal DEV", a disposable copy. Writing to it through the app is expected and encouraged — that's what it's for. Verify write paths end to end rather than stopping at the UI layer. Never point secrets.toml back at the production sheet.
- The roster (Kopi af In-House Liste) is masked in the dump only. Real values ARE available at runtime via SheetsService — build features that use them normally.

# Constraints

- This repo is PUBLIC. Never write sheet data, roster data, or credentials anywhere inside the repo directory — dumps go to ~/.cache/kitchenpal/.

# Copy-balances contract (protected)

`copy_balances_from_previous_month(month, year)` in src/kitchenpal/sheets/months.py is the most damage-prone code in the app — wrong numbers propagate for months. Its behaviour is pinned by the copy_balances tests in tests/test_sheets_service.py; do not change it without explicit sign-off.

- Previous month = calendar month before (year-1 for January). Sheet names resolve English then Danish ("May 2026" / "Maj 2026"), exact match then case-insensitive; missing sheets raise ValueError.
- Reads from the previous sheet: A45:B65 (room label, name), Z45:Z65 (closing balances), AG37 (kitchen account). Reads current A45:B65 for labels only.
- Writes to the current sheet only: B45:B{n} names, I45:I65 previous-balances, AS3:AT3 = [month#, year], and AG37 = "=<prev value, comma-decimal, no thousands sep>+sum(AG44:AG55)". One batch_update + one update_acell; Z is never written (sheet formulas own it).
- Matching is by ROOM LABEL: each current row gets the previous month's occupant of that room (overwriting whatever name is in the current sheet) and that person's closing balance. Balances follow rooms, not people.
- Blanks: unknown/blank labels → name "" and balance 0.0. Unparseable balances → 0.0. Blank AG37 → ValueError. Rooms present last month but missing this month are silently dropped — their balance is carried nowhere.
- Duplicate person in two rooms last month → the last row's balance wins for both rooms.

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