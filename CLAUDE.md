# Where we are (updated 2026-08-31)

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

2026-08-31, from the house's own feedback on the live app: Dinner's day picker
stopped jumping (a bar at the top and a dialog, see App structure), Plan stopped
telling people to ask an admin and grew the same swap Dinner has, and the
Kitchen fund payment dialog now shows the account to send to.

Next, in order:
1. Deploy and run the three-task walkthrough with residents.
2. Birthdays overview under House.

The plan, the mockups and the settled decisions live in the artifact at
https://claude.ai/code/artifact/f0d009a0-9197-477f-94fe-80b719e100bb

Open backlog: bytte madklub (a swap action on your own cooking night), birthdays
overview under House.

DEV sheet state: rebuilt on 2026-08-29 with the new layout — August and September
2026 only. The Log worksheet permanently contains demo rows from the 2026-08-05 and
2026-08-29 end-to-end tests; real history from here on. 349 was put down to cook
10 September on 2026-08-31, deliberately: it is the only cook on DEV, and it is
what makes Plan's schedule card and its swap testable in a browser.

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
- The nav bar is drawn BEFORE page.run(), and the order is the point
  (2026-08-31, pinned by a test in test_app_nav.py). A tab button reports its
  click on the run that FOLLOWS it and st.switch_page raises immediately, so
  everything drawn before the bar has already run by the time the app learns
  you wanted to leave. Drawn last, a tab tap re-ran the page you were ON in
  full, reads included, and only then switched. Measured with the month caches
  expired: 2.2s for the page being left, then 15ms for the page arrived at.
  Bar first, that run is 15-22ms. Warm, a switch is ~20ms of Python and ~270ms
  click-to-painted locally — the rest is the websocket round trip and
  Streamlit re-rendering the whole element tree, and on Community Cloud the
  network adds to it.
- Dinner answers from get_day_rows (one call for the month, menu description
  included). It does not call get_day_details or get_signed_up_people.

# App structure (2026-08-29)

