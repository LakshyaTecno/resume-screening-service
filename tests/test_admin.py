from app.config import get_settings


def _configure_admin(monkeypatch, username="admin", password="admin-secret"):
    monkeypatch.setattr(get_settings(), "admin_username", username)
    monkeypatch.setattr(get_settings(), "admin_password", password)


def test_unconfigured_admin_credentials_returns_503(authenticated_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_username", "")
    monkeypatch.setattr(get_settings(), "admin_password", "")

    response = authenticated_client.get("/api/v1/admin/tenants", auth=("anything", "anything"))

    assert response.status_code == 503


def test_missing_credentials_returns_401(authenticated_client, monkeypatch):
    _configure_admin(monkeypatch)

    response = authenticated_client.get("/api/v1/admin/tenants")

    assert response.status_code == 401


def test_wrong_credentials_returns_401(authenticated_client, monkeypatch):
    _configure_admin(monkeypatch)

    response = authenticated_client.get("/api/v1/admin/tenants", auth=("admin", "wrong-password"))

    assert response.status_code == 401


def test_create_and_list_tenants(authenticated_client, monkeypatch):
    _configure_admin(monkeypatch)
    auth = ("admin", "admin-secret")

    create_response = authenticated_client.post(
        "/api/v1/admin/tenants", auth=auth, json={"name": "Acme Recruiting"}
    )
    assert create_response.status_code == 201
    tenant_id = create_response.json()["id"]

    list_response = authenticated_client.get("/api/v1/admin/tenants", auth=auth)
    assert list_response.status_code == 200
    assert tenant_id in [t["id"] for t in list_response.json()]

    get_response = authenticated_client.get(f"/api/v1/admin/tenants/{tenant_id}", auth=auth)
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Acme Recruiting"


def test_create_api_key_returns_raw_key_once(authenticated_client, monkeypatch, mock_vector_store):
    _configure_admin(monkeypatch)
    auth = ("admin", "admin-secret")

    tenant_id = authenticated_client.post(
        "/api/v1/admin/tenants", auth=auth, json={"name": "Acme Recruiting"}
    ).json()["id"]

    create_key_response = authenticated_client.post(
        f"/api/v1/admin/tenants/{tenant_id}/api-keys", auth=auth
    )
    assert create_key_response.status_code == 201
    body = create_key_response.json()
    assert "raw_key" in body
    assert body["key_prefix"] == body["raw_key"][:8]

    # The new key actually works against the real tenant-auth dependency.
    tenant_response = authenticated_client.post(
        "/api/v1/jobs/",
        headers={"X-API-Key": body["raw_key"]},
        json={"title": "Backend Engineer", "description": "Build APIs."},
    )
    assert tenant_response.status_code == 201


def test_revoke_api_key(authenticated_client, monkeypatch, mock_vector_store):
    _configure_admin(monkeypatch)
    auth = ("admin", "admin-secret")

    tenant_id = authenticated_client.post(
        "/api/v1/admin/tenants", auth=auth, json={"name": "Acme Recruiting"}
    ).json()["id"]
    key_body = authenticated_client.post(
        f"/api/v1/admin/tenants/{tenant_id}/api-keys", auth=auth
    ).json()

    revoke_response = authenticated_client.post(
        f"/api/v1/admin/api-keys/{key_body['id']}/revoke", auth=auth
    )
    assert revoke_response.status_code == 200
    assert revoke_response.json()["revoked_at"] is not None

    blocked_response = authenticated_client.get(
        "/api/v1/jobs/", headers={"X-API-Key": key_body["raw_key"]}
    )
    assert blocked_response.status_code == 401


def test_create_and_list_plans(authenticated_client, monkeypatch):
    _configure_admin(monkeypatch)
    auth = ("admin", "admin-secret")

    create_response = authenticated_client.post(
        "/api/v1/admin/plans",
        auth=auth,
        json={
            "name": "Starter",
            "price": 99900,
            "currency": "INR",
            "monthly_resume_quota": 100,
            "razorpay_plan_id": "plan_test123",
        },
    )
    assert create_response.status_code == 201

    list_response = authenticated_client.get("/api/v1/admin/plans", auth=auth)
    assert list_response.status_code == 200
    assert any(p["name"] == "Starter" for p in list_response.json())


def test_tenant_usage_with_no_subscription(authenticated_client, monkeypatch):
    _configure_admin(monkeypatch)
    auth = ("admin", "admin-secret")

    tenant_id = authenticated_client.post(
        "/api/v1/admin/tenants", auth=auth, json={"name": "Acme Recruiting"}
    ).json()["id"]

    usage_response = authenticated_client.get(f"/api/v1/admin/tenants/{tenant_id}/usage", auth=auth)

    assert usage_response.status_code == 200
    body = usage_response.json()
    assert body["candidates_this_period"] == 0
    assert body["monthly_resume_quota"] is None
