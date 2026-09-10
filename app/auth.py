import hashlib
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

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
