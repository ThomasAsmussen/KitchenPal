# KitchenPal

## Purpose

KitchenPal is a Streamlit app that provides a friendly interface on top of an
existing Google Sheet for running a shared kitchen or food club. It keeps the
spreadsheet as the source of truth while making day-to-day registrations,
monthly setup, balance transfers, and host planning easier to manage.

The month planner uses Google OR-Tools CP-SAT optimization to turn each person's
availability, unavailable days, preferred days, and hosting limits into a
suggested schedule. The optimizer first tries to assign everyone at least once,
then avoids overusing people, spaces repeated assignments about a week apart,
and gives a small preference to requested days.

## Run the app

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Make sure the credentials file exists in the project root, or set:

- `GOOGLE_CREDENTIALS_FILE`
- `GOOGLE_CREDENTIALS_JSON`
- `KITCHEN_SPREADSHEET_NAME`
- `KITCHEN_TEMPLATE_SHEET`

3. Run the app:

```bash
streamlit run streamlit_app.py
```

## Test

Install test dependencies and run tests:

```bash
pip install -e .[test]
pytest -q
```

CI is also configured in `.github/workflows/ci.yml`, which runs tests on pushes and pull requests.

## Deploy

The app can run on Streamlit Community Cloud without committing the Google service-account JSON file.

1. Share the Google Sheet with the service account's `client_email`.
2. Push the app to GitHub. Do not commit `koekkenregnskab-3d-ny-040a2ee5b105.json` or `.streamlit/secrets.toml`.
3. In Streamlit Community Cloud, create an app from this repository with `streamlit_app.py` as the entrypoint.
4. In Advanced settings, paste secrets like:

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

Locally, you can use the same format in `.streamlit/secrets.toml`, or keep using `GOOGLE_CREDENTIALS_FILE`.

## Structure

```
src/kitchenpal/
  app.py
  config.py
  constants.py
  sheets_service.py
  ui/
    day_to_day.py
    month_setup.py
streamlit_app.py
```

Todo:
Change to cannot host when box is selected
Make save request individual
Delete names seperated by commas
Delete FL and daniel from signup
Create new month tab bugs
Fix purchase and transfers
