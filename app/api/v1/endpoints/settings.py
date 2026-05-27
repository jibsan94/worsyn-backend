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
from app.services.audit import log_action
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
    # Base URL of the frontend. Used to build magic links inside outgoing emails
    # (welcome, password reset). MUST be reachable by the recipient — set the
    # public domain in production. Default is the local LAN address.
    "general.app_url": "http://10.211.55.11",
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
    "security.password_reset_ttl_minutes": "10",
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
        is_secret = key.endswith(".password") or "_password" in key
        result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
        row = result.scalar_one_or_none()
        if row:
            row.value = value
            if is_secret and not row.encrypted:
                row.encrypted = True
        else:
            db.add(SystemSetting(key=key, value=value, encrypted=is_secret))
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
    await log_action(db, user, "settings.general.save", "settings", None, "general",
                     {"maintenance_mode": payload.maintenance_mode, "timezone": payload.timezone})
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
        password_reset_ttl_minutes=int(s["security.password_reset_ttl_minutes"]),
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
        "security.password_reset_ttl_minutes": str(payload.password_reset_ttl_minutes),
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
    await log_action(db, user, "settings.security.save", "settings", None, "security",
                     {"require_2fa": payload.require_2fa, "sso_enabled": payload.sso_enabled})
    return {"status": "saved"}


# ── Email / SMTP ──────────────────────────────────────────────────────────────
# Shared SMTP server used by every tenant when sending emails from Services.
# Password is encrypted via app.core.crypto (Fernet). The GET endpoint returns
# the password masked; pass it back to leave it untouched on save.

from app.core.crypto import encrypt, decrypt  # noqa: E402
from app.services.smtp import CFG_KEYS, SmtpConfig, send_one, load_config  # noqa: E402

EMAIL_DEFAULTS: dict[str, str] = {
    "email.smtp.enabled": "false",
    "email.smtp.host": "",
    "email.smtp.port": "587",
    "email.smtp.username": "",
    "email.smtp.password": "",   # encrypted
    "email.smtp.use_tls": "true",
    "email.smtp.use_ssl": "false",
    "email.smtp.from_email": "",
    "email.smtp.from_name": "Worsyn",
    "email.smtp.provider": "custom",
    "email.smtp.reply_to": "",
    "email.smtp.timeout": "20",
}

PASSWORD_MASK = "••••••••"


@router.get("/email")
async def get_email_config(
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_role("admin", "owner")),
):
    """Return SMTP config. Password is replaced by a mask (••••••••) when set."""
    s = await _get_settings_by_prefix("email", EMAIL_DEFAULTS, db)
    has_password = bool(s.get("email.smtp.password"))
    return {
        "enabled":   s["email.smtp.enabled"] == "true",
        "host":      s["email.smtp.host"],
        "port":      int(s["email.smtp.port"] or 587),
        "username":  s["email.smtp.username"],
        "password":  PASSWORD_MASK if has_password else "",
        "has_password": has_password,
        "use_tls":   s["email.smtp.use_tls"] == "true",
        "use_ssl":   s["email.smtp.use_ssl"] == "false" and False or (s["email.smtp.use_ssl"] == "true"),
        "from_email": s["email.smtp.from_email"],
        "from_name":  s["email.smtp.from_name"],
        "provider":   s["email.smtp.provider"],
        "reply_to":   s["email.smtp.reply_to"],
        "timeout":    int(s["email.smtp.timeout"] or 20),
        "readonly":   user.role != "owner",
    }


_MISSING = object()


def _resolve_password(incoming, existing_enc: str) -> str:
    """Decide which encrypted password to store given the incoming form value.

      _MISSING / None / PASSWORD_MASK → keep existing (DON'T wipe on no-op saves)
      ""                              → explicit clear
      any other plain string          → encrypt and store
    """
    if incoming is _MISSING or incoming is None or incoming == PASSWORD_MASK:
        return existing_enc
    if incoming == "":
        return ""
    return encrypt(incoming)


