PERSON_TO_ROOM = {
    "Philip": 346,
    "August": 347,
    "Frederik": 348,
    "Josefine": 349,
    "Amalie": 350,
    "Asta": 351,
    "Sofie A": 352,
    "Sofie G": 353,
    "Alberte": 354,
    "Sylvester": 355,
    "Cecilie": 356,
    "Julia": 357,
    "Thor": 358,
    "Thomas": 359,
    "Henriette": 360,
}

DAY_SHEET_DAY_OFFSET = 2
DAY_SHEET_MENU_COLUMN = 4
DAY_SHEET_SIGNUP_HEADER_RANGE = "I2:AA2"

PERSONAL_ACCOUNT_BEER_COLUMN = 35
PERSONAL_ACCOUNT_WINE_COLUMN = 36
PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE = "Y45:Y65"
PERSONAL_ACCOUNT_SHEET_ACCOUNT_CELL = "AF37"
PERSONAL_ACCOUNT_TABLE_RANGE = "A45:B65"
PERSONAL_ACCOUNT_TABLE_START_ROW = 45

PURCHASE_LOOKUP_RANGE = "Y2:Y200"
PURCHASE_INSERT_START_COLUMN = "Y"
PURCHASE_INSERT_END_COLUMN = "AB"

TRANSACTION_LOOKUP_RANGE = "AB44:AB55"
TRANSACTION_INSERT_START_COLUMN = "AB"
TRANSACTION_INSERT_END_COLUMN = "AD"
TRANSACTION_AMOUNT_COLUMN = "AF"

PLANNING_SHEET_NAME = "Planning"
PLANNING_HEADERS = ["Year", "Month", "Name", "Room", "Can", "Cannot", "Prefers", "Max 1 day"]

ENGLISH_MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

MONTH_TO_NUMBER = {month: index + 1 for index, month in enumerate(ENGLISH_MONTHS)}
