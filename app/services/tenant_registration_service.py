"""The three self-service ways a Tenant row gets created or authenticated
without an admin - email/password registration and login, and Google
sign-up. Mirrors how app/services/billing_service.py keeps business logic
out of the router (see app/routers/auth.py for the HTTP glue).
"""

from uuid import UUID

import bcrypt
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.exceptions import InvalidCredentialsError, ResourceConflictError, ResourceNotFoundError
from app.models.db import Tenant

settings = get_settings()


def _hash_password(raw_password: str) -> str:
    # bcrypt, not the SHA-256 used for ApiKey.hashed_key - this is a real
    # user-chosen password (low entropy, reused across sites, guessable),
    # unlike a generated API key, so a slow hash is the whole point here.
    return bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(raw_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(raw_password.encode("utf-8"), hashed_password.encode("utf-8"))


def register_with_password(db: Session, email: str, password: str) -> Tenant:
    existing = db.scalar(select(Tenant).where(Tenant.email == email))
    if existing is not None:
        raise ResourceConflictError("An account with this email already exists.")

    tenant = Tenant(name=email, email=email, hashed_password=_hash_password(password))
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def authenticate_with_password(db: Session, email: str, password: str) -> Tenant:
    tenant = db.scalar(select(Tenant).where(Tenant.email == email))
    if tenant is None or tenant.hashed_password is None:
        raise InvalidCredentialsError("Invalid email or password.")
    if not _verify_password(password, tenant.hashed_password):
        raise InvalidCredentialsError("Invalid email or password.")
    return tenant


def register_or_login_with_google(db: Session, google_id_token_str: str) -> Tenant:
    """Verifies the ID token's signature and audience against Google's
    own public keys - this is what makes it trustworthy, not merely
    decoding it. Finds an existing tenant by google_sub, or creates one -
    this is the "full alternate sign-up" behavior, not sign-in-only."""
    if not settings.google_oauth_client_id:
        raise ResourceNotFoundError("Google sign-in is not configured on this server.")

    claims = google_id_token.verify_oauth2_token(
        google_id_token_str,
        google_requests.Request(),
        settings.google_oauth_client_id,
    )
    google_sub = claims["sub"]
    email = claims.get("email", "")

    tenant = db.scalar(select(Tenant).where(Tenant.google_sub == google_sub))
    if tenant is not None:
        return tenant

    tenant = Tenant(name=email or google_sub, email=email or None, google_sub=google_sub)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def get_tenant(db: Session, tenant_id: UUID) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise ResourceNotFoundError("Tenant not found")
    return tenant
