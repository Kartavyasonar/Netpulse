from fastapi import APIRouter, HTTPException, status
from app.schemas.schemas import LoginRequest, TokenResponse
from app.core.security import create_access_token, verify_password, hash_password
from app.core.config import settings

router = APIRouter()

# Simple single-admin auth (extend to DB users for multi-user)
ADMIN_HASH = hash_password(settings.ADMIN_PASSWORD)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    if body.username != settings.ADMIN_USERNAME or not verify_password(body.password, ADMIN_HASH):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token({"sub": body.username, "role": "admin"})
    return TokenResponse(access_token=token)
