"""Authentication endpoints — login, me, change password/username."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.models import AdminUser

router = APIRouter(prefix="/auth", tags=["Auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    result = await db.execute(select(AdminUser).where(AdminUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


def require_role(*roles: str):
    """Dependency factory — raises 403 if user role not in allowed roles."""
    async def checker(user: AdminUser = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user
    return checker


@router.post("/login")
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Authenticate with username + password. Returns JWT tokens."""
    result = await db.execute(
        select(AdminUser).where(AdminUser.username == form.username)
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()

    return {
        "access_token": create_access_token(str(user.id)),
        "refresh_token": create_refresh_token(str(user.id)),
        "token_type": "bearer",
        "must_change_password": user.must_change_password,
        "role": user.role,
    }


@router.get("/me")
async def get_me(user: AdminUser = Depends(get_current_user)):
    """Return current authenticated user info."""
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "created_at": user.created_at.isoformat(),
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


@router.post("/change-credentials")
async def change_credentials(
    payload: dict,
    user: AdminUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change username and/or password. Required on first login.

    Body: { "new_username": str, "new_password": str, "current_password": str }
    """
    current_password = payload.get("current_password", "")
    new_username = payload.get("new_username")
    new_password = payload.get("new_password")

    if not verify_password(current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

    if not new_username and not new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide new_username or new_password")

    if new_username:
        if len(new_username) < 3:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username must be at least 3 characters")
        existing = await db.execute(select(AdminUser).where(AdminUser.username == new_username))
        if existing.scalar_one_or_none() and new_username != user.username:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")
        user.username = new_username

    if new_password:
        if len(new_password) < 8:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 8 characters")
        user.hashed_password = hash_password(new_password)

    user.must_change_password = False
    await db.flush()

    return {"status": "ok", "username": user.username}
