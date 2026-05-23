"""Tenant module: Services → Person blockouts.

Per-ServiceMember unavailability ranges. Scoped under
/tenant/{slug}/services/people/{sm_id}/blockouts.

Auth:
  GET    — any service_member or org admin/leader
  POST   — admin/leader/coordinator OR the member themselves (self-edit)
  PATCH  — same as POST
  DELETE — same as POST
"""
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.models.models import (
    Organization, OrgMember, ServiceMember, ServiceMemberBlockout,
)

router = APIRouter(
    prefix="/tenant/{slug}/services/people/{sm_id}/blockouts",
    tags=["Tenant · Service People · Blockouts"],
)

VALID_REPEAT = {"none", "day", "week", "month", "year"}


async def _auth_and_target(
    slug: str, sm_id: str, authorization: str | None, cookie: str | None, db: AsyncSession,
) -> tuple[Organization, ServiceMember, OrgMember, OrgMember | None, str | None]:
    """Returns (org, target_sm, target_om, caller_om, caller_org_role).
    caller_om is None on impersonation. Raises if anything invalid."""
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else cookie
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado")
    data = decode_token(token)
    if data.get("type") != "tenant_access" or data.get("org_slug") != slug:
        raise HTTPException(status_code=401, detail="Token inválido")
    org = (await db.execute(select(Organization).where(Organization.slug == slug))).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Org no encontrada")
    try:
        smu = uuid.UUID(sm_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")
    row = (await db.execute(
        select(ServiceMember, OrgMember)
        .join(OrgMember, OrgMember.id == ServiceMember.member_id)
        .where(ServiceMember.id == smu, ServiceMember.org_id == org.id)
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Persona no encontrada")
    target_sm, target_om = row

    if data.get("impersonating"):
        return org, target_sm, target_om, None, "admin"
    caller = (await db.execute(
        select(OrgMember).where(OrgMember.id == uuid.UUID(data["sub"]), OrgMember.org_id == org.id)
    )).scalar_one_or_none()
    if caller is None:
        raise HTTPException(status_code=401, detail="Miembro no encontrado")
    return org, target_sm, target_om, caller, caller.role


def _can_view(caller_role: str | None) -> bool:
    return caller_role in ("admin", "leader", "member")  # any active member can view


def _can_edit(target_om: OrgMember, caller: OrgMember | None, caller_org_role: str | None, db_caller_svc_role: str | None) -> bool:
    if caller is None:
        return True  # impersonation
    if caller_org_role in ("admin", "leader"):
        return True
    if db_caller_svc_role in ("administrator", "editor", "coordinator"):
        return True
    if caller.id == target_om.id:
        return True  # self-edit
    return False


async def _caller_service_role(caller: OrgMember | None, db: AsyncSession) -> str | None:
    if caller is None:
        return None
    sm = (await db.execute(
        select(ServiceMember).where(ServiceMember.member_id == caller.id)
    )).scalar_one_or_none()
    return sm.service_role if sm else None


def _parse_date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Fecha inválida: {s} (YYYY-MM-DD)")


def _serialize(b: ServiceMemberBlockout) -> dict:
    return {
        "id": str(b.id),
        "start_date": b.start_date.isoformat(),
        "end_date": b.end_date.isoformat(),
        "all_day": b.all_day,
        "repeat_kind": b.repeat_kind,
        "repeat_interval": b.repeat_interval,
        "repeat_until": b.repeat_until.isoformat() if b.repeat_until else None,
        "reason": b.reason,
        "created_at": b.created_at.isoformat(),
    }


@router.get("")
async def list_blockouts(
    slug: str, sm_id: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, target_sm, _, caller, caller_role = await _auth_and_target(slug, sm_id, authorization, tenant_access, db)
    if not _can_view(caller_role):
        raise HTTPException(status_code=403, detail="Sin acceso")
    rows = (await db.execute(
        select(ServiceMemberBlockout)
        .where(ServiceMemberBlockout.service_member_id == target_sm.id)
        .order_by(ServiceMemberBlockout.start_date.desc())
    )).scalars().all()
    return [_serialize(b) for b in rows]


def _validate_payload(body: dict) -> dict:
    start = _parse_date(body.get("start_date") or "")
    end = _parse_date(body.get("end_date") or body.get("start_date") or "")
    if end < start:
        raise HTTPException(status_code=400, detail="La fecha de fin debe ser igual o posterior")
    rk = (body.get("repeat_kind") or "none").lower()
    if rk not in VALID_REPEAT:
        raise HTTPException(status_code=400, detail=f"repeat_kind inválido: {rk}")
    ri = int(body.get("repeat_interval") or 1)
    if ri < 1 or ri > 12:
        raise HTTPException(status_code=400, detail="repeat_interval fuera de rango (1–12)")
    ru = body.get("repeat_until")
    repeat_until = _parse_date(ru) if ru else None
    if repeat_until is not None and repeat_until < start:
        raise HTTPException(status_code=400, detail="repeat_until no puede ser anterior al inicio")
    return {
        "start_date": start, "end_date": end,
        "all_day": bool(body.get("all_day", True)),
        "repeat_kind": rk if rk != "none" else "none",
        "repeat_interval": ri if rk != "none" else 1,
        "repeat_until": repeat_until if rk != "none" else None,
        "reason": (body.get("reason") or None) or None,
    }


@router.post("", status_code=201)
async def create_blockout(
    slug: str, sm_id: str, body: dict,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, target_sm, target_om, caller, caller_role = await _auth_and_target(slug, sm_id, authorization, tenant_access, db)
    svc_role = await _caller_service_role(caller, db)
    if not _can_edit(target_om, caller, caller_role, svc_role):
        raise HTTPException(status_code=403, detail="Sin permiso para editar bloqueos")
    data = _validate_payload(body)
    b = ServiceMemberBlockout(
        org_id=org.id, service_member_id=target_sm.id,
        **data,
    )
    db.add(b)
    await db.flush()
    await db.refresh(b)
    return _serialize(b)


@router.patch("/{blockout_id}")
async def update_blockout(
    slug: str, sm_id: str, blockout_id: str, body: dict,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, target_sm, target_om, caller, caller_role = await _auth_and_target(slug, sm_id, authorization, tenant_access, db)
    svc_role = await _caller_service_role(caller, db)
    if not _can_edit(target_om, caller, caller_role, svc_role):
        raise HTTPException(status_code=403, detail="Sin permiso para editar bloqueos")
    try:
        bid = uuid.UUID(blockout_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")
    b = (await db.execute(
        select(ServiceMemberBlockout).where(
            ServiceMemberBlockout.id == bid,
            ServiceMemberBlockout.service_member_id == target_sm.id,
        )
    )).scalar_one_or_none()
    if b is None:
        raise HTTPException(status_code=404, detail="Bloqueo no encontrado")
    data = _validate_payload({
        "start_date": body.get("start_date", b.start_date.isoformat()),
        "end_date": body.get("end_date", b.end_date.isoformat()),
        "all_day": body.get("all_day", b.all_day),
        "repeat_kind": body.get("repeat_kind", b.repeat_kind),
        "repeat_interval": body.get("repeat_interval", b.repeat_interval),
        "repeat_until": body.get("repeat_until", b.repeat_until.isoformat() if b.repeat_until else None),
        "reason": body.get("reason", b.reason),
    })
    for k, v in data.items():
        setattr(b, k, v)
    await db.flush()
    return _serialize(b)


@router.delete("/{blockout_id}", status_code=204)
async def delete_blockout(
    slug: str, sm_id: str, blockout_id: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, target_sm, target_om, caller, caller_role = await _auth_and_target(slug, sm_id, authorization, tenant_access, db)
    svc_role = await _caller_service_role(caller, db)
    if not _can_edit(target_om, caller, caller_role, svc_role):
        raise HTTPException(status_code=403, detail="Sin permiso")
    try:
        bid = uuid.UUID(blockout_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")
    b = (await db.execute(
        select(ServiceMemberBlockout).where(
            ServiceMemberBlockout.id == bid,
            ServiceMemberBlockout.service_member_id == target_sm.id,
        )
    )).scalar_one_or_none()
    if b is None:
        raise HTTPException(status_code=404, detail="Bloqueo no encontrado")
    await db.delete(b)
