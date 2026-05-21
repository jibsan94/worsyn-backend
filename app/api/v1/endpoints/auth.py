"""Authentication endpoints — login, me, change-credentials, 2FA setup/complete."""
from datetime import datetime, timezone

import redis as redis_lib
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_partial_token,
    create_refresh_token,
    decode_token,
    generate_qr_base64,
    generate_totp_secret,
    get_totp_uri,
    hash_password,
    verify_password,
    verify_totp,
)
from app.db.session import get_db
from app.models.models import AdminUser
from app.services.audit import log_action

settings = get_settings()

router = APIRouter(prefix="/auth", tags=["Auth"])

_COOKIE: dict = dict(httponly=True, samesite="lax", secure=False, path="/")


def _redis() -> redis_lib.Redis:
    return redis_lib.from_url(settings.redis_url, decode_responses=True)


async def get_current_user(
    authorization: str | None = Header(default=None),
    worsyn_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    token: str | None = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    elif worsyn_access:
        token = worsyn_access
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
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


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post("/logout")
async def logout(response: Response):
    """Clear admin session cookies."""
    response.delete_cookie("worsyn_access", path="/")
    response.delete_cookie("worsyn_refresh", path="/")
    return {"ok": True}


@router.post("/login")
async def login(
    response: Response,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Authenticate with username + password.

    If user has 2FA enabled, returns {requires_2fa: true, partial_token} instead of full tokens.
    Client must then call POST /auth/2fa/complete with the TOTP code.
    """
    result = await db.execute(
        select(AdminUser).where(AdminUser.username == form.username)
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    if user.two_factor_enabled and user.two_factor_secret:
        return {
            "requires_2fa": True,
            "partial_token": create_partial_token(str(user.id)),
            "access_token": None,
            "refresh_token": None,
            "token_type": "bearer",
            "must_change_password": user.must_change_password,
            "role": user.role,
        }

    user.last_login_at = datetime.now(timezone.utc)
    await log_action(db, user, "auth.login", "session", resource_name=user.username)
    access = create_access_token(str(user.id))
    refresh = create_refresh_token(str(user.id))
    response.set_cookie("worsyn_access", access, max_age=30 * 60, **_COOKIE)
    response.set_cookie("worsyn_refresh", refresh, max_age=7 * 24 * 60 * 60, **_COOKIE)
    return {
        "requires_2fa": False,
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "must_change_password": user.must_change_password,
        "role": user.role,
    }


@router.post("/2fa/complete")
async def complete_2fa_login(
    payload: dict,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Second step of login when user has 2FA enabled.

    Body: { "partial_token": str, "totp_code": str }
    Returns full JWT tokens on success.
    """
    partial_token = payload.get("partial_token", "")
    totp_code = payload.get("totp_code", "")

    data = decode_token(partial_token)
    if not data.get("sub") or data.get("type") != "2fa_pending":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido o expirado")

    result = await db.execute(select(AdminUser).where(AdminUser.id == data["sub"]))
    user = result.scalar_one_or_none()
    if not user or not user.is_active or not user.two_factor_enabled or not user.two_factor_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Estado de autenticación inválido")

    if not verify_totp(user.two_factor_secret, totp_code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Código 2FA incorrecto")

    user.last_login_at = datetime.now(timezone.utc)
    await log_action(db, user, "auth.2fa.complete", "session", resource_name=user.username)
    access = create_access_token(str(user.id))
    refresh = create_refresh_token(str(user.id))
    response.set_cookie("worsyn_access", access, max_age=30 * 60, **_COOKIE)
    response.set_cookie("worsyn_refresh", refresh, max_age=7 * 24 * 60 * 60, **_COOKIE)
    return {
        "requires_2fa": False,
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "must_change_password": user.must_change_password,
        "role": user.role,
    }


# ── Me ────────────────────────────────────────────────────────────────────────

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
        "two_factor_enabled": user.two_factor_enabled,
        "avatar": user.avatar,
        "created_at": user.created_at.isoformat(),
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


# ── Change credentials ────────────────────────────────────────────────────────

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

    changed: list[str] = []
    if new_username:
        if len(new_username) < 3:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username must be at least 3 characters")
        existing = await db.execute(select(AdminUser).where(AdminUser.username == new_username))
        if existing.scalar_one_or_none() and new_username != user.username:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")
        changed.append("username")
        user.username = new_username

    if new_password:
        if len(new_password) < 8:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 8 characters")
        changed.append("password")
        user.hashed_password = hash_password(new_password)

    user.must_change_password = False
    await log_action(db, user, "auth.credentials.change", "user",
                     str(user.id), user.username, {"changed": changed})
    return {"status": "ok", "username": user.username}


# ── 2FA Management (own account) ──────────────────────────────────────────────

@router.get("/2fa/setup")
async def setup_2fa(user: AdminUser = Depends(get_current_user)):
    """Generate a TOTP secret for the current user and return QR code.

    The secret is stored in Redis for 5 minutes pending verification via POST /auth/2fa/enable.
    """
    secret = generate_totp_secret()
    uri = get_totp_uri(secret, user.email)
    qr_b64 = generate_qr_base64(uri)

    r = _redis()
    r.setex(f"2fa_setup:{user.id}", 300, secret)

    return {
        "secret": secret,
        "qr_code": qr_b64,
        "uri": uri,
    }


@router.post("/2fa/enable")
async def enable_2fa(
    payload: dict,
    user: AdminUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify TOTP code from authenticator app and enable 2FA.

    Body: { "totp_code": str }
    Must be called after GET /auth/2fa/setup while the Redis session is alive.
    """
    totp_code = payload.get("totp_code", "")

    r = _redis()
    secret = r.get(f"2fa_setup:{user.id}")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sesión expirada. Inicia el proceso de configuración de nuevo.",
        )

    if not verify_totp(secret, totp_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código incorrecto. Verifica que el código de la app sea correcto e inténtalo de nuevo.",
        )

    user.two_factor_secret = secret
    user.two_factor_enabled = True
    r.delete(f"2fa_setup:{user.id}")
    await log_action(db, user, "auth.2fa.enable", "user", str(user.id), user.username)
    return {"status": "enabled"}


@router.post("/2fa/disable")
async def disable_2fa(
    payload: dict,
    user: AdminUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disable 2FA for the current user. Requires current TOTP code to confirm.

    Body: { "totp_code": str }
    """
    totp_code = payload.get("totp_code", "")

    if not user.two_factor_enabled or not user.two_factor_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El 2FA no está activado.")

    if not verify_totp(user.two_factor_secret, totp_code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Código incorrecto.")

    user.two_factor_secret = None
    user.two_factor_enabled = False
    await log_action(db, user, "auth.2fa.disable", "user", str(user.id), user.username)
    return {"status": "disabled"}
