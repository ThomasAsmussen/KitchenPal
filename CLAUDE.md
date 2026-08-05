# Where we are (updated 2026-08-05, end of session)

Landed today (main == claude-worklog, suite at 146 passed):
- Bug fixes: feedback form clears after submit (3c14956), negative purchase amounts for pant (9211df8), planning calendar usable on phones (5ce1d9e), copy-balances button deadlock + frozen label (4c7f3ca).
- Repo/infra: roster PII scrubbed from git history and force-pushed, sheet dumps moved to ~/.cache/kitchenpal/ (d3ad030), streamlit pinned (80e372c).
- Copy-balances v2 + Log: contract and failing tests (357c28b), person-keyed copy + Log service (3501efb), two-month delete guard + copy report in Admin (3a, 0efb1fb), occupancy actions + Log writes + sheet integrity check (3b, d3d1593).

Next, in order:
1. USER_ENTERED formula-write audit: gspread batch_update defaults to RAW (bit us when backfilling Z formulas); audit every code path that writes formulas, and check whether any existing DEV sheet has a text (non-formula) AG37.
2. The four remaining integrity checks: signup header complete at I2:AA2, account table anchored (A45 == "346"), AG37 contains a formula, AS3:AT3 month metadata present.
3. 3c: People tab restructure (task-language forms, compact two-line people list) and the pending-handover banner (reminder options 1+2).

Open backlog: bytte madklub, the Andet capacity question, birthdays overview, tutorial page.

DEV sheet state: February 2027 deleted; January 2027 restored to its post-copy state; test1 removed from FL2; the Log worksheet permanently contains demo rows from the 2026-08-05 end-to-end tests — real history from here on, but the early rows are test events.

Manual tasks for Thomas (the app can't do these):
- Backfill the closing-balance formulas (=sum(F{row}:X{row}) in Z45:Z65) into the PRODUCTION month sheets — the Skabelon fix only helps sheets created from now on.
- Mark today's fixed items Done in the production Bugs and New Features tabs.

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

# Copy-balances contract (protected, v2 — implemented 2026-08-05)

`copy_balances_from_previous_month(month, year)` in src/kitchenpal/sheets/months.py is the most damage-prone code in the app — wrong numbers propagate for months. Its behaviour is pinned by the copy_balances tests in tests/test_sheets_service.py; do not change it without explicit sign-off. Balances belong to people; rooms are where a person currently lives.

Resolution and mechanics:
- Previous-month resolution incl. Dec→Jan year rollover; English/Danish sheet names,
  exact then case-insensitive; ValueError when previous or current sheet is missing.
- Read ranges (previous A45:B65, Z45:Z65, AG37; current A45:B65) and write ranges
  (B45:B{n}, I45:I65, AS3:AT3, AG37 formula "=<prev, comma-decimal, no thousands
  sep>+sum(AG44:AG55)"). One batch_update + one update_acell. Z never written.
- Unparseable balances → 0.0. Blank AG37 → ValueError. Blank current labels → "" / 0.0.

Matching (person-keyed):
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

Special rows and creation:
- The −29 in AG44:AG55 on a fresh sheet is the legitimate automatic monthly
  Spotify transaction, present in the template on purpose. It is NOT stale
  data — do not flag it, "fix" it, or add an integrity check against it.
- Labels in constants.NON_PERSON_ACCOUNT_LABELS (currently "Spotify") are
  accounting-only, never people: their name and balance carry forward by label
  (overwriting the current cell), and they are excluded from filling, chasing,
  rename and duplicate detection. Never chase a balance into such a row.
- create_month_sheet blanks the person-row name cells (B45:B65, non-person rows
  kept) right after duplicating the template, so a fresh sheet always arrives in
  a known state whatever names the template holds. Do not detect template names
  by comparing against Skabelon — a real resident's name could match.

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