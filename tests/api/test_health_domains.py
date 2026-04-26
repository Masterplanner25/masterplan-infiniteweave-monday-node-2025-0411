from __future__ import annotations


def test_health_domains_returns_200_when_all_checks_pass(client, monkeypatch):
    from AINDY.platform_layer.domain_health import domain_health_registry

    original = dict(domain_health_registry._checks)
    monkeypatch.setattr(
        domain_health_registry,
        "_checks",
        {
            "analytics": lambda: True,
            "automation": lambda: True,
        },
    )
    try:
        response = client.get("/health/domains")
    finally:
        monkeypatch.setattr(domain_health_registry, "_checks", original)

    assert response.status_code == 200
    body = response.json()
    assert body["domains"]["analytics"]["healthy"] is True
    assert body["domains"]["automation"]["error"] is None


def test_health_domains_returns_207_when_one_check_fails(client, monkeypatch):
    from AINDY.platform_layer.domain_health import domain_health_registry

    original = dict(domain_health_registry._checks)
    monkeypatch.setattr(
        domain_health_registry,
        "_checks",
        {
            "analytics": lambda: True,
            "automation": lambda: False,
        },
    )
    try:
        response = client.get("/health/domains")
    finally:
        monkeypatch.setattr(domain_health_registry, "_checks", original)

    assert response.status_code == 207
    body = response.json()
    assert body["domains"]["analytics"]["healthy"] is True
    assert body["domains"]["automation"]["healthy"] is False
