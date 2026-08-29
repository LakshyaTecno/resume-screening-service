from datetime import datetime, timezone

from app.auth import _hash_key
from app.models.db import ApiKey, Tenant


def _seed_api_key(db_session, tenant: Tenant, raw_key: str, revoked: bool = False):
    key = ApiKey(
        tenant_id=tenant.id,
        hashed_key=_hash_key(raw_key),
        key_prefix=raw_key[:8],
        revoked_at=datetime.now(timezone.utc) if revoked else None,
    )
    db_session.add(key)
    db_session.commit()
    return key


def test_missing_header_returns_401(authenticated_client):
    response = authenticated_client.get("/api/v1/jobs/")

    assert response.status_code == 401


def test_unknown_key_returns_401(authenticated_client):
    response = authenticated_client.get("/api/v1/jobs/", headers={"X-API-Key": "not-a-real-key"})

    assert response.status_code == 401


def test_revoked_key_returns_401(authenticated_client, db_session, tenant):
    _seed_api_key(db_session, tenant, "revoked-key-123", revoked=True)

    response = authenticated_client.get("/api/v1/jobs/", headers={"X-API-Key": "revoked-key-123"})

    assert response.status_code == 401


def test_valid_key_resolves_correct_tenant(
    authenticated_client, db_session, tenant, mock_vector_store
):
    _seed_api_key(db_session, tenant, "valid-key-123")

    response = authenticated_client.post(
        "/api/v1/jobs/",
        headers={"X-API-Key": "valid-key-123"},
        json={"title": "Backend Engineer", "description": "Build APIs."},
    )

    assert response.status_code == 201


def test_health_check_does_not_require_a_key(authenticated_client):
    """/health has no auth dependency - Docker's healthcheck calls it with
    no headers at all (see docker-compose.yml), so it must stay open."""
    response = authenticated_client.get("/health")

    assert response.status_code == 200