Four pages, one per question a resident actually has: Dinner, Me, Plan, House.
Because the app knows who you are, no screen asks again and nothing house-wide sits
on a personal screen:
- Dinner: tonight, one tap to eat, a guest stepper, your cooking nights. The host
  fields appear inline on your own night and behind one button on anyone else's.
  Which day you are looking at is answered by a bar at the TOP (2026-08-31):
  one step either way, and the month between them, opening a dialog that holds
  the calendar AND the month picker. It was an expander at the bottom, under
  everything it changes, and the house reported it "jumping around the page".
  Three things moved at once on every tap: the expander collapsed (its open
  state is not kept unless it is made stateful), the card, the host controls
  and the two lists above it changed height, and the control slid out from
  under the finger that had just used it. Nothing was slow -- every read on
  that page is cached. Placing it above the title is the fix, not styling: the
  title is one line whether it says "Tonight" or a date, so nothing over the
  bar can change height and it cannot be pushed. Keep it there.
  The dialog re-reads current_month_sheet on every run instead of taking the
  month as an argument, because a dialog re-runs as a FRAGMENT with the
  arguments it was opened with -- a captured month keeps drawing the month you
  just left. Changing the month inside it redraws only the dialog; picking a
  day sets DINNER_DAY_KEY in an on_click callback and st.rerun() closes the
  dialog and redraws the page behind in one go. render_dinner_view also clears
  DAY_PICKED_KEY defensively: when a click reruns the whole app instead of the
  fragment, the dialog is not drawn and nothing else would.
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
- How to pay (2026-08-30): Me said what you owe and stopped, and the account
  number was only in the spreadsheet -- the thing this app exists to spare
  people from opening. A card under the balance, ONLY when you owe, carries the
  three things a transfer needs: amount, account, and a message ("354 Philip" --
  room first because the accounts are keyed on it, first name after because that
  is what a human recognises on a bank statement). "Reg. nr." and "Kontonr."
  stay Danish inside an English interface on purpose: they are the names of the
  fields you are about to type into.
  The details are READ, never typed twice: AC35:AC42 of the month sheet, with
  the bank line found inside that block by carrying eight digits or more. Do not
  pin its row -- the Andet growth moved this whole region by 11 rows once
  already -- and do not match "konto" loosely, because "Bankkonto" one row above
  is the fund's own figure and not somewhere to send money.
  parse_bank_details returns the raw line when it cannot split reg from account,
  and the card shows that instead. Half a guess is worse than none: a resident
  who types a wrong account number into a bank app has no way back. An empty
  cell means no card, never an error.
  It only appears past 500 DKK (TRANSFER_REMINDER_THRESHOLD_DKK). Everybody's
  balance dips negative in the ordinary course of a month -- dues on the 1st, a
  dinner, a round of drinks -- and a card that turns up the day after somebody
  eats is one people learn to scroll past. It is a nudge for a real debt.
  The amount is EDITABLE, because paying part of a big balance is a normal thing
  to do, and "I've transferred it" records what you actually chose rather than
  the whole balance. Its widget key carries the amount owed, so a balance that
  moved since you last looked resets the field instead of quietly offering a
  stale number, while an amount you typed survives the reruns in between.
  st.code carries the copy button, which is the whole reason the values are code
  blocks -- but Streamlit reveals that button on HOVER, and a phone has none.
  Measured on the running app it is visibility:hidden until then, so the one
  affordance the card exists for was unreachable on the device everybody uses.
  nav.page_styles pins it visible inside [class*="st-key-kpalpay"], via the
  toolbar being the only div child of stCode (the other is the pre) -- never
  the emotion class. That toolbar FLOATS over the right-hand end of the block,
  so the pre reserves its width as padding; without it a ten-digit account
  number ran under the button.
  The same three values open the Kitchen fund payment dialog (2026-08-31,
  _render_bank_fields). The card only appears past the threshold, but people
  also open that dialog when they are ABOUT to pay, and the account was still
  only in the spreadsheet. Reg. nr. and Kontonr. sit side by side on the card
  and STACKED in the dialog: measured at 390px two columns there leave ~90px
  for a number that needs 91, and it broke across two lines. A bank account
  split over a line break is worse than a taller card -- it is the one value
  on the screen nobody can check by eye.
  "I've transferred it" ARMS a session flag that render_me_view pops
  (take_armed_transfer), and the card's own return value means only "was it
  drawn". They were one value once: the card returned `float | None` while two
  early returns still said `return False` from an earlier version, and
  `False is not None` — so every run that did NOT draw the card opened the
  payment dialog. Switching to anyone in credit did it, reported from
  production 2026-08-30. A return value doing double duty as data and as a
  signal rots the moment its type changes; a flag that means one thing cannot.
  It opens the existing dialog with the amount already in it: recording the payment is the step people forget, and the moment just
  after the transfer is the only one they remember it in.
  The house has no MobilePay number and does not expect one, so the deep-link
  idea is dead rather than deferred -- do not rebuild it speculatively.
  Known and deliberate: residents record their own payments, so the sheet's
  record of who has paid is a claim; the bank statement is the evidence. Making
  transfers easy makes that gap busier, not smaller.
- The fund's own position opens House's Balances (render_fund_summary,
  2026-08-30): the total, then the parts, the same shape as a person's
  statement on Me because it answers the same question one level up. Read from
  the STATUS box (AC35:AG39), matched on what each LABEL SAYS and never on a row
  number, most specific marker first -- "Bankkonto" and "Køkkenkassen I alt"
  must not be taken for each other. The sheet computes the total and the app
  never recomputes it, exactly as on Me.
  The residents' line is TURNED AROUND on screen and this is deliberate: the
  sheet's total is bank + cash MINUS the combined balance, which is negative
  while the house owes money, so printing it with its own sign beside a larger
  total reads as an arithmetic error. Facing the fund, money the house owes is
  money coming in -- "Owed by the house", positive -- and the two printed parts
  add to the printed total. A test pins that identity.
  No red/green here. That vocabulary means "what YOU owe" everywhere else in the
  app, and the per-person list sits directly below; a total is not a debt.
  The old "N of M owe the fund, X in total" caption lost its X, because that
  summed only the people who are behind while the card nets credits against
  debts -- two similar sentences carrying different numbers is how people stop
  trusting both.
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
  MONTH_STATE_KEY is PLAIN session state and MONTH_PICKER_KEY is the selectbox
  (2026-08-31). Streamlit deletes the state of a widget a run did not draw
  (SessionState._remove_stale_widgets), one run late -- measured: the value
  survives one hidden run and is gone on the second. The month used to BE the
  widget's key, so it only lived while a picker was on screen; that is why
  every page carried one, and House's Admin section, the one place that hides
  it, silently reset the month after two runs. The plain value is not widget
  state and is never collected, so the picker can be drawn once, anywhere,
  including inside a dialog. Every picker shares one widget key so two of them
  can never remember different answers.
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
  bookmark remembers you. Choosing a room CLOSES the panel: a popover does not
  close because something inside it was clicked, and st.rerun() does not close
  it either. Its open state is a widget value — but only when it is stateful,
  and `is_stateful = on_change != "ignore"` in Streamlit's layouts.py, so the
  popover is given a key AND on_change="rerun". Writing False to that value is
  then legal only before the widget is instantiated, which is what the on_click
  callback is for. It is a claim, not a login: nothing is locked to it, every
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
  per concept — dinner, host, signup, drinks, shared purchase, split bill, transfer,
  kitchen fund, balance. Never "food club" or "madklub" in the interface.
  "Shared cost" was renamed to SPLIT A BILL on 2026-08-30 and "Pay in" to TRANSFER.
  The first was not a style change: "shared cost" and "shared purchase" were nearly
  the same words for opposite mechanics — the fund pays a purchase back in full,
  while a split bill is divided between a chosen few — and naming the split is what
  tells them apart. Rename user-facing strings TOGETHER; half a rename is worse than
  none. The sheet's own name for the block stays Andet, and so do the code names.
