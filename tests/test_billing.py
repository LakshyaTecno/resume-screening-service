import hashlib
import hmac
import json

from app.auth import _hash_key
from app.config import get_settings
from app.models.db import ApiKey, Candidate, Plan, Subscription, Tenant
from app.services import billing_service, candidate_service
from tests.factories import make_razorpay_webhook_payload


def _seed_tenant_with_key(db_session, raw_key: str = "billing-test-key") -> Tenant:
    tenant = Tenant(name="Billing Test Tenant")
    db_session.add(tenant)
    db_session.flush()
    db_session.add(
        ApiKey(tenant_id=tenant.id, hashed_key=_hash_key(raw_key), key_prefix=raw_key[:8])
    )
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


def _seed_plan(db_session, monthly_resume_quota: int | None = None) -> Plan:
    plan = Plan(
        name="Starter",
        price=99900,
        currency="INR",
        monthly_resume_quota=monthly_resume_quota,
        razorpay_plan_id="plan_test123",
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    return plan


def _seed_subscription(
    db_session, tenant: Tenant, plan: Plan, status: str = "active"
) -> Subscription:
    subscription = Subscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        status=status,
        razorpay_subscription_id="sub_test123",
    )
    db_session.add(subscription)
    db_session.commit()
    db_session.refresh(subscription)
    return subscription


class _FakeSubscriptionAPI:
    def __init__(self, response: dict):
        self._response = response

    def create(self, data):
        return self._response


class _FakeRazorpayClient:
    def __init__(self, response: dict):
        self.subscription = _FakeSubscriptionAPI(response)


