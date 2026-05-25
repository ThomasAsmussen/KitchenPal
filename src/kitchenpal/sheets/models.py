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
class FeedbackEntry:
    row_number: int
    created_at: str
    name: str
    title: str
    details: str
    status: str
