import calendar
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional


SCHEDULING_WEEKDAYS = {
    "sunday": 6,
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
}


@dataclass(frozen=True)
class ScheduleResult:
    assignments: Dict[int, str]
    unassigned_people: List[str]


def get_weekdays_in_month(year: int, month: int) -> List[int]:
    days = []
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        if calendar.weekday(year, month, day) in [6, 0, 1, 2, 3]:
            days.append(day)
    return days


def get_days_of_week_in_month(year: int, month: int, weekday_name: str) -> List[int]:
    weekday_index = SCHEDULING_WEEKDAYS[weekday_name.lower()]
    days = []
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        if calendar.weekday(year, month, day) == weekday_index:
            days.append(day)
    return days


def parse_dates(date_list: Iterable[str], year: int, month: int) -> List[int]:
    result_dates = []

    for date in date_list:
        date = date.strip()
        if not date:
            continue

        if date.isdigit():
            result_dates.append(int(date))
        elif "-" in date:
            start, end = map(int, date.split("-", maxsplit=1))
            result_dates.extend(range(start, end + 1))
        elif date.lower() in SCHEDULING_WEEKDAYS:
            result_dates.extend(get_days_of_week_in_month(year, month, date))

    return result_dates


def split_date_input(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _spacing_penalty(days_apart: int) -> int:
    if days_apart >= 7:
        return 0
    return (7 - days_apart) * 5


def combine_availability(
    available: Dict[str, List[str]],
    unavailable: Dict[str, List[str]],
    year: int,
    month: int,
) -> Dict[str, List[int]]:
    weekdays_in_month = get_weekdays_in_month(year, month)
    final_availability = {}

    for person in set(available.keys()).union(unavailable.keys()):
        parsed_available_dates = parse_dates(available.get(person, []), year, month)
        parsed_unavailable_dates = parse_dates(unavailable.get(person, []), year, month)

        if not parsed_available_dates:
            parsed_available_dates = weekdays_in_month

        final_available_dates = [
            day
            for day in parsed_available_dates
            if day in weekdays_in_month and day not in parsed_unavailable_dates
        ]
        final_availability[person] = sorted(set(final_available_dates))

    return final_availability


def schedule_people(
    available_days: Dict[str, List[int]],
    preferences: Dict[str, List[int]],
    possible_days: List[int],
    limit_one_day_per_person: Dict[str, bool],
) -> Optional[ScheduleResult]:
    from ortools.sat.python import cp_model

    if not available_days or not possible_days:
        return None

    people = list(available_days.keys())
    ordered_days = sorted(set(possible_days))
    model = cp_model.CpModel()
    schedule = {day: model.NewIntVar(0, len(people) - 1, f"schedule_{day}") for day in ordered_days}

    for person_index, person in enumerate(people):
        for day in ordered_days:
            if day not in available_days[person]:
                model.Add(schedule[day] != person_index)

    assigned_by_person = {}
    limit_penalties = []
    spacing_penalties = []
    for person_index, person in enumerate(people):
        assigned_days = []
        assigned_day_vars = {}
        for day in ordered_days:
            assigned = model.NewBoolVar(f"assigned_{person_index}_{day}")
            model.Add(schedule[day] == person_index).OnlyEnforceIf(assigned)
            model.Add(schedule[day] != person_index).OnlyEnforceIf(assigned.Not())
            assigned_days.append(assigned)
            assigned_day_vars[day] = assigned

        assigned_by_person[person] = assigned_days
        max_days = 1 if limit_one_day_per_person.get(person, False) else 2
        extra_days = model.NewIntVar(0, len(ordered_days), f"extra_days_{person_index}")
        model.Add(extra_days >= sum(assigned_days) - max_days)
        model.Add(extra_days >= 0)
        limit_penalties.append(extra_days)

        for left_index, left_day in enumerate(ordered_days):
            for right_day in ordered_days[left_index + 1 :]:
                gap = right_day - left_day
                if gap >= 7:
                    break

                both_assigned = model.NewBoolVar(f"both_assigned_{person_index}_{left_day}_{right_day}")
                model.AddBoolAnd([assigned_day_vars[left_day], assigned_day_vars[right_day]]).OnlyEnforceIf(both_assigned)
                model.AddBoolOr([assigned_day_vars[left_day].Not(), assigned_day_vars[right_day].Not(), both_assigned])
                spacing_penalties.append(_spacing_penalty(gap) * both_assigned)

    unassigned_penalties = []
    for person_index, person in enumerate(people):
        has_assignment = model.NewBoolVar(f"has_assignment_{person_index}")
        model.Add(sum(assigned_by_person[person]) >= 1).OnlyEnforceIf(has_assignment)
        model.Add(sum(assigned_by_person[person]) == 0).OnlyEnforceIf(has_assignment.Not())
        unassigned_penalties.append(has_assignment.Not())

    preferred_assignments = []
    for person_index, person in enumerate(people):
        for day in preferences.get(person, []):
            if day in ordered_days:
                preferred = model.NewBoolVar(f"preferred_{person_index}_{day}")
                model.Add(schedule[day] == person_index).OnlyEnforceIf(preferred)
                model.Add(schedule[day] != person_index).OnlyEnforceIf(preferred.Not())
                preferred_assignments.append(preferred)

    unassigned_penalty_weight = 1000
    extra_day_penalty_weight = 80
    model.Minimize(
        unassigned_penalty_weight * sum(unassigned_penalties)
        + extra_day_penalty_weight * sum(limit_penalties)
        + sum(spacing_penalties)
        - sum(preferred_assignments)
    )

    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        return None

    assignments = {day: people[solver.Value(schedule[day])] for day in ordered_days}
    unassigned_people = [
        person for person, assigned_days in assigned_by_person.items() if not any(solver.Value(day) for day in assigned_days)
    ]
    return ScheduleResult(assignments=assignments, unassigned_people=unassigned_people)
