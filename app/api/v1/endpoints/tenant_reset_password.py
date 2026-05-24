"""Public password-reset endpoints for tenant org_members.

Triggered by the welcome email (and later by the "forgot password" flow).
The magic link is `/set-password/{token}` on the frontend — it calls these.

Endpoints (NO AUTH required — the token IS the auth):

  GET  /tenant/auth/reset-password/{token}
       → { email, full_name, org_name, org_slug, expires_at } or 404 if invalid/expired/used

  POST /tenant/auth/reset-password/{token}   body: { password }
       → 200 { org_slug } on success — frontend uses org_slug for "Ir a Servicios" button
       → 400 / 404 on validation failure
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.session import get_db
from app.models.models import OrgMember, Organization

router = APIRouter(prefix="/tenant/auth/reset-password", tags=["Tenant · Reset Password"])

MIN_PASSWORD_LEN = 8


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _load_valid_member(token: str, db: AsyncSession) -> tuple[OrgMember, Organization]:
    if not token or len(token) < 16:
        raise HTTPException(status_code=404, detail="Token inválido")
    row = (await db.execute(
        select(OrgMember, Organization)
        .join(Organization, Organization.id == OrgMember.org_id)
        .where(OrgMember.password_reset_token == token)
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Enlace inválido o ya utilizado")
    om, org = row
    if om.password_reset_expires_at is None or om.password_reset_expires_at < _now():
        raise HTTPException(status_code=410, detail="El enlace ha caducado. Pide al administrador que reenvíe la invitación.")
    return om, org


@router.get("/{token}")
async def info(token: str, db: AsyncSession = Depends(get_db)):
    om, org = await _load_valid_member(token, db)
    return {
        "email": om.email,
        "full_name": om.full_name,
        "org_name": org.name,
        "org_slug": org.slug,
        "expires_at": om.password_reset_expires_at.isoformat() if om.password_reset_expires_at else None,
    }


@router.post("/{token}")
async def submit(token: str, body: dict, db: AsyncSession = Depends(get_db)):
    om, org = await _load_valid_member(token, db)
    pwd = (body.get("password") or "").strip()
    if len(pwd) < MIN_PASSWORD_LEN:
        raise HTTPException(status_code=400, detail=f"La contraseña debe tener al menos {MIN_PASSWORD_LEN} caracteres")
    if pwd.lower() in ("password", "12345678", "contraseña", "worsyn"):
        raise HTTPException(status_code=400, detail="Contraseña demasiado común")
    om.hashed_password = hash_password(pwd)
    om.password_reset_token = None
    om.password_reset_expires_at = None
    await db.flush()
    return {"org_slug": org.slug, "email": om.email}
