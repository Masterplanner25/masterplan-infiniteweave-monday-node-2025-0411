from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_post_ai_productivity_boost():
    payload = {
        "tasks_with_ai": 100,
        "tasks_without_ai": 40,
        "time_saved": 10
    }
    response = client.post("/ai_productivity_boost", json=payload)
    assert response.status_code == 200
    assert "AI Productivity Boost" in response.json()

def test_post_income_efficiency():
    payload = {
        "focused_effort": 50,
        "ai_utilization": 5,
        "time": 10,
        "capital": 5
    }
    response = client.post("/income_efficiency", json=payload)
    assert response.status_code == 200
    assert "Income Efficiency" in response.json()

def test_post_execution_speed():
    payload = {
        "ai_automations": 10,
        "systemized_workflows": 5,
        "decision_lag": 5
    }
    response = client.post("/execution_speed", json=payload)
    assert response.status_code == 200
    assert "Execution Speed" in response.json()

def test_post_engagement_rate():
    payload = {
        "total_interactions": 500,
        "total_views": 1000
    }
    response = client.post("/engagement_rate", json=payload)
    assert response.status_code == 200
    assert "Engagement Rate" in response.json()

def test_post_lost_potential():
    payload = {
        "missed_opportunities": 10,
        "time_delayed": 2,
        "gains_from_action": 5
    }
    response = client.post("/lost_potential", json=payload)
    assert response.status_code == 200
    assert "Lost Potential" in response.json()

def test_post_decision_efficiency():
    payload = {
        "automated_decisions": 50,
        "manual_decisions": 5,
        "processing_time": 5
    }
    response = client.post("/decision_efficiency", json=payload)
    assert response.status_code == 200
    assert "Decision Efficiency" in response.json()

def test_post_batch_calculations():
    payload = {
        "ai_productivity_boost": [{
            "tasks_with_ai": 120,
            "tasks_without_ai": 60,
            "time_saved": 15
        }],
        "lost_potential": [{
            "missed_opportunities": 5,
            "time_delayed": 3,
            "gains_from_action": 2
        }],
        "decision_efficiency": [{
            "automated_decisions": 30,
            "manual_decisions": 10,
            "processing_time": 5
        }],
        "tasks": [{
            "task_name": "Test Task",
            "time_spent": 5,
            "task_complexity": 2.0,
            "skill_level": 3.0,
            "ai_utilization": 2,
            "task_difficulty": 2.0
        }],
        "engagements": [{
            "likes": 10,
            "shares": 5,
            "comments": 3,
            "clicks": 20,
            "time_on_page": 120.0,
            "total_views": 500
        }],
        "ai_efficiencies": [{
            "ai_contributions": 80,
            "human_contributions": 20,
            "total_tasks": 100
        }],
        "impacts": [{
            "reach": 1000,
            "engagement": 150,
            "conversion": 30
        }],
        "efficiencies": [{
            "focused_effort": 40,
            "ai_utilization": 2,
            "time": 12,
            "capital": 6
        }],
        "revenue_scalings": [{
            "ai_leverage": 1.5,
            "content_distribution": 2.0,
            "time": 5.0,
            "audience_engagement": 2
        }],
        "execution_speeds": [{
            "ai_automations": 8,
            "systemized_workflows": 4,
            "decision_lag": 4
        }],
        "attention_values": [{
            "content_output": 10,
            "platform_presence": 5,
            "time": 2
        }],
        "engagement_rates": [{
            "total_interactions": 300,
            "total_views": 1000
        }],
        "business_growths": [{
            "revenue": 10000,
            "expenses": 4000,
            "scaling_friction": 2.0
        }],
        "monetization_efficiencies": [{
            "total_revenue": 20000,
            "audience_size": 5000
        }]
    }
    response = client.post("/batch_calculations", json=payload)
    print(response.json())
    assert response.status_code == 200
    assert isinstance(response.json(), dict)
    assert "AI Productivity Boost" in response.json()

def test_get_results():
    response = client.get("/results")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
