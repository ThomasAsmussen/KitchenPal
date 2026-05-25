# KitchenPal

KitchenPal is a Streamlit app that provides a friendly interface on top of an
existing Google Sheet for running a shared kitchen or food club. The spreadsheet
stays the source of truth, while the app makes common workflows easier, safer,
and faster than editing sheet cells directly.

## What It Does

- Sign rooms up for food club and show the current menu, host, signup count, and
  budget.
- Register dishes, drinks, purchases, and transfers for a selected month sheet.
- Create new month sheets from a template and transfer balances from the
  previous month.
- Manage room residents and FL accounts.
- Collect feature suggestions and bug reports in dedicated feedback sheets.
- Plan who hosts food club using availability and preference data.

## Planning Optimization

The month planner uses Google OR-Tools CP-SAT optimization. For each month, it
takes the possible food club days, each person's available and unavailable days,
preferred days, and whether they should host at most once.

The optimizer searches for a feasible schedule and minimizes a weighted
objective:

- assign as many people as possible at least once;
- avoid assigning people more than their configured limit;
- avoid repeated assignments that are less than about a week apart;
- give a small bonus to preferred days.

This means the generated schedule is not just the first valid assignment it can
find. It is chosen to balance fairness, spacing, hard availability constraints,
and individual preferences.

## Requirements

- Python 3.10 or newer
- Access to a Google Sheet with the expected KitchenPal layout
- A Google service account with access to that sheet

Runtime dependencies are listed in `requirements.txt` and `pyproject.toml`.

## Local Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

For development and tests, install the package in editable mode with test
dependencies:

```bash
pip install -e .[test]
```

2. Configure Google Sheets access.

The app can read credentials from either a local JSON file, environment
variables, or Streamlit secrets.

Default local file:

```text
koekkenregnskab-3d-ny-040a2ee5b105.json
```

Supported environment variables:

```bash
GOOGLE_CREDENTIALS_FILE=path/to/service-account.json
GOOGLE_CREDENTIALS_JSON='{"type":"service_account", ...}'
KITCHEN_SPREADSHEET_NAME="Køkkenregnskab 3D ny"
KITCHEN_TEMPLATE_SHEET="Skabelon"
```

Make sure the Google Sheet is shared with the service account's `client_email`.

3. Run the app:

```bash
streamlit run streamlit_app.py
```

## Streamlit Secrets

For local Streamlit secrets or Streamlit Community Cloud, use this shape:

```toml
[app]
spreadsheet_name = "Køkkenregnskab 3D ny"
template_sheet_name = "Skabelon"

[google_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = """-----BEGIN PRIVATE KEY-----
...
-----END PRIVATE KEY-----
"""
client_email = "..."
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
```

Locally, place this in `.streamlit/secrets.toml` if you do not want to use a
credentials JSON file.

## Google Sheet Structure

KitchenPal expects a workbook built around monthly sheets and a few support
sheets:

- Monthly sheets named like `May 2026` or `Maj 2026`.
- A template sheet, configured by `KITCHEN_TEMPLATE_SHEET`, used when creating a
  new month.
- `Planning`, used to store monthly host availability and preferences.
- `Possible Days`, used to store optional per-month planning day limits.
- `New Features` and `Bugs`, used by the feedback view.

The exact cell ranges and table positions are defined in
`src/kitchenpal/constants.py`.

## App Views

The sidebar has three main areas:

- `Day to day`: signups, dish names, drinks, purchases, and kitchen fund
  transfers.
- `Create new month`: month creation, balance carryover, people management, and
  host planning.
- `Feedback`: feature suggestions and bug reports.

Use the sidebar `Refresh data` button if the underlying Google Sheet was edited
outside the app and the current view looks stale.

## Tests

Run the test suite with:

```bash
pytest -q
```

CI is configured in `.github/workflows/ci.yml` and runs the tests on pushes and
pull requests.

## Deployment

The app can run on Streamlit Community Cloud without committing any service
account JSON file.

1. Share the Google Sheet with the service account's `client_email`.
2. Push the app to GitHub.
3. Create a Streamlit Community Cloud app from this repository.
4. Use `streamlit_app.py` as the entrypoint.
5. Add the Streamlit secrets shown above in the app's advanced settings.

Do not commit local credentials such as
`koekkenregnskab-3d-ny-040a2ee5b105.json` or `.streamlit/secrets.toml`.

## Project Structure

```text
.
|-- streamlit_app.py          # Streamlit entrypoint
|-- requirements.txt          # Runtime dependencies
|-- pyproject.toml            # Package metadata and test extras
|-- src/kitchenpal/
|   |-- app.py                # App routing
|   |-- config.py             # Environment and secrets configuration
|   |-- constants.py          # Sheet layout and range definitions
|   |-- scheduler.py          # OR-Tools scheduling optimization
|   |-- sheets_service.py     # Google Sheets service facade
|   |-- sheets/               # Sheet-specific read/write logic
|   `-- ui/                   # Streamlit views
`-- tests/                    # Unit tests
```

## Development Notes

- Keep Google Sheets layout changes in sync with `src/kitchenpal/constants.py`
  and the sheet layout tests.
- Prefer adding tests when changing scheduler behavior, sheet ranges, or
  Google Sheets write logic.
- Month names can be English or Danish; helper functions normalize both where
  needed.
