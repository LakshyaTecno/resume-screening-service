import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import require_tenant
from app.database import get_db
from app.exceptions import ResourceNotFoundError
from app.models.schemas import SubscribeRequest, SubscribeResponse
from app.services import billing_service

router = APIRouter(prefix="/billing", tags=["billing"])


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
