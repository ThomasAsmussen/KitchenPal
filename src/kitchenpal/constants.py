from dataclasses import dataclass


@dataclass(frozen=True)
class PersonalAccountLayout:
    beer_column: int
    wine_column: int
    balance_range: str
    previous_balance_range: str
    previous_balance_column: int
    account_cell: str
    table_range: str
    table_start_row: int
    kovs_header_range: str
    kovs_search_start_row: int
    kovs_search_end_row: int
    transaction_total_range: str


@dataclass(frozen=True)
class TransactionTableLayout:
    lookup_range: str
    table_range: str
    insert_start_column: str
    insert_end_column: str
    amount_column: str


@dataclass(frozen=True)
class DaySheetLayout:
    day_offset: int
    menu_column: int
    signup_header_range: str
    drink_table_range: str


@dataclass(frozen=True)
class PlanningLayout:
    sheet_name: str
    header_range: str
    headers: list[str]


@dataclass(frozen=True)
class SheetLayout:
    day: DaySheetLayout
    personal_account: PersonalAccountLayout
    purchases: TransactionTableLayout
    transactions: TransactionTableLayout
    planning: PlanningLayout


SHEET_LAYOUT = SheetLayout(
    day=DaySheetLayout(
        day_offset=2,
        menu_column=4,
        signup_header_range="I2:AA2",
        drink_table_range="AI3:AK21",
    ),
    personal_account=PersonalAccountLayout(
        beer_column=36,
        wine_column=37,
        balance_range="Z45:Z65",
        previous_balance_range="I45:I65",
        previous_balance_column=9,
        account_cell="AG37",
        table_range="A45:B65",
        table_start_row=45,
        kovs_header_range="A1:AZ1",
        kovs_search_start_row=3,
        kovs_search_end_row=300,
        transaction_total_range="AG44:AG55",
    ),
    purchases=TransactionTableLayout(
        lookup_range="AC2:AC43",
        table_range="AC3:AG43",
        insert_start_column="AC",
        insert_end_column="AE",
        amount_column="AG",
    ),
    transactions=TransactionTableLayout(
        lookup_range="AC44:AC55",
        table_range="AC44:AG200",
        insert_start_column="AC",
        insert_end_column="AE",
        amount_column="AG",
    ),
    planning=PlanningLayout(
        sheet_name="Planning",
        header_range="A1:H1",
        headers=["Year", "Month", "Name", "Room", "Can", "Cannot", "Prefers", "Max 1 day"],
    ),
)


DAY_SHEET_DAY_OFFSET = SHEET_LAYOUT.day.day_offset
DAY_SHEET_MENU_COLUMN = SHEET_LAYOUT.day.menu_column
DAY_SHEET_SIGNUP_HEADER_RANGE = SHEET_LAYOUT.day.signup_header_range

PERSONAL_ACCOUNT_BEER_COLUMN = SHEET_LAYOUT.personal_account.beer_column
PERSONAL_ACCOUNT_WINE_COLUMN = SHEET_LAYOUT.personal_account.wine_column
PERSONAL_ACCOUNT_SHEET_BALANCE_RANGE = SHEET_LAYOUT.personal_account.balance_range
PERSONAL_ACCOUNT_SHEET_PREVIOUS_BALANCE_RANGE = SHEET_LAYOUT.personal_account.previous_balance_range
PERSONAL_ACCOUNT_PREVIOUS_BALANCE_COLUMN = SHEET_LAYOUT.personal_account.previous_balance_column
PERSONAL_ACCOUNT_SHEET_ACCOUNT_CELL = SHEET_LAYOUT.personal_account.account_cell
PERSONAL_ACCOUNT_TABLE_RANGE = SHEET_LAYOUT.personal_account.table_range
PERSONAL_ACCOUNT_TABLE_START_ROW = SHEET_LAYOUT.personal_account.table_start_row
PERSONAL_ACCOUNT_KOVS_HEADER_RANGE = SHEET_LAYOUT.personal_account.kovs_header_range
PERSONAL_ACCOUNT_KOVS_SEARCH_START_ROW = SHEET_LAYOUT.personal_account.kovs_search_start_row
PERSONAL_ACCOUNT_KOVS_SEARCH_END_ROW = SHEET_LAYOUT.personal_account.kovs_search_end_row
PERSONAL_ACCOUNT_TRANSACTION_TOTAL_RANGE = SHEET_LAYOUT.personal_account.transaction_total_range

DRINK_TABLE_RANGE = SHEET_LAYOUT.day.drink_table_range

PURCHASE_LOOKUP_RANGE = SHEET_LAYOUT.purchases.lookup_range
PURCHASE_TABLE_RANGE = SHEET_LAYOUT.purchases.table_range
PURCHASE_INSERT_START_COLUMN = SHEET_LAYOUT.purchases.insert_start_column
PURCHASE_INSERT_END_COLUMN = SHEET_LAYOUT.purchases.insert_end_column
PURCHASE_AMOUNT_COLUMN = SHEET_LAYOUT.purchases.amount_column

TRANSACTION_LOOKUP_RANGE = SHEET_LAYOUT.transactions.lookup_range
TRANSACTION_TABLE_RANGE = SHEET_LAYOUT.transactions.table_range
TRANSACTION_INSERT_START_COLUMN = SHEET_LAYOUT.transactions.insert_start_column
TRANSACTION_INSERT_END_COLUMN = SHEET_LAYOUT.transactions.insert_end_column
TRANSACTION_AMOUNT_COLUMN = SHEET_LAYOUT.transactions.amount_column

PLANNING_SHEET_NAME = SHEET_LAYOUT.planning.sheet_name
PLANNING_HEADER_RANGE = SHEET_LAYOUT.planning.header_range
PLANNING_HEADERS = SHEET_LAYOUT.planning.headers
POSSIBLE_DAYS_SHEET_NAME = "Possible Days"
POSSIBLE_DAYS_HEADER_RANGE = "A1:C1"
POSSIBLE_DAYS_HEADERS = ["Year", "Month", "Limit days"]
MONTH_METADATA_RANGE = "AR3:AS3"

NEW_FEATURES_SHEET_NAME = "New Features"
BUGS_SHEET_NAME = "Bugs"
FEEDBACK_HEADER_RANGE = "A1:E1"
FEEDBACK_HEADERS = ["Created At", "Name", "Title", "Details", "Status"]
FEEDBACK_STATUS_COLUMN = "E"

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

DANISH_MONTHS = [
    "Januar",
    "Februar",
    "Marts",
    "April",
    "Maj",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "December",
]

DANISH_TO_ENGLISH_MONTH = dict(zip(DANISH_MONTHS, ENGLISH_MONTHS))
ENGLISH_TO_DANISH_MONTH = dict(zip(ENGLISH_MONTHS, DANISH_MONTHS))

MONTH_TO_NUMBER = {
    **{month: index + 1 for index, month in enumerate(ENGLISH_MONTHS)},
    **{month: index + 1 for index, month in enumerate(DANISH_MONTHS)},
}
