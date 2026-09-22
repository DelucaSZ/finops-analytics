from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.core.security import authenticate_admin, create_access_token
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    if not authenticate_admin(payload.email, payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    return TokenResponse(
        access_token=create_access_token(payload.email),
        expires_in_minutes=settings.access_token_minutes,
    )
