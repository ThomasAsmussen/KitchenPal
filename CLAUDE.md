# Where we are (updated 2026-08-29)

2026-08-29: the Andet block grew from 9 rows to 20 and pushed the account table to
row 56 (see Sheet layout). Constants, capacity guards, integrity checks and tests
followed; merged to main as b20ab33. Then step 0+1 of the restructure landed on
claude-worklog: four tabs with a fixed bottom bar, identity, and (step 2) the
Dinner screen — tonight first, a guest stepper that saves itself, your cooking
nights for the month, and the month/day pickers behind "Another day". Step 3 gave
Me the balance statement: one number, then the parts the sheet itself computed.

Steps 4 and 5 landed too, and on 2026-08-29 the House ledgers were rebuilt: the
three st.table dumps with a "pick a row from a dropdown" editor became row lists in
the app's own line language, each row a pencil that opens a dialog.

On the same day Admin followed, twice: three tabs and eight sheet-named forms
became a rollover checklist, and then the checklist itself was cut down to two
questions once it turned out four of its six steps needed no human at all (see
Admin and The month turns, below).

Next, in order:
1. COMMIT — none of this session's work is committed, and it lives in one
   working tree.
2. Deploy and run the three-task walkthrough with residents.
3. Birthdays overview under House.

The plan, the mockups and the settled decisions live in the artifact at
https://claude.ai/code/artifact/f0d009a0-9197-477f-94fe-80b719e100bb

Open backlog: bytte madklub (a swap action on your own cooking night), birthdays
overview under House.

DEV sheet state: rebuilt on 2026-08-29 with the new layout — August and September
2026 only. The Log worksheet permanently contains demo rows from the 2026-08-05 and
2026-08-29 end-to-end tests; real history from here on.

