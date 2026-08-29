import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import get_settings

settings = get_settings()

security = HTTPBasic()


def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    """HTTP Basic auth for /api/v1/admin/*, checked against a single
    operator credential - not tenant API keys, since admins operate across
    every tenant. secrets.compare_digest avoids a timing side-channel on
    both fields; a plain `==` would leak how many leading characters
    matched via response time.

    Fails closed the same way require_api_key does: checked explicitly,
    not just via compare_digest - a caller can send an empty username/
    password over Basic auth, and compare_digest("", "") is True, so an
    unconfigured ADMIN_USERNAME/ADMIN_PASSWORD would otherwise accept an
    empty-credential request instead of rejecting everything.
    """
    if not settings.admin_username or not settings.admin_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_USERNAME/ADMIN_PASSWORD are not configured on the server.",
        )

    valid_username = secrets.compare_digest(credentials.username, settings.admin_username)
    valid_password = secrets.compare_digest(credentials.password, settings.admin_password)
    if not (valid_username and valid_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials.",
            headers={"WWW-Authenticate": "Basic"},
        )