def test_subscribe_happy_path(authenticated_client, db_session, monkeypatch):
    tenant = _seed_tenant_with_key(db_session)
    plan = _seed_plan(db_session)

    monkeypatch.setattr(
        billing_service,
        "_client",
        lambda: _FakeRazorpayClient(
            {"id": "sub_new123", "status": "created", "short_url": "https://rzp.io/i/abc123"}
        ),
    )

    response = authenticated_client.post(
        "/api/v1/billing/subscribe",
        headers={"X-API-Key": "billing-test-key"},
        json={"plan_id": str(plan.id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "created"
    assert body["checkout_url"] == "https://rzp.io/i/abc123"

    subscription = (
        db_session.query(Subscription).filter(Subscription.tenant_id == tenant.id).first()
    )
    assert subscription.razorpay_subscription_id == "sub_new123"


def test_list_plans_is_reachable_with_a_tenant_key(authenticated_client, db_session):
    """Unlike GET /admin/plans (HTTP Basic, operator-only), a tenant needs
    to see what's available to subscribe to with their own credential."""
    _seed_tenant_with_key(db_session)
    _seed_plan(db_session)

    response = authenticated_client.get(
        "/api/v1/billing/plans", headers={"X-API-Key": "billing-test-key"}
    )

    assert response.status_code == 200
    assert any(p["name"] == "Starter" for p in response.json())


def test_get_my_subscription_returns_null_with_no_subscription(authenticated_client, db_session):
    _seed_tenant_with_key(db_session)

    response = authenticated_client.get(
        "/api/v1/billing/subscription", headers={"X-API-Key": "billing-test-key"}
    )

    assert response.status_code == 200
    assert response.json() is None


def test_get_my_subscription_returns_only_the_callers_own(authenticated_client, db_session):
    tenant = _seed_tenant_with_key(db_session, raw_key="mine-key")
    _seed_tenant_with_key(db_session, raw_key="someone-elses-key")
    plan = _seed_plan(db_session)
    _seed_subscription(db_session, tenant, plan)

    response = authenticated_client.get(
        "/api/v1/billing/subscription", headers={"X-API-Key": "mine-key"}
    )

    assert response.status_code == 200
    assert response.json()["plan_id"] == str(plan.id)


def test_subscribe_unknown_plan_returns_404(authenticated_client, db_session):
    _seed_tenant_with_key(db_session)

    response = authenticated_client.post(
        "/api/v1/billing/subscribe",
        headers={"X-API-Key": "billing-test-key"},
        json={"plan_id": "00000000-0000-0000-0000-000000000000"},
    )

    assert response.status_code == 404


def test_webhook_valid_signature_updates_subscription(
    authenticated_client, db_session, monkeypatch
):
    tenant = _seed_tenant_with_key(db_session)
    plan = _seed_plan(db_session)
    _seed_subscription(db_session, tenant, plan, status="created")

    monkeypatch.setattr(get_settings(), "razorpay_webhook_secret", "whsec_test")

    payload = make_razorpay_webhook_payload(
        event="subscription.charged",
        razorpay_subscription_id="sub_test123",
        current_end=1893456000,
    )
    raw_body = json.dumps(payload).encode("utf-8")
    signature = hmac.new(b"whsec_test", raw_body, hashlib.sha256).hexdigest()

    response = authenticated_client.post(
        "/api/v1/billing/webhook",
        headers={"X-Razorpay-Signature": signature, "Content-Type": "application/json"},
        content=raw_body,
    )

    assert response.status_code == 200
    subscription = (
        db_session.query(Subscription).filter(Subscription.tenant_id == tenant.id).first()
    )
    assert subscription.status == "active"
    assert subscription.current_period_end is not None


def test_webhook_invalid_signature_returns_400(authenticated_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "razorpay_webhook_secret", "whsec_test")

    payload = make_razorpay_webhook_payload()
    raw_body = json.dumps(payload).encode("utf-8")

    response = authenticated_client.post(
        "/api/v1/billing/webhook",
        headers={"X-Razorpay-Signature": "not-the-right-signature"},
        content=raw_body,
    )

    assert response.status_code == 400


def test_upload_without_subscription_succeeds_under_free_tier(
    authenticated_client, db_session, mock_vector_store, monkeypatch
):
    """No subscription no longer means an immediate 402 - a tenant gets a
    free-tier lifetime allowance (settings.free_tier_resume_limit) first.
    See test_upload_without_subscription_over_free_tier_returns_402 for
    what happens once that's used up."""
    _seed_tenant_with_key(db_session)
    monkeypatch.setattr(
        candidate_service.ingestion,
        "upload_resume_and_enqueue",
        lambda candidate_id, tenant_id, file_bytes: None,
    )

    response = authenticated_client.post(
        "/api/v1/candidates/upload",
        headers={"X-API-Key": "billing-test-key"},
        files={"file": ("resume.pdf", b"%PDF-1.4 fake bytes", "application/pdf")},
    )

    assert response.status_code == 202


def test_upload_without_subscription_over_free_tier_returns_402(
    authenticated_client, db_session, mock_vector_store, monkeypatch
):
    tenant = _seed_tenant_with_key(db_session)
    limit = get_settings().free_tier_resume_limit
    for _ in range(limit):
        db_session.add(Candidate(tenant_id=tenant.id, status="processed"))
    db_session.commit()

    response = authenticated_client.post(
        "/api/v1/candidates/upload",
        headers={"X-API-Key": "billing-test-key"},
        files={"file": ("resume.pdf", b"%PDF-1.4 fake bytes", "application/pdf")},
    )

    assert response.status_code == 402
    assert "Free tier" in response.json()["detail"]


def test_upload_under_quota_succeeds(
    authenticated_client, db_session, mock_vector_store, monkeypatch
):
    tenant = _seed_tenant_with_key(db_session)
    plan = _seed_plan(db_session, monthly_resume_quota=5)
    _seed_subscription(db_session, tenant, plan)

    monkeypatch.setattr(
        candidate_service.ingestion,
        "upload_resume_and_enqueue",
        lambda candidate_id, tenant_id, file_bytes: None,
    )

    response = authenticated_client.post(
        "/api/v1/candidates/upload",
        headers={"X-API-Key": "billing-test-key"},
        files={"file": ("resume.pdf", b"%PDF-1.4 fake bytes", "application/pdf")},
    )

    assert response.status_code == 202


def test_upload_over_quota_returns_402(authenticated_client, db_session, mock_vector_store):
    tenant = _seed_tenant_with_key(db_session)
    plan = _seed_plan(db_session, monthly_resume_quota=1)
    _seed_subscription(db_session, tenant, plan)

    db_session.add(Candidate(tenant_id=tenant.id, status="processed"))
    db_session.commit()

    response = authenticated_client.post(
        "/api/v1/candidates/upload",
        headers={"X-API-Key": "billing-test-key"},
        files={"file": ("resume.pdf", b"%PDF-1.4 fake bytes", "application/pdf")},
    )

    assert response.status_code == 402
