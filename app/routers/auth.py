from fastapi import APIRouter, Depends, HTTPException
from google.auth.exceptions import GoogleAuthError
from sqlalchemy.orm import Session

from app import jwt_auth
from app.database import get_db
from app.exceptions import InvalidCredentialsError, ResourceConflictError, ResourceNotFoundError
from app.models.schemas import (
    GoogleAuthRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services import tenant_registration_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(tenant_id) -> TokenResponse:
    try:
        token = jwt_auth.create_access_token(tenant_id)
    except RuntimeError as exc:
        # JWT_SECRET unset - a server misconfiguration, not a client
        # error, so 503 rather than letting this leak out as a 500.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return TokenResponse(access_token=token, tenant_id=tenant_id)


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    try:
        tenant = tenant_registration_service.register_with_password(
            db, payload.email, payload.password
        )
    except ResourceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _token_response(tenant.id)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    try:
        tenant = tenant_registration_service.authenticate_with_password(
            db, payload.email, payload.password
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return _token_response(tenant.id)


@router.post("/google", response_model=TokenResponse)
def google_auth(payload: GoogleAuthRequest, db: Session = Depends(get_db)):
    try:
        tenant = tenant_registration_service.register_or_login_with_google(db, payload.id_token)
    except ResourceNotFoundError as exc:
        # Not-configured case (no GOOGLE_OAUTH_CLIENT_ID) - a server
        # misconfiguration, not a client error.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (GoogleAuthError, ValueError) as exc:
        # verify_oauth2_token raises on a forged/expired/wrong-audience
        # token - that's an authentication failure, not a 500.
        raise HTTPException(status_code=401, detail="Invalid Google ID token.") from exc
    return _token_response(tenant.id)
