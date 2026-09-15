import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_tenant
from app.database import get_db
from app.exceptions import ResourceNotFoundError
from app.models.db import Plan, Subscription
from app.models.schemas import (
    PlanResponse,
    SubscribeRequest,
    SubscribeResponse,
    TenantSubscriptionResponse,
)
from app.services import billing_service

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plans", response_model=list[PlanResponse])
def list_plans(tenant_id: UUID = Depends(require_tenant), db: Session = Depends(get_db)):
    """Tenant-facing plan list - GET /admin/plans exists too, but that's
    behind admin HTTP Basic. A tenant needs to see what's available to
    subscribe to; this is the same Plan rows, just reachable with a
    tenant credential instead of an operator one."""
    return list(db.scalars(select(Plan).order_by(Plan.price)).all())


@router.get("/subscription", response_model=TenantSubscriptionResponse | None)
def get_my_subscription(tenant_id: UUID = Depends(require_tenant), db: Session = Depends(get_db)):
    """The calling tenant's own subscription, or null if they have none
    yet - the admin equivalent (GET /admin/subscriptions?tenant_id=) can
    see every tenant's; this can only ever see the caller's own, scoped
    by require_tenant the same way every other tenant-facing route is."""
    return db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))


@router.post("/subscribe", response_model=SubscribeResponse)
def subscribe(
    payload: SubscribeRequest,
    tenant_id: UUID = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    try:
        subscription, checkout_url = billing_service.create_subscription(
            db, tenant_id, payload.plan_id
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return SubscribeResponse(
        subscription_id=subscription.id,
        status=subscription.status,
        checkout_url=checkout_url,
    )


@router.post("/webhook", status_code=200)
async def webhook(request: Request, db: Session = Depends(get_db)):
    """Called directly by Razorpay, not a tenant - authenticated by
    signature, not X-API-Key. Verifies against the *raw* request body:
    re-serializing parsed JSON before hashing can change whitespace/key
    order and break the signature check, so the body is read once, as
    bytes, before any parsing."""
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not billing_service.verify_webhook_signature(raw_body, signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")

    payload = json.loads(raw_body)
    billing_service.handle_webhook_event(db, payload["event"], payload)
    return {"status": "ok"}
