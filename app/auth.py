import hashlib
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app import jwt_auth
from app.database import get_db
from app.models.db import ApiKey


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


async def require_api_key(
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> UUID:
    """Resolves X-API-Key to the tenant it belongs to.

    Route handlers receive the tenant_id via Depends(require_api_key) and
    must scope every query with it - this dependency only proves *who* is
    calling, not that any particular resource belongs to them.

    Fails closed by construction: an empty api_keys table (or an
    unrecognized/revoked key) rejects with 401 the same as any other
    invalid key - there's no separate "unconfigured" state to fall open on.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header.",
        )

    api_key = (
        db.query(ApiKey)
        .filter(ApiKey.hashed_key == _hash_key(x_api_key), ApiKey.revoked_at.is_(None))
        .first()
    )
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key.",
        )

    api_key.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return api_key.tenant_id


async def require_tenant(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> UUID:
    """Resolves either a JWT session token (self-registered tenants, see
    app/jwt_auth.py and app/routers/auth.py) or an X-API-Key
    (admin-issued or self-service-issued, see require_api_key above) to
    the same tenant_id - the two auth modes are equally valid on every
    route that used to only accept require_api_key.

    If an Authorization header is present at all, it's treated as
    authoritative and must be a valid 'Bearer <token>' - it does not
    silently fall back to X-API-Key on failure, since that could mask a
    real bug (an expired session token) as a confusing, unrelated
    "missing API key" error instead. X-API-Key is only consulted when no
    Authorization header was sent."""
    if authorization is not None:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Malformed Authorization header - expected 'Bearer <token>'.",
            )
        tenant_id = jwt_auth.decode_access_token(token)
        if tenant_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session token.",
            )
        return tenant_id

    return await require_api_key(x_api_key=x_api_key, db=db)
