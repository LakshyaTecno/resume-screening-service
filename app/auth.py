from fastapi import Header, HTTPException, status

from app.config import get_settings

settings = get_settings()


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Router-level dependency enforcing a shared API key on `/api/v1/*`.

    Fails closed: an unset API_KEY rejects every request with 503 rather
    than silently accepting all of them - a misconfigured deploy should be
    obviously broken, not quietly open.
    """
    if not settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API_KEY is not configured on the server.",
        )
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key. Send it as the X-API-Key header.",
        )
