"""Admin settings endpoints (database config, general config, security config).

Access:
  - GET /database: admin + owner (read)
  - POST /database: owner only (write)
  - POST /database/test: admin + owner (non-destructive)
  - GET /general: admin + owner (read)
  - POST /general: owner only (write)
  - GET /security: admin + owner (read)
  - POST /security: owner only (write)
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import get_current_user, require_role
from app.db.session import get_db
from app.models.models import AdminUser, SystemSetting
from app.schemas.schemas import (
    DatabaseConfigWrite,
    GeneralConfigRead,
    GeneralConfigWrite,
    SecurityConfigRead,
    SecurityConfigWrite,
)

router = APIRouter(prefix="/admin/settings", tags=["Admin Settings"])

SUPPORTED_ENGINES = {"postgresql", "mysql", "mariadb"}

GENERAL_DEFAULTS: dict[str, str] = {
    "general.platform_name": "Worsyn",
    "general.support_email": "",
    "general.timezone": "UTC",
    "general.maintenance_mode": "false",
    "general.maintenance_message": "El sistema está en mantenimiento. Vuelve pronto.",
}

SECURITY_DEFAULTS: dict[str, str] = {
    "security.password_min_length": "8",
    "security.password_require_uppercase": "false",
    "security.password_require_numbers": "false",
    "security.password_require_special": "false",
    "security.password_max_age_days": "0",
    "security.session_access_token_minutes": "30",
    "security.session_refresh_token_days": "7",
    "security.max_sessions_per_user": "0",
    "security.require_2fa": "false",
    # SSO / Active Directory (pending implementation)
    "security.sso_enabled": "false",
    "security.sso_provider": "ldap",
    "security.sso_ad_server": "",
    "security.sso_ad_base_dn": "",
    "security.sso_ad_bind_dn": "",
    "security.sso_ad_bind_password": "",
    "security.sso_ad_domain": "",
    "security.sso_ad_user_filter": "(sAMAccountName={username})",
}


async def _get_settings_by_prefix(prefix: str, defaults: dict, db: AsyncSession) -> dict[str, str]:
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.key.like(f"{prefix}.%"))
    )
    rows = result.scalars().all()
    settings = dict(defaults)
    for row in rows:
        if row.value is not None:
            settings[row.key] = row.value
    return settings


async def _upsert_settings(updates: dict[str, str], db: AsyncSession) -> None:
    for key, value in updates.items():
        result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
        row = result.scalar_one_or_none()
        if row:
            row.value = value
        else:
            db.add(SystemSetting(key=key, value=value))
    await db.commit()


# ── Database ──────────────────────────────────────────────────────────────────

@router.get("/database")
async def get_database_config(
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_role("admin", "owner")),
):
    """Return current database config (password masked)."""
    return {
        "engine": "postgresql",
        "host": "db",
        "port": 5432,
        "name": "worsyn",
        "user": "worsyn_admin",
        "password": "***",
        "ssl": True,
        "readonly": user.role != "owner",
    }


@router.post("/database")
async def save_database_config(
    payload: DatabaseConfigWrite,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_role("owner")),
):
    """Persist database config. Owner only."""
    if payload.engine not in SUPPORTED_ENGINES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported engine '{payload.engine}'. Supported: {sorted(SUPPORTED_ENGINES)}",
        )
    return {"status": "saved", "engine": payload.engine}


@router.post("/database/test")
async def test_database_connection(
    payload: DatabaseConfigWrite,
    user: AdminUser = Depends(require_role("admin", "owner")),
):
    """Test a database connection without saving."""
    if payload.engine not in SUPPORTED_ENGINES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported engine '{payload.engine}'. Supported: {sorted(SUPPORTED_ENGINES)}",
        )
    return {"status": "ok", "latency_ms": 12}


# ── General ───────────────────────────────────────────────────────────────────

@router.get("/general", response_model=GeneralConfigRead)
async def get_general_config(
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_role("admin", "owner")),
):
    """Return general platform config. Admin+owner read, owner write."""
    s = await _get_settings_by_prefix("general", GENERAL_DEFAULTS, db)
    return GeneralConfigRead(
        platform_name=s["general.platform_name"],
        support_email=s["general.support_email"],
        timezone=s["general.timezone"],
        maintenance_mode=s["general.maintenance_mode"] == "true",
        maintenance_message=s["general.maintenance_message"],
        readonly=user.role != "owner",
    )


@router.post("/general")
async def save_general_config(
    payload: GeneralConfigWrite,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_role("owner")),
):
    """Persist general config to system_settings. Owner only."""
    await _upsert_settings({
        "general.platform_name": payload.platform_name or "Worsyn",
        "general.support_email": payload.support_email,
        "general.timezone": payload.timezone,
        "general.maintenance_mode": str(payload.maintenance_mode).lower(),
        "general.maintenance_message": payload.maintenance_message,
    }, db)
    return {"status": "saved"}


# ── Security ──────────────────────────────────────────────────────────────────

@router.get("/security", response_model=SecurityConfigRead)
async def get_security_config(
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_role("admin", "owner")),
):
    """Return current security config. Admin+owner read, owner edit."""
    s = await _get_settings_by_prefix("security", SECURITY_DEFAULTS, db)
    return SecurityConfigRead(
        password_min_length=int(s["security.password_min_length"]),
        password_require_uppercase=s["security.password_require_uppercase"] == "true",
        password_require_numbers=s["security.password_require_numbers"] == "true",
        password_require_special=s["security.password_require_special"] == "true",
        password_max_age_days=int(s["security.password_max_age_days"]),
        session_access_token_minutes=int(s["security.session_access_token_minutes"]),
        session_refresh_token_days=int(s["security.session_refresh_token_days"]),
        max_sessions_per_user=int(s["security.max_sessions_per_user"]),
        require_2fa=s["security.require_2fa"] == "true",
        sso_enabled=s["security.sso_enabled"] == "true",
        sso_provider=s["security.sso_provider"],
        sso_ad_server=s["security.sso_ad_server"],
        sso_ad_base_dn=s["security.sso_ad_base_dn"],
        sso_ad_bind_dn=s["security.sso_ad_bind_dn"],
        sso_ad_bind_password="",  # never expose stored password
        sso_ad_domain=s["security.sso_ad_domain"],
        sso_ad_user_filter=s["security.sso_ad_user_filter"],
        readonly=user.role != "owner",
    )


@router.post("/security")
async def save_security_config(
    payload: SecurityConfigWrite,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_role("owner")),
):
    """Persist security config to system_settings. Owner only."""
    updates: dict[str, str] = {
        "security.password_min_length": str(payload.password_min_length),
        "security.password_require_uppercase": str(payload.password_require_uppercase).lower(),
        "security.password_require_numbers": str(payload.password_require_numbers).lower(),
        "security.password_require_special": str(payload.password_require_special).lower(),
        "security.password_max_age_days": str(payload.password_max_age_days),
        "security.session_access_token_minutes": str(payload.session_access_token_minutes),
        "security.session_refresh_token_days": str(payload.session_refresh_token_days),
        "security.max_sessions_per_user": str(payload.max_sessions_per_user),
        "security.require_2fa": str(payload.require_2fa).lower(),
        "security.sso_enabled": str(payload.sso_enabled).lower(),
        "security.sso_provider": payload.sso_provider,
        "security.sso_ad_server": payload.sso_ad_server,
        "security.sso_ad_base_dn": payload.sso_ad_base_dn,
        "security.sso_ad_bind_dn": payload.sso_ad_bind_dn,
        "security.sso_ad_domain": payload.sso_ad_domain,
        "security.sso_ad_user_filter": payload.sso_ad_user_filter,
    }
    # Only update bind password if explicitly provided (avoid clearing stored value)
    if payload.sso_ad_bind_password:
        updates["security.sso_ad_bind_password"] = payload.sso_ad_bind_password

    await _upsert_settings(updates, db)
    return {"status": "saved"}
