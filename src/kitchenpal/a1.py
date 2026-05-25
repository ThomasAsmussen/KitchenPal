import re


def range_start_row(a1_range: str, default: int = 1) -> int:
    match = re.search(r"(\d+)$", a1_range.split(":")[0])
    return int(match.group(1)) if match else default


def range_end_row(a1_range: str, default: int | None = None) -> int:
    match = re.search(r"(\d+)$", a1_range.split(":")[-1])
    if match:
        return int(match.group(1))
    if default is not None:
        return default
    return range_start_row(a1_range)
