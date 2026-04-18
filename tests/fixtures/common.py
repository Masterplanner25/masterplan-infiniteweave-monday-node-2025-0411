from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_openai(mocker):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"reply": "test", "state_update": {}, "synthesis_ready": false}'
    mock_client.chat.completions.create.return_value = mock_response
    mocker.patch("openai.OpenAI", return_value=mock_client)
    return mock_client


@pytest.fixture
def sample_task_input():
    from apps.analytics.schemas.analytics_inputs import TaskInput

    return TaskInput(
        task_name="Test Task",
        time_spent=2.0,
        task_complexity=3,
        skill_level=4,
        ai_utilization=3,
        task_difficulty=2,
    )


@pytest.fixture
def sample_engagement_input():
    from apps.analytics.schemas.analytics_inputs import EngagementInput

    return EngagementInput(
        likes=100,
        shares=50,
        comments=30,
        clicks=200,
        time_on_page=45.0,
        total_views=1000,
    )
