"""JWT session tokens for self-registered tenants - a second auth mode
alongside app/auth.py's require_api_key, not a replacement for it. An
admin-created tenant has no password and never gets a JWT; it keeps
using its API key exactly as before. A self-registered tenant gets a
JWT at register/login/google time (see app/routers/auth.py) and can use
it wherever an API key would otherwise be accepted (see
require_tenant in app/auth.py).
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt

from app.config import get_settings

settings = get_settings()

_ALGORITHM = "HS256"


def create_access_token(tenant_id: UUID) -> str:
    """Raises RuntimeError if JWT_SECRET is unset - PyJWT itself refuses
    to sign with an empty key, so this would fail regardless, but an
    explicit check here gives app/routers/auth.py a clear exception to
    catch and turn into a 503, instead of a bare PyJWT InvalidKeyError
    leaking out as an unhandled 500."""
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not configured on the server.")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(tenant_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expiry_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> UUID | None:
    """Returns None on any invalid/expired/malformed token, or if
    JWT_SECRET isn't configured - fails closed the same way an unset
    ADMIN_USERNAME/ADMIN_PASSWORD does, rather than trusting a token
    signed with an empty/predictable key."""
    if not settings.jwt_secret:
        return None
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
        return UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None
