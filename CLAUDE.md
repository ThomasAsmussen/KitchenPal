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

# Copy-balances contract v2 (approved 2026-08-05 — tests written, NOT yet implemented)

Person-keyed replacement for the contract above. Balances belong to people; rooms are
where a person currently lives. Once implemented, the v1 section above is deleted.

UNCHANGED from v1:
- Previous-month resolution incl. Dec→Jan year rollover; English/Danish sheet names,
  exact then case-insensitive; ValueError when previous or current sheet is missing.
- Read ranges (previous A45:B65, Z45:Z65, AG37; current A45:B65) and write ranges
  (B45:B{n}, I45:I65, AS3:AT3, AG37 formula "=<prev, comma-decimal, no thousands
  sep>+sum(AG44:AG55)"). One batch_update + one update_acell. Z never written.
- Unparseable balances → 0.0. Blank AG37 → ValueError. Blank current labels → "" / 0.0.

CHANGED matching (the core):
1. KEEP: a current row with a non-blank name keeps that name; its balance is the
   previous sheet's closing balance for that normalized name (0.0 if the person is new).
2. FILL: a current row with a blank name and a label is filled with the previous
   occupant of that label and their balance — but only if that person is not already
   named elsewhere on the current sheet (kept or filled earlier, top-down); otherwise
   the row stays "" / 0.0. Deliberate occupancy changes are never reverted.
3. CHASE: previous-sheet people with a non-zero closing balance who appear nowhere on
   the current sheet after 1–2 are written into free FL slots, highest label first
   (FL5→FL1), in previous-sheet row order. Zero-balance departures are dropped silently.
   If no free FL slot remains, the copy still completes and reports them as unplaced —
   leftover balances are chased, never written off.
4. REPORT: the function returns a report instead of None: chased [(name, balance,
   fl_label)], unplaced [(name, balance)], suspected_renames [(label, previous_name,
   current_name)] — flagged when a room's name changed and the previous occupant left
   a non-zero balance and is nowhere on the sheet (likely typo/rename) — and
   duplicate_names [name] when one person appears in several current rows (each row
   gets that person's balance). The copy itself stays deterministic; the report is
   for the UI to surface.

# Log sheet schema (append-only)

Worksheet "Log" (renamed from Ark5) is the permanent event history. Rows are appended
at the bottom, never edited, never cleared; correctness must never depend on the Log
being complete (residents edit the spreadsheet directly). The app displays newest-first,
capped at ~50 on mobile.

Header row 1, columns A–K:
  Timestamp | Event | Summary | Action id | Month sheet | By | Person | From | To | Balance | Room intent
- Timestamp: "YYYY-MM-DD HH:MM:SS", Europe/Copenhagen local. Always filled.
- Event: stable snake_case token (moved_in, moved_out, parked_fl, moved, deleted, …).
  Tokens are never recycled with a new meaning. Always filled.
- Summary: complete human sentence, self-sufficient for event types the app doesn't
  know. Always filled.
- Action id: short token shared by all rows written by one admin action (a swap's two
  rows share it). Always filled.
- Month sheet: the month sheet the action modified (e.g. "June 2026"). Always filled.
- By: claimed identity, optional free text, never trusted.
- Person / From / To / Balance / Room intent: one row per PERSON affected (a swap
  appends two rows). From/To are account labels; Balance is the DKK that moved with
  them; Room intent (parked_fl only) is the room they are waiting for.

Growth rules: readers go by header name, never column index. New event types fill
Timestamp/Event/Summary/Action id/Month sheet and reuse other columns only when the
header's meaning matches exactly; new structured fields get NEW columns appended on
the right — never insert, rename, or repurpose. The rollover may read parked_fl rows
to SUGGEST completions but acts only on explicit confirmation and falls back to sheet
state detection when the Log says nothing.

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