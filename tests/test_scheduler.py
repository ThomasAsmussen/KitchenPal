from kitchenpal.scheduler import schedule_people


def test_schedule_people_allows_exceeding_day_limit_with_penalty():
    result = schedule_people(
        available_days={"Alex": [1, 2]},
        preferences={},
        possible_days=[1, 2],
        limit_one_day_per_person={"Alex": True},
    )

    assert result is not None
    assert result.assignments == {1: "Alex", 2: "Alex"}
    assert result.unassigned_people == []


def test_schedule_people_prefers_week_apart_assignments():
    result = schedule_people(
        available_days={"Alex": [1, 4, 8], "Blair": [1, 4, 8]},
        preferences={"Alex": [4], "Blair": [8]},
        possible_days=[1, 4, 8],
        limit_one_day_per_person={},
    )

    assert result is not None
    assert result.assignments == {1: "Blair", 4: "Alex", 8: "Blair"}