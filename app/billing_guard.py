from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_tenant
from app.config import get_settings
from app.database import get_db
from app.models.db import Plan, Subscription
from app.services.billing_service import (
    count_all_time_candidates,
    count_candidates_this_period,
    current_period_start,
)

settings = get_settings()


async def enforce_quota(
    tenant_id: UUID = Depends(require_tenant),
    db: Session = Depends(get_db),
) -> UUID:
    """Gate for resume-consuming endpoints. No active subscription doesn't
    mean an immediate 402 anymore - a tenant gets a free-tier lifetime
    allowance (settings.free_tier_resume_limit) before needing to
    subscribe. With an active subscription, the existing monthly-quota
    check applies unchanged.

    Both branches count live Candidate rows rather than a separate
    running counter - always correct by construction, no drift risk if a
    webhook is ever missed. Revisit only if resume volume ever makes that
    COUNT itself the bottleneck."""
    subscription = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))

    if subscription is None or subscription.status != "active":
        used = count_all_time_candidates(db, tenant_id)
        if used >= settings.free_tier_resume_limit:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=(
                    f"Free tier limit ({settings.free_tier_resume_limit} resumes) reached. "
                    "Subscribe to a plan to continue."
                ),
            )
        return tenant_id

    plan = db.get(Plan, subscription.plan_id)
    if plan.monthly_resume_quota is not None:
        period_start = current_period_start(subscription, plan)
        used = count_candidates_this_period(db, tenant_id, period_start)
        if used >= plan.monthly_resume_quota:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Monthly resume quota exceeded.",
            )

    return tenant_id
