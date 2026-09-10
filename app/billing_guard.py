from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.database import get_db
from app.models.db import Plan, Subscription
from app.services.billing_service import count_candidates_this_period, current_period_start


async def enforce_quota(
    tenant_id: UUID = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> UUID:
    """Gate for resume-consuming endpoints: 402s with no active
    subscription, or once the plan's monthly quota is used up. Counts live
    Candidate rows for the current period rather than a separate running
    counter - always correct by construction, no drift risk if a webhook
    is ever missed. Revisit only if resume volume ever makes that COUNT
    itself the bottleneck."""
    subscription = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
    if subscription is None or subscription.status != "active":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="No active subscription.",
        )

    plan = db.get(Plan, subscription.plan_id)
    if plan.monthly_resume_quota is not None:
        period_start = current_period_start(subscription)
        used = count_candidates_this_period(db, tenant_id, period_start)
        if used >= plan.monthly_resume_quota:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Monthly resume quota exceeded.",
            )

    return tenant_id
