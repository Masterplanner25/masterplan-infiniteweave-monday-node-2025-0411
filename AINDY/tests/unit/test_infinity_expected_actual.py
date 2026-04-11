from AINDY.domain.infinity_loop import _build_expectation, _derive_actual_outcome


def test_build_expectation_sets_expected_outcome_and_score():
    expected_outcome, expected_score = _build_expectation(
        "continue_highest_priority_task",
        {"master_score": 62.0},
    )

    assert expected_outcome == "task_progress"
    assert expected_score == 65


def test_derive_actual_outcome_maps_completion_to_task_progress():
    assert _derive_actual_outcome("task_completion") == "task_progress"
    assert _derive_actual_outcome("agent_completed") == "task_progress"

