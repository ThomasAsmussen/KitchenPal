from dataclasses import dataclass


@dataclass(frozen=True)
class PlanningEntry:
    person: str
    room_number: str
    available_dates: str
    unavailable_dates: str
    preferred_dates: str
    limit_one_day: bool


@dataclass(frozen=True)
class RoomEntry:
    label: str
    name: str
    account_row: int
    signup_column: int | None


@dataclass(frozen=True)
class PersonalAccountEntry:
    label: str
    name: str
    row_number: int
    balance: float


@dataclass(frozen=True)
class DrinkEntry:
    row_number: int
    room: str
    name: str
    beer_soda: int
    wine: int


@dataclass(frozen=True)
class PurchaseEntry:
    row_number: int
    room: str
    date: str
    item: str
    amount: float


@dataclass(frozen=True)
class TransactionEntry:
    row_number: int
    room: str
    date: str
    transaction_type: str
    amount: float


@dataclass(frozen=True)
class DayToDayEntries:
    drinks: list[DrinkEntry]
    purchases: list[PurchaseEntry]
    transactions: list[TransactionEntry]


@dataclass(frozen=True)
class AccountStatement:
    """A person's month: the closing balance and the parts that made it."""

    label: str
    name: str
    balance: float
    components: dict


@dataclass(frozen=True)
class AndetRow:
    """A shared cost with no date: who paid, what it was, and who was in on it."""

    row_number: int
    payer: str
    description: str
    amount: float
    participants: dict

    @property
    def head_count(self) -> int:
        return sum(self.participants.values())

    @property
    def share(self) -> float:
        return self.amount / self.head_count if self.head_count else 0.0


@dataclass(frozen=True)
class DayRow:
    """One dinner day, read with the whole month in a single call."""

    day: int
    chef: str
    menu: str
    menu_description: str
    signed_up: int
    meal_price: float
    signups: dict


@dataclass(frozen=True)
class DaySummary:
    chef: str
    menu: str
    signed_up: str
    meal_price: float
    menu_description: str


@dataclass(frozen=True)
class FeedbackEntry:
    row_number: int
    created_at: str
    name: str
    title: str
    details: str
    status: str


@dataclass(frozen=True)
class BankDetails:
    """Where to send money to the kitchen fund.

    `text` is the cell exactly as a human wrote it and is always filled; the two
    numbers are filled only when they could be told apart. A house maintains
    that cell by hand, so the raw line is the fallback that always works.
    """

    reg_number: str
    account_number: str
    text: str
