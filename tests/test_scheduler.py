from kitchenpal.scheduler import schedule_people


def test_schedule_people_never_exceeds_one_day_limit():
    result = schedule_people(
        available_days={"Alex": [1, 2]},
        preferences={},
        possible_days=[1, 2],
        limit_one_day_per_person={"Alex": True},
    )

    assert result is not None
    assert set(result.assignments.values()) == {"Alex"}
    assert len(result.assignments) == 1
    assert result.unassigned_people == []
    assert len(result.unassigned_days) == 1


def test_schedule_people_leaves_days_open_instead_of_assigning_a_third_day():
    result = schedule_people(
        available_days={"Alex": [1, 2, 3], "Blair": [1, 2, 3]},
        preferences={},
        possible_days=[1, 2, 3],
        limit_one_day_per_person={},
    )

    assert result is not None
    assert len(result.assignments) == 3
    assert all(
        list(result.assignments.values()).count(person) <= 2
        for person in ("Alex", "Blair")
    )
    assert result.unassigned_days == []


def test_schedule_people_reports_unassigned_days_when_capacity_is_too_low():
    result = schedule_people(
        available_days={"Alex": [1, 2, 3, 4, 5]},
        preferences={},
        possible_days=[1, 2, 3, 4, 5],
        limit_one_day_per_person={},
    )

    assert result is not None
    assert len(result.assignments) == 2
    assert len(result.unassigned_days) == 3
    assert set(result.assignments).isdisjoint(result.unassigned_days)


def test_schedule_people_prefers_week_apart_assignments():
    result = schedule_people(
        available_days={"Alex": [1, 4, 8], "Blair": [1, 4, 8]},
        preferences={"Alex": [4], "Blair": [8]},
        possible_days=[1, 4, 8],
        limit_one_day_per_person={},
    )

    assert result is not None
    assert result.assignments == {1: "Blair", 4: "Alex", 8: "Blair"}