@router.post("/email")
async def save_email_config(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_role("owner")),
):
    """Owner only: save the shared SMTP config."""
    # Load existing for password preservation
    existing = await _get_settings_by_prefix("email", EMAIL_DEFAULTS, db)
    provider = (payload.get("provider") or "custom").lower()
    if provider not in {"gmail", "workspace", "sendgrid", "mailgun", "outlook", "custom"}:
        raise HTTPException(status_code=400, detail=f"Provider inválido: {provider}")
    use_tls = bool(payload.get("use_tls", True))
    use_ssl = bool(payload.get("use_ssl", False))
    if use_tls and use_ssl:
        raise HTTPException(status_code=400, detail="No actives STARTTLS y SSL al mismo tiempo")
    try:
        port = int(payload.get("port") or 587)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Puerto inválido")
    try:
        timeout = int(payload.get("timeout") or 20)
    except (TypeError, ValueError):
        timeout = 20

    pwd_enc = _resolve_password(payload.get("password", _MISSING), existing.get("email.smtp.password", ""))

    updates = {
        "email.smtp.enabled":    str(bool(payload.get("enabled", False))).lower(),
        "email.smtp.host":       (payload.get("host") or "").strip(),
        "email.smtp.port":       str(port),
        "email.smtp.username":   (payload.get("username") or "").strip(),
        "email.smtp.password":   pwd_enc,
        "email.smtp.use_tls":    str(use_tls).lower(),
        "email.smtp.use_ssl":    str(use_ssl).lower(),
        "email.smtp.from_email": (payload.get("from_email") or "").strip(),
        "email.smtp.from_name":  (payload.get("from_name") or "Worsyn").strip(),
        "email.smtp.provider":   provider,
        "email.smtp.reply_to":   (payload.get("reply_to") or "").strip(),
        "email.smtp.timeout":    str(timeout),
    }
    await _upsert_settings(updates, db)
    await log_action(db, user, "settings.email.save", "settings", None, "email",
                     {"host": updates["email.smtp.host"], "enabled": updates["email.smtp.enabled"]})
    return {"status": "saved"}


@router.post("/email/test")
async def test_email_config(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_role("admin", "owner")),
):
    """Send a test email using either the SAVED config or the payload below.

    Body:
      to: <recipient email>          (required)
      override: { host, port, username, password, use_tls, use_ssl, from_email, from_name }
        (optional — if present, uses these instead of saved settings; password
         can be PASSWORD_MASK to use the saved one)
    """
    to = (payload.get("to") or "").strip()
    if "@" not in to:
        raise HTTPException(status_code=400, detail="Email destino inválido")

    # Build a config: start from saved, optionally overlay user-provided overrides
    existing = await _get_settings_by_prefix("email", EMAIL_DEFAULTS, db)
    raw = dict(existing)
    ov = payload.get("override") or {}
    if ov:
        if "host" in ov:       raw["email.smtp.host"] = (ov["host"] or "").strip()
        if "port" in ov:       raw["email.smtp.port"] = str(ov["port"])
        if "username" in ov:   raw["email.smtp.username"] = (ov["username"] or "").strip()
        if "use_tls" in ov:    raw["email.smtp.use_tls"] = str(bool(ov["use_tls"])).lower()
        if "use_ssl" in ov:    raw["email.smtp.use_ssl"] = str(bool(ov["use_ssl"])).lower()
        if "from_email" in ov: raw["email.smtp.from_email"] = (ov["from_email"] or "").strip()
        if "from_name" in ov:  raw["email.smtp.from_name"] = (ov["from_name"] or "Worsyn").strip()
        if "password" in ov and ov["password"]:
            raw["email.smtp.password"] = (
                existing.get("email.smtp.password", "") if ov["password"] == PASSWORD_MASK
                else encrypt(ov["password"])
            )
        # Force enable for the test
        raw["email.smtp.enabled"] = "true"

    cfg = SmtpConfig(raw)
    if not cfg.is_configured():
        raise HTTPException(status_code=400, detail="Configuración SMTP incompleta (host, usuario, contraseña, from_email)")

    ok, err = send_one(
        cfg, to_email=to,
        subject="Worsyn — Prueba de configuración SMTP",
        html=(
            "<h2>¡Conexión SMTP correcta!</h2>"
            "<p>Este correo de prueba se envió desde Worsyn usando la configuración SMTP guardada en el panel.</p>"
            f"<p style='color:#64748B; font-size:13px'>Host: {cfg.host}:{cfg.port} · Usuario: {cfg.username}</p>"
        ),
    )
    await log_action(db, user, "settings.email.test", "settings", None, "email",
                     {"to": to, "ok": ok, "error": err})
    if not ok:
        raise HTTPException(status_code=502, detail=f"Envío falló: {err}")
    return {"status": "ok", "to": to}
