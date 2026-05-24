ROOM_NUMBERS = list(range(346, 361))

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

ROOM_TO_ROW_INDEX = {
    346: 3,
    347: 4,
    348: 5,
    349: 6,
    350: 7,
    351: 8,
    352: 9,
    353: 10,
    354: 11,
    355: 12,
    356: 13,
    357: 14,
    358: 15,
    359: 16,
    360: 17,
}

DAY_SHEET_FIRST_DAY_ROW = 3
DAY_SHEET_DAY_OFFSET = 2
DAY_SHEET_COOK_COLUMN = 3
DAY_SHEET_MENU_COLUMN = 4
DAY_SHEET_SIGNUP_TOTAL_COLUMN = 7
DAY_SHEET_FIRST_ROOM_COLUMN = 9
DAY_SHEET_ROOM_COLUMN_OFFSET = 6
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

TRANSACTION_LOOKUP_RANGE = "AC44:AC55"
TRANSACTION_INSERT_START_COLUMN = "AC"
TRANSACTION_INSERT_END_COLUMN = "AE"
TRANSACTION_AMOUNT_COLUMN = "AG"

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