Manual tasks for Thomas (the app can't do these):
- Mark fixed items Done in the production Bugs and New Features tabs.
- test_sheet.xlsx now lives in ~/.cache/kitchenpal/ and is gitignored, because the
  export carries roster e-mail addresses and phone numbers and this repo is public.
  KITCHENPAL_TEST_SHEET overrides the path; the integration tests skip without it.

# Reads and caching (2026-08-29)

Every read is an HTTPS round trip of ~300 ms, and the Sheets API's read budget
(60/minute) belongs to the app's one service account — it is the whole house's, not
each resident's. Measured before/after per tab: Dinner 10 → 4, Me 12 → 4, Plan 10 → 7,
House 28 → 0 for the index; a Dinner re-render went 4 → 0.

- ui/data.py holds every read as an st.cache_data function, so one fetch serves the
  whole house instead of one per session. Writes call the matching clear_* helper;
  the Refresh button clears everything. Never add a read that bypasses this module.
- SheetsService.get_worksheet caches the handle: gspread's Spreadsheet.worksheet()
  re-fetches the sheet list on every call. forget_worksheets() when a sheet is added
  or removed.
- Streamlit runs the body of a collapsed expander, so House shows an index and loads
  one section at a time. Do not put a read behind an expander and assume it is lazy.
- Dinner answers from get_day_rows (one call for the month, menu description
  included). It does not call get_day_details or get_signed_up_people.

# App structure (2026-08-29)

Four pages, one per question a resident actually has: Dinner, Me, Plan, House.
Because the app knows who you are, no screen asks again and nothing house-wide sits
on a personal screen:
- Dinner: tonight, one tap to eat, a guest stepper, your cooking nights. The host
  fields appear inline on your own night and behind one button on anyone else's.
- Me: your balance, the parts behind it, your own purchases and payments (editable),
  and three buttons that open dialogs to add drinks, a purchase or a payment. Each
  form acts as you, with a "For someone else" toggle for covering a housemate.
- Plan: your own availability card only.
- Andet (shared costs): a dinner without a date. Rows 34-53 of the month sheet take
  the same columns as a day, so the sheet does the splitting — the payer is credited
  the whole amount in "Mad udlæg" and everyone marked in I:AB is charged one share.
  Created from Me ("Shared cost"), listed under House, twenty slots per month.
  Who can take a share: "Everyone in the house" means the numbered rooms 346-360
  that someone lives in — never an FL slot. A parked FL person with a name can
  still be ticked by hand; an empty FL slot is a placeholder and is never offered
  anywhere (see is_room_label / is_occupied_account in sheets/utils.py, which the
  "For someone else" pickers use too).
  Verified live: 300 DKK paid by one person and split three ways moved the balances
  by +200 / -100 / -100.
- House: balances for everyone (worst first, your row bold), the cooking schedule,
  who can cook when, the ledgers, bugs and ideas, and Admin.
- The ledgers (drinks, purchases, payments) are lists, not tables: each tab opens
  with its one number, then a row per entry — what it was, whose it is, when — and
  a pencil that opens the same edit dialog Me uses. House passes allow_reassign so
  it can also move a row to the right person. Newest first; undated rows last.
  Deleting is two steps (_delete_control): st.rerun() inside a dialog CLOSES it, so
  arming and cancelling happen in on_click callbacks, which have already run by the
  time the dialog redraws. Drinks are correctable at last — the pencil sets the
  month's tally rather than adding to it.
- .kp-line draws the hairline between rows. It used to carry a
  `.kp-line:last-of-type {border-bottom: 0}` rule, which silently removed every
  divider in the app: each line is alone inside its own stMarkdownContainer, so
  every one of them is last-of-type. Style siblings, not markdown-wrapped singletons.
- The month is one shared choice (ui/month.py) for Dinner, Me and House. Plan keeps
  its own, because planning is about the month ahead, not the one you are living in.
- app.py builds them with st.navigation(position="hidden") so each tab keeps a real
  URL, and ui/nav.py draws the visible bar pinned to the bottom. Streamlit's own top
  navigation collapses into a hamburger on a phone, which is the hiding we are
  ending. Read the docstring in ui/nav.py before touching that CSS — the bar is
  matched with `.st-key-kpalnav` exactly, never `[class*=]`.
- Community Cloud serves the app inside <iframe title="streamlitApp"> and floats
  two controls in the HOST page beside it: ._viewerBadge_* (fixed, z-index 50)
  and ._profileContainer_* (fixed, z-index 40). Inspected on the live app at
  390x820 they cover x=253..390, y=774..820 — exactly the House tab. They CANNOT
  be hidden or out-ranked from in here: they are in the document that contains
  ours, so our selectors never match them and our z-index, however large, is
  confined to the iframe. Three attempts failed for that one reason before it
  was measured; measure the DOM before writing CSS against someone else's
  chrome. Staying clear of them at the bottom costs about 110px of a phone
  screen and three CSS workarounds; the TOP costs nothing, because the header's
  60px is reserved either way. So NAV_AT_TOP in ui/nav.py decides where the bar
  lives, and it is True while the app is on Community Cloud. Flip it and
  redeploy to compare — the bottom branch keeps the floating-pill treatment
  (inset, rounded, with a ::after skirt in the page colour so content does not
  scroll through the band the controls sit in, and width:auto because Streamlit
  gives the container width:100%, which beats the right offset and hangs the bar
  off the screen). Hosting anywhere that floats nothing makes the bottom free
  again, and it is the better place for a thumb.
- The identity chip's clipped ascenders were OUR rule, not Streamlit's: the
  "primary action above the fold" media query set padding-top: 2.2rem at 400px,
  putting the chip's top at y=51 behind a header ending at y=60. It was
  diagnosed as Streamlit's and papered over with a more specific selector before
  anyone read our own stylesheet to the end. Check what is already there before
  out-specifying somebody else.
- ui/identity.py asks once which room you are and keeps it in the query string, so a
  bookmark remembers you. It is a claim, not a login: nothing is locked to it, every
  form still shows the room it will write to, and room selectboxes merely default to
  you. st.switch_page drops the query string, so identity is re-stamped every run.
- One "Refresh data" for the whole app, at the bottom of the page (nav.py), instead
  of one at the top of every screen.
- Me never adds money up: `get_account_statement` reads the person's account row
  (A:Z) and names the columns the sheet already computed — carried in, dinners
  eaten, dinners cooked, drinks, purchases, payments, dues, interest. The parts sum
  to the balance because the sheet says so, not because the app recomputed it.
- Dinner reads the whole month in one call (`get_day_rows`) so tonight, the next
  dinners and your own cooking nights cost one request, not thirty. Writes go
  through on_click callbacks: Streamlit reruns by itself afterwards, so never call
  st.rerun() inside one — it prints a warning into the app.
- The accent is set once in .streamlit/config.toml (primaryColor), so the primary
  button and the active tab are the same petrol. The same file sets
  client.toolbarMode = "minimal", which removes Deploy, the hamburger and the
  running indicator — Streamlit's own switch, not CSS guessing at class names.
  It empties the header but does NOT shrink it: the 60px box stays, so the
  main container keeps its top padding. Do not reclaim that space on the
  strength of a local screenshot — Community Cloud puts its own controls in
  that header, and the padding is what keeps the identity chip out from under
  them.
- UI language: English interface, Danish content left as residents typed it, one word
  per concept — dinner, host, signup, drinks, shared purchase, kitchen fund, balance.
  Never "food club" or "madklub" in the interface.

# The month turns by itself (2026-08-29)

ui/rollover.py. Creating a month sheet has no decision in it, and the copy reads
the previous sheet's LIVE closing column -- so carrying early writes numbers that
are still moving. Neither is a step an admin performs:

- The sheet appears when something first needs it, already FILLED (_ensure_prepared
  in ui/admin.py): preparing is create + copy, so an admin never lands on a sheet
  holding one typed name and fourteen blank rooms. That half-state is worse than
  no sheet at all -- it looks like a house with one resident.
- turn_if_due() runs from app.py's _chrome on every page load and opens the
  CURRENT month if it is not open yet: create if missing, then carry, then log.
  Streamlit has no scheduler, so "on the 1st" means the first page load on or
  after it. Until then every screen carries the red banner instead of quietly
  showing last month's numbers.
- Guarded by a module-level lock (process-wide: Streamlit serves all sessions
  from one process), a 300 s retry throttle after a failure, and a fresh
  uncached re-check inside the lock. create_month_sheet re-reads the sheet list
  and refuses to make a second sheet; the copy is idempotent by design.

Two states, both proved by the Log and never by the sheet's contents:
- PREPARED (a prepared or rolled_over row): a copy has filled the sheet, so there
  is a real roster to edit. Names cannot prove this -- one typed name is exactly
  the state needing repair.
- OPEN (a rolled_over row DATED ON OR AFTER THE 1st): the balances are final.
  The turn only skips a month that is open, so preparing early must NOT count as
  opening or the balances would never be refreshed on the 1st. An opening that
  happened BEFORE the month began is provisional too (turned_early): the copy
  reads the previous month's live closing column, so opening on the 30th freezes
  figures August had not finished moving, and the last two days of dinners would
  vanish from the carry. The automatic turn runs again once the month starts. A
  row with no timestamp is taken at its word -- re-copying on every page load
  would be worse.
The bias is deliberate: believing a month is closed when it is open costs one
idempotent copy, the other way round leaves every balance wrong. The house's
first month, with no previous sheet behind it, counts as open (nothing_to_carry).
Running the copy twice is safe -- pass 1 KEEPS every name already on the sheet,
so an admin's edits survive the turn.

Known limit: month_status reads the whole Log (cached 300 s). Fine for a house;
if the Log ever grows to thousands of rows, read a tail instead.

# Admin (rebuilt 2026-08-29, cut down the same day)

ui/admin.py. Two questions, because four of the old six steps needed no human.
The screen is three numbered cards, and the third one matters as much as the
other two: showing the step nobody performs is what makes the sequence legible.
Above them, one sentence carries the whole model -- "Opens by itself on Tuesday 1
September" and "Two things to answer before then, the app does the rest" -- which
is a deadline and a division of labour, the two things that were missing when it
read as a bare list of buttons. A date beats a countdown: "in 3 days" is not
something anyone can act on.

Each card is a bordered container holding its question button and its own state
line, because a loose caption between two full-width buttons could be read as
belonging to either. An answered question's button goes tertiary so the card
border is not doubled; exactly one unanswered card is primary, so there is always
one obvious next thing. Question one's actions sit ABOVE its roster: twenty rows
between a question and its answer means nobody reaches the answer on a phone.

The three cards:

- 1. "Who lives here in September?" -- the only thing the app cannot know, asked as
  a ROSTER rather than a list of move types. An admin does not think in verbs:
  a room can empty, fill, or change hands three ways round in one month, and
  enumerating those cases produces a form nobody can map onto their situation.
  Next month starts as a copy of this one and you edit rows until it is right;
  any permutation is expressible by putting the right name in each room. The
  answer is recorded as an occupancy_confirmed Log row, and the button says
  "That's everyone -- done", never "nobody is moving" (which becomes a lie the
  moment one change is recorded, and left the admin with no way forward).
  It MUST be answered before the month turns: copy-balances reads the sheet's
  names to decide who to KEEP, so a move-in recorded first is one action (keep
  the new person, chase the leaver's balance into FL) and the same move-in after
  the turn is three.
- A room-to-room move and a swap are one control ("Moving to another room"):
  move_person_between_accounts swaps when the destination is taken and moves when
  it is free, so nobody has to say which is happening. An empty room also offers
  "someone already on the sheet", which is what makes a chain expressible: 347
  leaves, 350 moves into 347, someone new takes 350.
- Someone without a room is NOT SCHEDULABLE until they say otherwise.
  combine_availability reads an empty available list as "every day", so silence
  is a yes -- right for someone on the rota, wrong for someone who is not on it
  and would otherwise be handed a night they never asked for.
  _stored_availability marks an unanswered person without a room unavailable for
  the whole month, and Plan opens their calendar with every day set to "can't",
  one tap from a yes.
- Only people with a ROOM count towards "everyone has answered". Someone parked
  without a room may still answer on Plan and is scheduled if they do -- they are
  simply not on the rota, so they cannot be missing from it.
- "The name is spelled wrong" calls rename_person, NOT replace_room_person.
  replace_room_person treats a new name as a new person and moves the old one out
  to an FL slot, which for a typo invents a second person and displaces the first.
  rename_person rewrites the name cell only, finds the row BY LABEL so it still
  works on a sheet with the duplicate names it exists to fix, and never touches a
  balance. Offered on FL rows too.
  It also spreads the correction to the months either side (_spread_rename), and
  that is not a nicety: copy-balances matches people BY NAME, so a spelling fixed
  on one sheet and not its neighbour makes one human look like two -- the new
  spelling starts at 0.00 and the old one is chased into FL as a departed debtor.
  Only an unambiguous single match on a neighbour is touched. Saving an unchanged
  name is deliberately not a no-op: it re-spreads, which is the one-tap repair.
- "Someone is moving in" is ONE path, whoever arrives when. Everybody joining
  needs the same two things: a row without a room in the month running now, so
  the app knows who they are and they can answer when they can cook, and the
  room itself on the month they take it over. The dialog used to ask "when?" and
  then do those same two writes in a different order -- a question with no
  consequence, and the two orders did not even fail the same way. The only
  question left is which room, if any.
- The ROOM is written first, then the row for now. This month's FL rows can
  legitimately all be taken, and a full FL table must not stop the app recording
  which room somebody has next month -- the half that is hard to reconstruct
  afterwards. When the second half fails the toast says which half landed.
- The room-less row is not billing: dues are charged to room rows, so an FL row
  costs nothing. It exists because the app only knows the people on the current
  month's sheet, and without one they cannot even say who they are.
- Every action reports through st.toast, not st.success: these actions end in a
  rerun that would wipe a success message, and where a person ended up is the one
  thing they must not do silently.

FL slots are filled from opposite ends on purpose: arrivals take the lowest free
slot, leftover tabs the highest. A displaced person landing on FL5 while FL2 is
free is correct, not a bug -- it matches where copy-balances would chase them
(highest first). The signup-column filter on arrivals is a guard, not the reason;
every FL slot has had a signup column since the 2026-08-29 layout change.
- 2. "Who is cooking?" -- the answers, the day limit, the schedule, the write.
  The day limit is a SETTING inside this question, not a step: blank is the
  normal answer, and a checklist item you complete by leaving something empty is
  a bug in the checklist.
- 3. "Everyone's balance carries over" -- not a button, a statement of what the
  app does on the 1st without being asked.
- Below them, a to-do list derived from the sheet rather than remembered from the
  copy's report -- money left behind by someone with no row this month, a name on
  two rows, a parked person whose room is now free. It survives a restart and
  cannot go stale. Only shown once the month is open, or everyone in the previous
  month reads as "missing" from a sheet that has no names yet.
- "Something went wrong?" holds the manual open (for a failed turn, or to carry
  again after correcting last month) and the month picker.
- The footer says "Change August (this month)", never "Who lives here": a second
  control with the same name as question one is the fastest way to make someone
  edit the wrong month. House's own month picker is hidden on Admin for the same
  reason, and the next-month nudge in the banner is suppressed there -- on Admin
  it is the same fact said twice, an inch apart.

Arrivals no longer cost a month in FL. A room's accounting belongs to one person
for a whole month, which is the ONLY reason FL parking exists, and it binds
mid-month arrivals alone: "Someone is moving in" asks when, and someone starting
on the 1st goes straight into the room on next month's sheet.

Who lives here (the roster) and What has been done (the Log) are unchanged.

Known interaction with the protected copy: moving out someone who owes NOTHING
leaves no FL row behind (pass 3 drops zero balances), so pass 2 refills their
empty room with them at the turn. No money is ever wrong -- a settled tab is 0.00
-- but a silently reverted admin action is worse than a wrong one, so
reverted_move_outs() flags it on the to-do list. Do not "fix" it by parking
settled leavers: FL slots are scarce and the copy is not ours to change.

Gotchas this cost:
- The Log is written with value_input_option="RAW". Under USER_ENTERED, a
  Danish-locale spreadsheet parses the Month sheet cell "September 2026" as a
  DATE and hands it back as "september 2026" -- which silently broke every reader
  matching on the sheet name. Readers still compare case-insensitively
  (rollover.same_month_sheet) for the rows written before this was found.
- AppTest's .click() fires a disabled button, so a disabled-button guard must be
  asserted with `.disabled`, never by clicking and checking nothing happened.
- tests/conftest.py clears st.cache_data around every test: ui/data.py hides the
  service from the cache key, so one test's stub reads would answer another's.
- get_log_entries already returns NEWEST FIRST. Do not reverse it again.
- st.rerun() inside an st.dialog CLOSES it, so a two-step confirmation inside one
  arms and cancels through on_click callbacks instead.

# Sheet layout (verified against the live sheet 2026-08-29)

The Andet block was grown from 9 rows to 20 on 2026-08-29, which pushed everything
below it down by 11 rows on every month sheet and on Skabelon. Column blocks that
live to the right (AC:AG) did not move.

    rows  3-33   Indkøb — 31 purchase rows; the sheet sums SUMIF($AC$3:$AC$33,...)
    rows 35-42   STATUS box and bank details (labels AC, amounts AG)
    row   43     payment table header
    rows 44-55   kitchen fund payments — 12 rows; SUMIF($AC$44:$AC$55,...)
    rows  3-33   day table (A:AB), rows 34-53 Andet (same columns, no date)
    row   54     "Personlige Regnskaber", row 55 "Værelse | Navn"
    rows 56-76   personal accounts: 346-360, FL1-FL5, Spotify

Rules that follow from it:
- Never write past a table's last row. The balance formulas only sum the rows
  above, so a spilled row is money that silently never lands, and rows 34-43 hold
  the STATUS box. Capacities are in constants (31 purchases, 12 payments) and the
  UI shows how many are used.
- The nth account row must line up with the nth signup column (I2:AB2) and the nth
  KØVS row: the sheet charges meals with INDEX($I$3:$AB$53, 0, ROW(A1)) and drinks
  with =-AP3. Reordering one list without the other bills the wrong people.
- tests/test_transfer_purchase_layout.py is the single place these row numbers are
  pinned to literals; check_month_sheet_integrity checks a live sheet against them.

# Copy-balances contract (protected, v2 — implemented 2026-08-05)

`copy_balances_from_previous_month(month, year)` in src/kitchenpal/sheets/months.py is the most damage-prone code in the app — wrong numbers propagate for months. Its behaviour is pinned by the copy_balances tests in tests/test_sheets_service.py; do not change it without explicit sign-off. Balances belong to people; rooms are where a person currently lives.

Resolution and mechanics:
- Previous-month resolution incl. Dec→Jan year rollover; English/Danish sheet names,
  exact then case-insensitive; ValueError when previous or current sheet is missing.
- Read ranges (previous A56:B76, Z56:Z76, AG37; current A56:B76) and write ranges
  (B56:B{n}, I56:I76, AS3:AT3, AG37 formula "=<prev, comma-decimal, no thousands
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
- create_month_sheet blanks the person-row name cells (B56:B76, non-person rows
  kept) right after duplicating the template, so a fresh sheet always arrives in
  a known state whatever names the template holds. Do not detect template names
  by comparing against Skabelon — a real resident's name could match.

# Calendars and swapping a dinner (2026-08-29)

ui/calendar_grid.py draws a month as seven columns wherever one appears — Plan's
answer, Dinner's day picker — and its styles live in nav.page_styles, which every
page emits. That placement is the point: the first calendar was invisible on
phones because its stylesheet was written but never put on a page, and a test
that only inspects a style STRING cannot catch that. The state of a day rides on
its wrapper container's key (`st-key-kpalday_<state>_...`), leaving the button's
own key stable across a change of state.

Dinner's picker shows the month instead of a dropdown of numbers: your nights
solid, nights somebody else has taken pale, the day you are looking at outlined,
and free days plain. "free" deliberately has no fill — a night nobody has taken
must not look like a night somebody has.

Bytte madklub is service.swap_dinner: the chef is one cell per day, so giving a
night away and trading two are the same write. It re-reads the chef column first
and refuses when the sheet no longer agrees about who is cooking, because the
screen offering the swap may be a minute old. Both people get a Log row sharing
one action id — nobody is asked to consent (this is a house, not a workflow
engine), but an argument about it would need the record.

That staleness guard CANNOT catch a replayed click: a swap is its own inverse,
so a repeat looks exactly like a genuine swap back the other way. One test click
was applied twice from a browser tab reconnecting to a restarted server, which is
how this was found. The dialog now refuses the same swap twice within a session.
That is a mitigation, not a proof — a replay arriving as a fresh session would
still get through, and the Log is where a double swap would be spotted.

# The Plan tab (rebuilt 2026-08-29)

ui/plan.py. One calendar, three states, no modes. Every dinner day is already
available / unavailable / preferred in the data, so the state lives on the day
and a TAP CYCLES IT: can cook -> can't -> would like to. That retired the radio
that reversed the meaning of ticks already made, and the second "preferred
dates" grid whose relation to the first was never stated. Days the house cannot
hold a dinner on are drawn flat and inert, which retired the "Possible dates:
1, 2, 3, 6..." wall of numbers into the thing it described.

- Days start as CAN: most people can cook most days, so the answer is its
  exceptions. The one answer that cannot be read that way is an old whitelist
  row -- available days listed with nothing marked unavailable -- where the days
  left out WERE the no. day_states_from_entry restores those as no, not as yes.
- A preferred day is also an available day, or the solver cannot use it.
- The state rides on a wrapper container's key (`st-key-kpalday_<state>_...`) so
  the button's own key stays stable across a change of state.
- Answered? The page opens on your answer in words, not the form -- the only
  question this tab is asked after answering once is "what did I put?".
- Saving ends in st.rerun(). Without it the page keeps the counts it read BEFORE
  the write, so answering never moved the number underneath it.
- Once cooks are written, Plan says which nights are yours and which of them you
  had asked for. Dinner shows the month you are living in; nothing showed next
  month, which is the one you just answered about. NOT yet verified against a
  live schedule -- no month on DEV has cooks written.

The old stylesheet was defined, covered by a test that only inspected the string
it returned, and CALLED FROM NOWHERE -- orphaned when the planner was split into
three views. st.columns stacks below ~640px, so the calendar became a 5,617px
column of 62 checkboxes on a phone. _plan_styles() is injected by
render_planning_view, forces the seven columns at every width, and a test now
asserts the injection and not just the string.

# Planning sheet identity

Plan is about the month AHEAD, but identity is a claim on a room in the month you
are living in, and rooms change hands at a rollover. So _planning_room_entry
resolves the claim through the person: your label in the current month gives your
NAME, and that name finds your row in the month being planned. In 356 this month
and 350 next month, your answers belong to 350 -- and must never land on the card
of whoever takes 356. When your name is on neither, and the claimed label belongs
to somebody else that month, Plan says so instead of answering for them.

Only rooms with someone in them are counted in "X of N have answered"
(_rota_entries). Anyone without a room may still answer and is scheduled if they
do; they are simply not on the rota, so they cannot be missing from it. The same
rule holds in Admin's question two and in House's availability overview.

A Planning row belongs to a ROOM, not to a person's name. `save_planning_entries`
matches existing rows on (year, month, Room); column C (Name) is display only and is
refreshed on every save. Rows with a blank Room fall back to a normalized-name key.
The UI looks stored preferences up by `room_entry.label` for the same reason.

Why: the UI identifies people as `entry.name or entry.label` from the month sheet's
B56:B76. That cell legitimately changes (create_month_sheet blanks it, copy-balances
fills it back in, occupancy actions rewrite it), so name-keyed rows flipped identity
underneath residents: their preferences stopped loading, the picker came up empty, and
saving appended a duplicate row while the old one kept the room number as its "name".
A save now also collapses any duplicate rows a room accumulated under the old scheme.

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

# Deployment

Community Cloud runs the app from GitHub with `streamlit run streamlit_app.py`,
which puts `src/` on the path. Two things about that environment have bitten:

- It picks its own Python and resolves unpinned dependencies at deploy time. It
  was running Python 3.14 while everything here is tested on 3.12, with
  gspread/pandas/ortools unpinned. requirements.txt now pins every version to
  what the tests run against; set the Python version to 3.12 in the app's
  Advanced settings, because there is no file for it.
- An error during IMPORT leaves the module tree half-built, and Streamlit reruns
  the script rather than dying. The second symptom is then
  UnserializableReturnValueError from a cached read: st.cache_data pickles what
  it stores, and a dataclass built against one copy of a class cannot be pickled
  against another. Chase the FIRST error in the Cloud logs; the cache error is
  usually its shadow, not a separate fault.

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