- Drinks are counted in GLASSES of wine, not bottles. The app used to say "Bottles of
  wine" and the sheet charges 9,50 kr a unit against 6,00 for a beer (AJ25/AK25),
  which is a glass price — so anybody logging one bottle was under-reporting about
  fivefold. The sheet's own header is just "Vin" and states no unit; the unit lives
  in the price row.
- Money carries its direction in colour: kp-good (green) when the fund owes you,
  kp-owed (red) when you owe it, on the balance itself, on every line of the
  statement, and in House's list. It is the one number people open the app for.
- Controls say what they do: "Choose month", not "Another month"; "Kitchen fund
  payments", not "Paid in or out"; "Balance from last month", not "Carried in".
- A night nobody has taken is not a dead end — Dinner offers "I'll cook this
  dinner" (one tap, the common case) and "Someone else is cooking" behind a
  picker. service.claim_dinner refuses a night that already has a cook and says
  to swap instead; two people overwriting each other is what a shared sheet
  makes easy.
- An answer already given is a picture, not a form: Plan's answered view draws
  the month with render_static_grid — plain markup, no widgets, because a
  disabled Streamlit button greys its own text and thirty-one of them on a
  read-only screen is waste. Three sentences carrying a dozen dates each was
  accurate and unreadable.

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
  from one process), a 300 s retry throttle, and a fresh uncached re-check
  inside the lock. create_month_sheet re-reads the sheet list and refuses to
  make a second sheet; the copy is idempotent by design.
- A month is only "not open" when the LOG SAYS SO. read_log returns None when
  the Log cannot be read at all, and turn_if_due refuses to act on that: None
  and [] are different answers, and treating "we could not read" as "not opened
  yet" is how August 2026 got carried five times in one evening on the
  production sheet. Any read can fail — a quota burst, a renamed worksheet.
- Two different guards, and it matters which does what. _turn_attempts only
  THROTTLES: it holds a timestamp and lapses after TURN_RETRY_SECONDS, so a
  FAILED turn is tried again five minutes later -- a 503 on the 1st must not
  leave the month shut until somebody notices the banner. The cap on SUCCESS is
  _turn_completed, a set this process never empties, so the automatic turn runs
  at most ONCE per month per process even if the Log starts lying again. (Until
  2026-08-30 the cap was claimed of the throttle, which does not hold: the
  original five carries were ~40 and ~20 minutes apart, which is a lapsed
  throttle, not an absent one.) A genuine second run is a deliberate act through
  "Open the month by hand", which calls open_month directly and is not capped.
  This is a convenience, not a correctness mechanism, and it must never loop.
- None of this appears on DEV: there is no July 2026 sheet, so August is
  nothing_to_carry and the whole path is skipped. Test the turn against a month
  that has a predecessor.

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
  month, which is the one you just answered about. Verified live on 2026-08-31
  against a cook written into September on DEV.
- Each of those nights carries the SAME swap as Dinner (2026-08-31), and the
  page no longer says "ask an admin to change a night" -- it never was an
  admin's job. Sending people to Dinner instead would have cost a tab change
  AND a month change, because Dinner opens on the month you are living in
  while Plan is about the one after it. build_month_context on the planning
  sheet adds no round trip: Plan has already read that sheet's people.

Plan does not ask which month (2026-08-30). It was a 12-month dropdown crossed
with a 3-year one -- 36 combinations against the two sheets that exist -- and
picking one of the other 34 replaced the page with "Create the January 2025
sheet before planning." Because that message came from an early return, the
picker sat BELOW it and vanished with the page: one mistap in a virtualised
dropdown on a phone and the tab was dead for the session. Refresh does not
rescue it, because it clears the data caches and not the choice.

