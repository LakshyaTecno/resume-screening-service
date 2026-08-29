import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin_auth import require_admin
from app.auth import _hash_key
from app.database import get_db
from app.models.db import ApiKey, Plan, Subscription, Tenant
from app.models.schemas import (
    AdminSubscriptionResponse,
    ApiKeyCreateResponse,
    ApiKeyResponse,
    PlanCreate,
    PlanResponse,
    TenantCreate,
    TenantResponse,
    TenantUsageResponse,
)
from app.services.billing_service import count_candidates_this_period, current_period_start

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/tenants", response_model=list[TenantResponse])
def list_tenants(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    statement = select(Tenant).order_by(Tenant.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(statement).all())


@router.post("/tenants", response_model=TenantResponse, status_code=201)
def create_tenant(payload: TenantCreate, db: Session = Depends(get_db)):
    tenant = Tenant(name=payload.name)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
def get_tenant(tenant_id: UUID, db: Session = Depends(get_db)):
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.get("/tenants/{tenant_id}/api-keys", response_model=list[ApiKeyResponse])
def list_api_keys(tenant_id: UUID, db: Session = Depends(get_db)):
    statement = (
        select(ApiKey).where(ApiKey.tenant_id == tenant_id).order_by(ApiKey.created_at.desc())
    )
    return list(db.scalars(statement).all())


@router.post("/tenants/{tenant_id}/api-keys", response_model=ApiKeyCreateResponse, status_code=201)
def create_api_key(tenant_id: UUID, db: Session = Depends(get_db)):
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    raw_key = secrets.token_urlsafe(32)
    api_key = ApiKey(tenant_id=tenant_id, hashed_key=_hash_key(raw_key), key_prefix=raw_key[:8])
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    return ApiKeyCreateResponse(
        id=api_key.id,
        tenant_id=api_key.tenant_id,
        key_prefix=api_key.key_prefix,
        created_at=api_key.created_at,
        revoked_at=api_key.revoked_at,
        last_used_at=api_key.last_used_at,
        raw_key=raw_key,
    )


@router.post("/api-keys/{key_id}/revoke", response_model=ApiKeyResponse)
def revoke_api_key(key_id: UUID, db: Session = Depends(get_db)):
    api_key = db.get(ApiKey, key_id)
    if api_key is None:
        raise HTTPException(status_code=404, detail="API key not found")

    api_key.revoked_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(api_key)
    return api_key


@router.get("/plans", response_model=list[PlanResponse])
def list_plans(db: Session = Depends(get_db)):
    return list(db.scalars(select(Plan).order_by(Plan.created_at.desc())).all())


@router.post("/plans", response_model=PlanResponse, status_code=201)
def create_plan(payload: PlanCreate, db: Session = Depends(get_db)):
    plan = Plan(
        name=payload.name,
        price=payload.price,
        currency=payload.currency,
        monthly_resume_quota=payload.monthly_resume_quota,
        razorpay_plan_id=payload.razorpay_plan_id,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/subscriptions", response_model=list[AdminSubscriptionResponse])
def list_subscriptions(tenant_id: UUID | None = None, db: Session = Depends(get_db)):
    statement = select(Subscription)
    if tenant_id is not None:
        statement = statement.where(Subscription.tenant_id == tenant_id)
    return list(db.scalars(statement.order_by(Subscription.created_at.desc())).all())


@router.get("/tenants/{tenant_id}/usage", response_model=TenantUsageResponse)
def get_tenant_usage(tenant_id: UUID, db: Session = Depends(get_db)):
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    subscription = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
    plan = db.get(Plan, subscription.plan_id) if subscription else None

    # Shares billing_guard.enforce_quota's exact period-start logic so this
    # view can never disagree with what actually gates uploads.
    period_start = (
        current_period_start(subscription)
        if subscription
        else datetime.now(timezone.utc) - timedelta(days=30)
    )

    return TenantUsageResponse(
        tenant_id=tenant_id,
        candidates_this_period=count_candidates_this_period(db, tenant_id, period_start),
        monthly_resume_quota=plan.monthly_resume_quota if plan else None,
    )
