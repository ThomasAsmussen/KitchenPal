from datetime import datetime, timedelta


def get_next_month_name(reference_date: datetime | None = None) -> str:
    today = reference_date or datetime.now()
    first_day_next_month = today.replace(day=1) + timedelta(days=32)
    return first_day_next_month.strftime("%B %Y")


if __name__ == "__main__":
    current_time = datetime.now()
    print(current_time.strftime("%Y %B %d, %H:%M"))
    print(get_next_month_name())