Narrowing the options to the sheets that exist was the first fix and it was the
wrong shape. The question has ONE right answer -- planning is about the month
ahead; nobody opens this tab to answer for a month at random -- so the tab
works it out instead of asking. _planning_month: next month when it has a
sheet, otherwise the month we are living in.

The fallback is not a detail. Next month's sheet only appears when an admin
first prepares it, usually in the last week, so a tab pinned to next month
would spend three weeks of every month hiding your own answer and your own
cooking nights behind "create the sheet first". It moves on by itself the day
next month is prepared -- the same moment the reminder below starts -- and says
"September is not ready to plan yet" while it waits, because an unexplained
heading on the wrong month reads as the app's mistake.

House's availability overview and Plan share this, so the overview now follows
the month being planned instead of whatever a picker on another tab was left
on. Admin is unaffected: it passes its own month and year.

The reminder to answer (rollover.unanswered_planning_month, 2026-08-30) is a
line in the accent above the admin caption, on every screen but Plan itself
-- there it is the same fact said twice, an inch from the answer. Its window
opens when NEXT MONTH'S SHEET IS PREPARED, because a sheet holding one typed
name is not a roster and there is no room to answer about yet; it closes when
they answer, and by itself when the month starts, since next_month() has moved
on by then and the month after it is not prepared. Nobody without a room on
next month's sheet is ever asked: they are not on the rota, and the default
that keeps them off it (_stored_availability) is the very thing a nudge would
undo. Whose room it is is resolved through the NAME, for the reason under
Planning sheet identity. Costs nothing for most of the month -- the first gate
is "does next month's sheet exist", which is answered from the cached sheet
list -- and two cached reads inside the window. Every read there is wrapped:
a nudge that takes the page down when the Planning sheet is briefly unreadable
is worse than no nudge.

Two grey captions stacked read as one paragraph, so the reminder wears
.kp-nudge (the accent, 600) and the house's status line stays grey. It is not a
button: the nav bar is at the top, so Plan is already an inch above the line
telling you to open it.

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
which puts `src/` on the path. Things about that environment that have bitten:

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
- That pickling error has a SECOND, unrelated cause, and the timestamp tells
  them apart: a deploy. Cloud does not restart the process — Streamlit's watcher
  deletes every one of our modules from sys.modules (all of them, not just the
  changed one: see watcher/local_sources_watcher.py) and the next run re-imports
  the tree. st.session_state survives that, so the SheetsService in it belongs
  to the old code and keeps minting old-class dataclasses that pickle refuses.
  Symptom: `PicklingError: ... it's not the same object as
  kitchenpal.sheets.models.RoomEntry`, arriving in the same second as
  "🔄 Updated app!". get_cached_service now keeps the RoomEntry class the
  connection was built against — resolved through sys.modules, because that
  lookup IS what pickle does — and rebuilds the connection when it no longer
  matches. Anything else cached across a deploy is fine: values pickled under
  the old class unpickle into the new one by name.
- The same eviction has a THIRD symptom, and it is not ours to fix:
  `KeyError: 'kitchenpal.constants'` raised from importlib's _bootstrap at
  `module = sys.modules.pop(spec.name)`. The module had finished executing; the
  watcher thread deleted it from sys.modules while the script thread was still
  importing it. It can only happen in the second a deploy lands (check the
  timestamps against the "Pulling code changes" line), it recovers on the next
  run, and NO code of ours can catch it — it dies importing app.py, before a
  line of the app runs. Do not chase it. If it ever becomes a nuisance,
  `server.fileWatcherType = "none"` removes the watcher and all three symptoms
  at once, but Cloud appears to rely on that watcher to pick up pulled code, so
  a push might then do nothing until a reboot. Untested; verify a deploy
  actually lands before trusting it.
- Google is occasionally unavailable, and nothing used to catch it: four
  `APIError: [503]` in one evening each showed a resident a traceback and a dead
  page. sheets/transient.py decides what is worth retrying (5xx and 429; never
  403/404, which will still be true in half a second), retry_reads wraps the
  connect and worksheet lookups, and run_app turns an APIError into a sentence
  plus a Try again button. NEVER wrap a WRITE in retry_reads: a 5xx on a write
  is ambiguous, the write may have landed, and a retry charges someone's dinner
  twice. Writes get the error and let the person press the button again.
- Streamlit deprecations show up in the Cloud log long before they break the
  app. `use_container_width` became `width="stretch"` / `width="content"`;
  test_resilience.py fails if it comes back.

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