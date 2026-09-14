"""Razorpay billing: creating subscriptions, verifying and applying
webhook events, and the tenant usage counting shared with app/billing_guard.py's
quota enforcement so the two can't drift apart.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import razorpay
from razorpay.errors import SignatureVerificationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.exceptions import ResourceNotFoundError
from app.models.db import Candidate, Plan, Subscription

settings = get_settings()

# Razorpay requires a finite total_count for a subscription even when the
# intent is "keep renewing until cancelled" - 120 monthly cycles (10 years)
# is the common workaround, not a real limit on how long a tenant can stay
# subscribed.
_SUBSCRIPTION_TOTAL_COUNT = 120


def _client() -> razorpay.Client:
    return razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))


def create_subscription(db: Session, tenant_id: UUID, plan_id: UUID) -> tuple[Subscription, str]:
    """Returns the local Subscription row plus Razorpay's hosted checkout
    URL - the URL itself isn't persisted, it's a one-time link for the
    tenant to complete payment, not a stable field to store and reuse."""
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise ResourceNotFoundError("Plan not found")

    response = _client().subscription.create(
        data={
            "plan_id": plan.razorpay_plan_id,
            "customer_notify": 1,
            "total_count": _SUBSCRIPTION_TOTAL_COUNT,
        }
    )

    subscription = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
    if subscription is None:
        subscription = Subscription(tenant_id=tenant_id)
        db.add(subscription)

    subscription.plan_id = plan.id
    subscription.status = response["status"]
    subscription.razorpay_subscription_id = response["id"]
    db.commit()
    db.refresh(subscription)
    return subscription, response["short_url"]


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    try:
        _client().utility.verify_webhook_signature(
            raw_body.decode("utf-8"), signature, settings.razorpay_webhook_secret
        )
        return True
    except SignatureVerificationError:
        return False


# Razorpay subscription statuses that map onto our own status column
# unchanged - the local field is the source of truth for enforce_quota, so
# only these events (not every event Razorpay can send) update it.
_STATUS_EVENTS = {
    "subscription.activated": "active",
    "subscription.charged": "active",
    "subscription.cancelled": "cancelled",
    "subscription.halted": "cancelled",
}


def handle_webhook_event(db: Session, event_type: str, payload: dict) -> None:
    new_status = _STATUS_EVENTS.get(event_type)
    if new_status is None:
        return  # Not a status-affecting event we track - ignored, not an error.

    razorpay_subscription_id = payload["subscription"]["entity"]["id"]
    subscription = db.scalar(
        select(Subscription).where(
            Subscription.razorpay_subscription_id == razorpay_subscription_id
        )
    )
    if subscription is None:
        return  # Unknown subscription (e.g. a test event) - nothing local to update.

    subscription.status = new_status
    if event_type == "subscription.charged":
        current_end = payload["subscription"]["entity"].get("current_end")
        if current_end is not None:
            subscription.current_period_end = datetime.fromtimestamp(current_end, tz=timezone.utc)
    db.commit()


def count_candidates_this_period(db: Session, tenant_id: UUID, period_start: datetime) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Candidate)
            .where(Candidate.tenant_id == tenant_id, Candidate.created_at >= period_start)
        )
        or 0
    )


def count_all_time_candidates(db: Session, tenant_id: UUID) -> int:
    """Unlike count_candidates_this_period, no period_start filter at
    all - this is the free-tier lifetime cap (billing_guard.enforce_quota
    with no active subscription), which never resets, unlike a paid
    plan's monthly quota."""
    return (
        db.scalar(
            select(func.count()).select_from(Candidate).where(Candidate.tenant_id == tenant_id)
        )
        or 0
    )


def current_period_start(subscription: Subscription, plan: Plan) -> datetime:
    """Best-effort period start when Razorpay hasn't told us current_end
    yet (e.g. before the first charge webhook arrives) - falls back to a
    rolling window sized to the plan's own duration_months rather than
    the subscription's whole lifetime, so quota isn't calculated against
    an unbounded window."""
    window = timedelta(days=30 * plan.duration_months)
    if subscription.current_period_end is not None:
        return subscription.current_period_end - window
    return datetime.now(timezone.utc) - window
