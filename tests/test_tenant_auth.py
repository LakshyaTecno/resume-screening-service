"""Self-service tenant auth: register/login with a password, Google
sign-up, and the resulting JWT working wherever an API key would on the
existing /api/v1/* routes - see app/auth.py's require_tenant, which
accepts either."""

from app.config import get_settings
from app.models.db import Tenant
from app.services import tenant_registration_service


def _configure_jwt(monkeypatch, secret: str = "test-jwt-secret-at-least-32-bytes-long"):
    monkeypatch.setattr(get_settings(), "jwt_secret", secret)


def test_register_creates_tenant_and_returns_a_working_token(
    authenticated_client, db_session, monkeypatch
):
    _configure_jwt(monkeypatch)

    response = authenticated_client.post(
        "/api/v1/auth/register",
        json={"email": "recruiter@acme.example", "password": "correct-horse-battery"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    token = body["access_token"]

    tenant = db_session.query(Tenant).filter(Tenant.email == "recruiter@acme.example").first()
    assert tenant is not None
    assert tenant.hashed_password is not None
    assert tenant.hashed_password != "correct-horse-battery"  # actually hashed, not stored raw

    # The token this registration returned works on an existing route,
    # exactly like an API key would - this is the point of require_tenant.
    jobs_response = authenticated_client.get(
        "/api/v1/jobs/", headers={"Authorization": f"Bearer {token}"}
    )
    assert jobs_response.status_code == 200


def test_register_duplicate_email_returns_409(authenticated_client, monkeypatch):
    _configure_jwt(monkeypatch)
    authenticated_client.post(
        "/api/v1/auth/register",
        json={"email": "dup@acme.example", "password": "correct-horse-battery"},
    )

    response = authenticated_client.post(
        "/api/v1/auth/register",
        json={"email": "dup@acme.example", "password": "a-different-password"},
    )

    assert response.status_code == 409


def test_login_with_correct_password_returns_a_token(authenticated_client, monkeypatch):
    _configure_jwt(monkeypatch)
    authenticated_client.post(
        "/api/v1/auth/register",
        json={"email": "login-test@acme.example", "password": "correct-horse-battery"},
    )

    response = authenticated_client.post(
        "/api/v1/auth/login",
        json={"email": "login-test@acme.example", "password": "correct-horse-battery"},
    )

    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_with_wrong_password_returns_401(authenticated_client):
    authenticated_client.post(
        "/api/v1/auth/register",
        json={"email": "wrong-pw@acme.example", "password": "correct-horse-battery"},
    )

    response = authenticated_client.post(
        "/api/v1/auth/login",
        json={"email": "wrong-pw@acme.example", "password": "not-the-right-password"},
    )

    assert response.status_code == 401


def test_login_with_unknown_email_returns_401(authenticated_client):
    response = authenticated_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@acme.example", "password": "whatever"},
    )

    assert response.status_code == 401


def test_google_sign_up_creates_tenant_and_returns_a_working_token(
    authenticated_client, db_session, monkeypatch
):
    _configure_jwt(monkeypatch)
    monkeypatch.setattr(get_settings(), "google_oauth_client_id", "test-client-id")
    monkeypatch.setattr(
        tenant_registration_service.google_id_token,
        "verify_oauth2_token",
        lambda token, request, client_id: {"sub": "google-sub-123", "email": "g@acme.example"},
    )

    response = authenticated_client.post(
        "/api/v1/auth/google", json={"id_token": "fake-google-token"}
    )

    assert response.status_code == 200
    tenant = db_session.query(Tenant).filter(Tenant.google_sub == "google-sub-123").first()
    assert tenant is not None
    assert tenant.hashed_password is None  # Google sign-up, no password at all


def test_google_sign_up_is_idempotent_for_the_same_google_account(
    authenticated_client, db_session, monkeypatch
):
    """A second Google sign-in with the same sub logs into the same
    tenant rather than creating a second one - this is what makes it a
    real sign-up-or-login flow, not sign-up-only."""
    _configure_jwt(monkeypatch)
    monkeypatch.setattr(get_settings(), "google_oauth_client_id", "test-client-id")
    monkeypatch.setattr(
        tenant_registration_service.google_id_token,
        "verify_oauth2_token",
        lambda token, request, client_id: {"sub": "google-sub-456", "email": "g2@acme.example"},
    )

    first = authenticated_client.post("/api/v1/auth/google", json={"id_token": "fake-google-token"})
    second = authenticated_client.post(
        "/api/v1/auth/google", json={"id_token": "fake-google-token"}
    )

    assert first.json()["tenant_id"] == second.json()["tenant_id"]
    assert db_session.query(Tenant).filter(Tenant.google_sub == "google-sub-456").count() == 1


def test_google_sign_up_not_configured_returns_503(authenticated_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "google_oauth_client_id", "")

    response = authenticated_client.post("/api/v1/auth/google", json={"id_token": "anything"})

    assert response.status_code == 503


def test_an_existing_admin_issued_api_key_still_works_unchanged(authenticated_client, db_session):
    """require_tenant's whole point is additive: an API key that worked
    before this change works identically after it."""
    from app.auth import _hash_key
    from app.models.db import ApiKey

    tenant = Tenant(name="Admin-Provisioned Tenant")
    db_session.add(tenant)
    db_session.flush()
    db_session.add(
        ApiKey(tenant_id=tenant.id, hashed_key=_hash_key("still-works-key"), key_prefix="still-wo")
    )
    db_session.commit()

    response = authenticated_client.get("/api/v1/jobs/", headers={"X-API-Key": "still-works-key"})

    assert response.status_code == 200


def test_malformed_authorization_header_returns_401(authenticated_client):
    response = authenticated_client.get(
        "/api/v1/jobs/", headers={"Authorization": "not-a-bearer-token"}
    )

    assert response.status_code == 401


def test_invalid_bearer_token_returns_401(authenticated_client, monkeypatch):
    # A real secret is configured so this actually exercises "signature
    # doesn't verify", not the separate "JWT_SECRET unset" fail-closed path.
    _configure_jwt(monkeypatch)

    response = authenticated_client.get(
        "/api/v1/jobs/", headers={"Authorization": "Bearer not-a-real-jwt"}
    )

    assert response.status_code == 401


def test_register_fails_closed_when_jwt_secret_is_unset(authenticated_client, monkeypatch):
    """PyJWT itself refuses to sign with an empty key, so an unset
    JWT_SECRET can't even issue a token in the first place - not "issues
    a token that later fails to verify," a stronger fail-closed property
    than that. Explicitly set to "" here rather than assumed - unlike
    every other test in this file, this one's entire point is what
    happens when it's blank, so it shouldn't depend on whatever happens
    to be in the real .env on whoever's machine runs this suite."""
    monkeypatch.setattr(get_settings(), "jwt_secret", "")

    response = authenticated_client.post(
        "/api/v1/auth/register",
        json={"email": "no-secret@acme.example", "password": "correct-horse-battery"},
    )

    assert response.status_code == 503
