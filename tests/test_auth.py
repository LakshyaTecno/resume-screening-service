from app.config import get_settings


def test_unconfigured_api_key_rejects_everything(authenticated_client, monkeypatch):
    """Fail closed: a deploy that forgot to set API_KEY should be obviously
    broken (503), not silently open to every request."""
    monkeypatch.setattr(get_settings(), "api_key", "")

    response = authenticated_client.get("/api/v1/jobs/")

    assert response.status_code == 503


def test_missing_header_returns_401(authenticated_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "api_key", "test-secret")

    response = authenticated_client.get("/api/v1/jobs/")

    assert response.status_code == 401


def test_wrong_key_returns_401(authenticated_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "api_key", "test-secret")

    response = authenticated_client.get("/api/v1/jobs/", headers={"X-API-Key": "wrong-key"})

    assert response.status_code == 401


def test_correct_key_is_accepted(authenticated_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "api_key", "test-secret")

    response = authenticated_client.get("/api/v1/jobs/", headers={"X-API-Key": "test-secret"})

    assert response.status_code == 200


def test_health_check_does_not_require_a_key(authenticated_client, monkeypatch):
    """/health has no auth dependency - Docker's healthcheck calls it with
    no headers at all (see docker-compose.yml), so it must stay open."""
    monkeypatch.setattr(get_settings(), "api_key", "test-secret")

    response = authenticated_client.get("/health")

    assert response.status_code == 200
