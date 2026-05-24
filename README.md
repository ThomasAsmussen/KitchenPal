# KitchenPal

## Run the app

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Make sure the credentials file exists in the project root, or set:

- `GOOGLE_CREDENTIALS_FILE`
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