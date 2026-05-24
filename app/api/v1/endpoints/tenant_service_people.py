"""Tenant module: Services → People (service module permissions).

Manages who has access to the Services module within a tenant and at what level.
Inspired by Planning Center: per-section roles + per-service-type overrides +
file-access flags + welcome flow (set initial password).

Auto-provisioning: on first GET, any org_member with org-role 'admin' that does
not yet have a service_members row is inserted as service_role='administrator'.
This ensures the first org admin always shows up here.

Roles:
  service_role:  administrator | editor | coordinator | viewer | scheduled_viewer
  songs_role / media_role: administrator | editor | viewer | scheduled_viewer  (no coordinator)

Access rules in this file:
  - GET    requires any service_member or org admin/leader.
  - POST   requires service administrator OR org admin (auto-promotion path).
  - PATCH  requires service administrator OR org admin.
  - DELETE requires service administrator OR org admin (editor cannot delete people).
"""
import base64
import re
import secrets
import string
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token, hash_password
from app.db.session import get_db
from app.models.models import (
    Organization, OrgMember, ServiceMember, ServiceMemberTypePerm, ServiceType,
    Team, TeamMembership,
)

router = APIRouter(prefix="/tenant/{slug}/services/people", tags=["Tenant · Service People"])

VALID_SERVICE_ROLES = {"administrator", "editor", "coordinator", "viewer", "scheduled_viewer"}
VALID_AREA_ROLES = {"administrator", "editor", "viewer", "scheduled_viewer"}  # no coordinator for songs/media

SIGNATURE_IMAGE_MAX_BYTES = 1 * 1024 * 1024  # 1 MB decoded
_DATA_URL_RE = re.compile(r"^data:(image/[a-zA-Z0-9+.-]+);base64,(.+)$", re.DOTALL)


def _validate_signature_image(value: str | None) -> str | None:
    """Accepts a base64 data URL (image/*) ≤1 MB decoded, or null to clear."""
    if value is None or value == "":
        return None
    m = _DATA_URL_RE.match(value)
    if not m:
        raise HTTPException(status_code=400, detail="Imagen inválida (debe ser data URL base64 de tipo image/*)")
    try:
        raw = base64.b64decode(m.group(2), validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Imagen inválida (base64 corrupto)")
    if len(raw) > SIGNATURE_IMAGE_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Imagen demasiado grande (máx. 1 MB)")
    return value


# ── Auth ──────────────────────────────────────────────────────────────────────
async def _auth(slug: str, authorization: str | None, cookie: str | None, db: AsyncSession):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else cookie
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado")
    data = decode_token(token)
    if data.get("type") != "tenant_access" or data.get("org_slug") != slug:
        raise HTTPException(status_code=401, detail="Token inválido")
    org = (await db.execute(select(Organization).where(Organization.slug == slug))).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Org no encontrada")
    if data.get("impersonating"):
        return org, None, "admin", "administrator"
    caller = (await db.execute(
        select(OrgMember).where(OrgMember.id == uuid.UUID(data["sub"]), OrgMember.org_id == org.id)
    )).scalar_one_or_none()
    if caller is None:
        raise HTTPException(status_code=401, detail="Miembro no encontrado")
    sm = (await db.execute(
        select(ServiceMember).where(ServiceMember.member_id == caller.id)
    )).scalar_one_or_none()
    svc_role = sm.service_role if sm else None
    return org, caller, caller.role, svc_role


def _can_manage_people(org_role: str | None, svc_role: str | None) -> bool:
    return org_role in ("admin", "leader") or svc_role == "administrator"


def _can_view_people(org_role: str | None, svc_role: str | None) -> bool:
    return org_role in ("admin", "leader") or svc_role is not None


async def _autoprovision_admins(org_id: uuid.UUID, db: AsyncSession) -> None:
    """For every org_member with role='admin' that lacks a service_members row,
    insert one with service_role='administrator'. Idempotent."""
    rows = (await db.execute(
        select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.role == "admin")
    )).scalars().all()
    if not rows:
        return
    member_ids = [r.id for r in rows]
    existing = set(x.member_id for x in (await db.execute(
        select(ServiceMember).where(ServiceMember.member_id.in_(member_ids))
    )).scalars().all())
    for m in rows:
        if m.id in existing:
            continue
        db.add(ServiceMember(
            org_id=org_id, member_id=m.id, service_role="administrator",
            songs_role="administrator", media_role="administrator",
            file_access_plans=True, file_access_songs=True, file_access_media=True,
        ))
    await db.flush()


async def _serialize(sm: ServiceMember, om: OrgMember, db: AsyncSession) -> dict:
    overrides = (await db.execute(
        select(ServiceMemberTypePerm).where(ServiceMemberTypePerm.service_member_id == sm.id)
    )).scalars().all()
    return {
        "id": str(sm.id),
        "member_id": str(om.id),
        "full_name": om.full_name, "email": om.email, "avatar": om.avatar,
        "org_role": om.role,
        "service_role": sm.service_role,
        "songs_role": sm.songs_role,
        "media_role": sm.media_role,
        "file_access": {
            "plans": sm.file_access_plans,
            "songs": sm.file_access_songs,
            "media": sm.file_access_media,
        },
        "type_permissions": [
            {"service_type_id": str(o.service_type_id), "role": o.role}
            for o in overrides
        ],
        "welcomed_at": sm.welcomed_at.isoformat() if sm.welcomed_at else None,
        "password_set": sm.password_set_at is not None or bool(om.hashed_password),
        "created_at": sm.created_at.isoformat(),
        "scheduling": {
            "max_per_month": sm.scheduling_max_per_month,  # null = unlimited
            "max_per_day": sm.scheduling_max_per_day,      # null = unlimited
        },
        "signature": {
            "text":  sm.signature_text,
            "image": sm.signature_image,  # full data: URL or null
        },
        "preferred_notif_app": sm.preferred_notif_app,
        # TEST-ONLY — plaintext password stored for local QA. Remove before prod.
        "debug_password": sm.debug_password,
    }


# ── List ──────────────────────────────────────────────────────────────────────
@router.get("")
async def list_service_people(
    slug: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, caller, org_role, svc_role = await _auth(slug, authorization, tenant_access, db)
    if not _can_view_people(org_role, svc_role):
        raise HTTPException(status_code=403, detail="Sin acceso al módulo de Servicios")
    await _autoprovision_admins(org.id, db)
    rows = (await db.execute(
        select(ServiceMember, OrgMember)
        .join(OrgMember, OrgMember.id == ServiceMember.member_id)
        .where(ServiceMember.org_id == org.id)
        .order_by(OrgMember.full_name)
    )).all()
    return [await _serialize(sm, om, db) for sm, om in rows]


# ── Create ────────────────────────────────────────────────────────────────────
def _gen_temp_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _validate_perms(body: dict) -> tuple[str, str | None, str | None]:
    svc_r = (body.get("service_role") or "viewer").lower()
    if svc_r not in VALID_SERVICE_ROLES:
        raise HTTPException(status_code=400, detail=f"service_role inválido: {svc_r}")
    songs_r = body.get("songs_role")
    if songs_r is not None and songs_r not in VALID_AREA_ROLES:
        raise HTTPException(status_code=400, detail=f"songs_role inválido: {songs_r}")
    media_r = body.get("media_role")
    if media_r is not None and media_r not in VALID_AREA_ROLES:
        raise HTTPException(status_code=400, detail=f"media_role inválido: {media_r}")
    return svc_r, songs_r, media_r


@router.post("", status_code=201)
async def add_service_person(
    slug: str, body: dict,
    background: BackgroundTasks,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Add a person to the Services module.

    Body:
      Existing member:    { "member_id": "<uuid>", ...perms }
      New member:         { "new_member": {"full_name", "email", "phone?"}, ...perms }
      ...perms:
        service_role, songs_role, media_role,
        file_access: { plans, songs, media },
        type_permissions: [ { service_type_id, role? } ],
        send_welcome: bool
    """
    org, caller, org_role, svc_role = await _auth(slug, authorization, tenant_access, db)
    if not _can_manage_people(org_role, svc_role):
        raise HTTPException(status_code=403, detail="Solo administradores pueden añadir personas")

    # Resolve / create OrgMember
    om: OrgMember | None = None
    temp_password: str | None = None
    if body.get("member_id"):
        try:
            mid = uuid.UUID(body["member_id"])
        except Exception:
            raise HTTPException(status_code=400, detail="member_id inválido")
        om = (await db.execute(
            select(OrgMember).where(OrgMember.id == mid, OrgMember.org_id == org.id)
        )).scalar_one_or_none()
        if om is None:
            raise HTTPException(status_code=404, detail="Miembro no encontrado")
    elif body.get("new_member"):
        nm = body["new_member"]
        email = (nm.get("email") or "").strip().lower()
        full_name = (nm.get("full_name") or "").strip()
        if not email or "@" not in email:
            raise HTTPException(status_code=400, detail="Email inválido")
        if not full_name:
            raise HTTPException(status_code=400, detail="Nombre requerido")
        dup = (await db.execute(
            select(OrgMember).where(OrgMember.org_id == org.id, OrgMember.email == email)
        )).scalar_one_or_none()
        if dup is not None:
            raise HTTPException(status_code=409, detail="Ese email ya existe en la organización")
        om = OrgMember(
            org_id=org.id, email=email, full_name=full_name,
            phone=(nm.get("phone") or None), role="member", is_active=True,
        )
        db.add(om)
        await db.flush()
    else:
        raise HTTPException(status_code=400, detail="Indica member_id o new_member")

    # Dup check on service_members
    dup_sm = (await db.execute(
        select(ServiceMember).where(ServiceMember.member_id == om.id)
    )).scalar_one_or_none()
    if dup_sm is not None:
        raise HTTPException(status_code=409, detail="Esta persona ya pertenece a Servicios")

    svc_r, songs_r, media_r = _validate_perms(body)
    fa = body.get("file_access") or {}

    sm = ServiceMember(
        org_id=org.id, member_id=om.id,
        service_role=svc_r, songs_role=songs_r, media_role=media_r,
        file_access_plans=bool(fa.get("plans", True)),
        file_access_songs=bool(fa.get("songs", True)),
        file_access_media=bool(fa.get("media", True)),
    )
    db.add(sm)
    await db.flush()

    # Per-type overrides
    for o in (body.get("type_permissions") or []):
        try:
            stid = uuid.UUID(o.get("service_type_id") or "")
        except Exception:
            continue
        ok = (await db.execute(
            select(ServiceType).where(ServiceType.id == stid, ServiceType.org_id == org.id)
        )).scalar_one_or_none()
        if ok is None:
            continue
        role_override = o.get("role")
        if role_override is not None and role_override not in VALID_SERVICE_ROLES:
            continue
        db.add(ServiceMemberTypePerm(service_member_id=sm.id, service_type_id=stid, role=role_override))

    # Welcome — send the magic-link email via SMTP. Skipped entirely for org
    # admins (they already have a tenant-level password). Falls back to legacy
    # temp_password path if SMTP isn't configured yet, so the admin can still
    # share creds manually.
    welcome_url: str | None = None
    if body.get("send_welcome") and om.role != "admin":
        sm.welcomed_at = datetime.now(timezone.utc)
        from app.api.v1.endpoints.tenant_email import send_welcome_email  # local import to avoid cycle
        from app.services.smtp import load_config
        smtp_cfg = await load_config(db)
        if smtp_cfg.is_configured():
            _, welcome_url = await send_welcome_email(
                org=org, recipient_member=om, sender_member=caller,
                db=db, background=background,
            )
        elif not om.hashed_password:
            # SMTP missing → legacy fallback (admin shares manually). Test-only.
            temp_password = _gen_temp_password()
            om.hashed_password = hash_password(temp_password)
            sm.debug_password = temp_password

    await db.flush()
    await db.refresh(sm)
    await db.refresh(om)
    out = await _serialize(sm, om, db)
    if temp_password is not None:
        out["temp_password"] = temp_password  # SMTP-not-configured fallback
    if welcome_url is not None:
        out["welcome_url"] = welcome_url  # so admin can copy if needed
    return out


# ── Update ────────────────────────────────────────────────────────────────────
@router.patch("/{sm_id}")
async def update_service_person(
    slug: str, sm_id: str, body: dict,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, caller, org_role, svc_role = await _auth(slug, authorization, tenant_access, db)
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
    sm, om = row

    # Permission split: signature is self-editable; everything else (roles,
    # file_access, scheduling caps, type permissions) requires admin/leader/svc admin.
    is_self = caller is not None and caller.id == om.id
    # Both 'signature' and 'preferred_notif_app' are self-editable; everything
    # else (roles, file_access, scheduling caps, type permissions) requires admin.
    self_editable = {"signature", "preferred_notif_app"}
    admin_only_keys = set(body.keys()) - self_editable
    if admin_only_keys and not _can_manage_people(org_role, svc_role):
        raise HTTPException(status_code=403, detail="Solo administradores pueden modificar permisos")
    if (body.keys() & self_editable) and not (is_self or _can_manage_people(org_role, svc_role)):
        raise HTTPException(status_code=403, detail="Sin permiso")

    if "service_role" in body or "songs_role" in body or "media_role" in body:
        svc_r, songs_r, media_r = _validate_perms({
            "service_role": body.get("service_role", sm.service_role),
            "songs_role": body.get("songs_role", sm.songs_role),
            "media_role": body.get("media_role", sm.media_role),
        })
        sm.service_role = svc_r
        if "songs_role" in body: sm.songs_role = songs_r
        if "media_role" in body: sm.media_role = media_r

    if "file_access" in body and isinstance(body["file_access"], dict):
        fa = body["file_access"]
        if "plans" in fa: sm.file_access_plans = bool(fa["plans"])
        if "songs" in fa: sm.file_access_songs = bool(fa["songs"])
        if "media" in fa: sm.file_access_media = bool(fa["media"])

    if "scheduling" in body and isinstance(body["scheduling"], dict):
        sc = body["scheduling"]
        def _cap(v: object) -> int | None:
            if v is None or v == "" or v == 0:
                return None
            n = int(v)
            if n < 1 or n > 31:
                raise HTTPException(status_code=400, detail="scheduling cap fuera de rango (1–31 o null)")
            return n
        if "max_per_month" in sc:
            sm.scheduling_max_per_month = _cap(sc["max_per_month"])
        if "max_per_day" in sc:
            sm.scheduling_max_per_day = _cap(sc["max_per_day"])

    if "signature" in body and isinstance(body["signature"], dict):
        sig = body["signature"]
        if "text" in sig:
            v = sig["text"]
            sm.signature_text = (v or None) if isinstance(v, str) else None
            # Cap text to keep DB rows reasonable (~16 KB)
            if sm.signature_text is not None and len(sm.signature_text) > 16_000:
                raise HTTPException(status_code=400, detail="Firma de texto demasiado larga (máx. 16 000 caracteres)")
        if "image" in sig:
            sm.signature_image = _validate_signature_image(sig["image"])

    if "preferred_notif_app" in body:
        v = (body["preferred_notif_app"] or "").lower()
        if v not in ("servicios", "worsyn"):
            raise HTTPException(status_code=400, detail="preferred_notif_app inválido")
        sm.preferred_notif_app = v

    if "type_permissions" in body and isinstance(body["type_permissions"], list):
        existing = (await db.execute(
            select(ServiceMemberTypePerm).where(ServiceMemberTypePerm.service_member_id == sm.id)
        )).scalars().all()
        for x in existing:
            await db.delete(x)
        for o in body["type_permissions"]:
            try:
                stid = uuid.UUID(o.get("service_type_id") or "")
            except Exception:
                continue
            ok = (await db.execute(
                select(ServiceType).where(ServiceType.id == stid, ServiceType.org_id == org.id)
            )).scalar_one_or_none()
            if ok is None:
                continue
            role_override = o.get("role")
            if role_override is not None and role_override not in VALID_SERVICE_ROLES:
                continue
            db.add(ServiceMemberTypePerm(service_member_id=sm.id, service_type_id=stid, role=role_override))

    await db.flush()
    return await _serialize(sm, om, db)


# ── Delete ────────────────────────────────────────────────────────────────────
@router.delete("/{sm_id}", status_code=204)
async def delete_service_person(
    slug: str, sm_id: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, caller, org_role, svc_role = await _auth(slug, authorization, tenant_access, db)
    # editor cannot delete people — administrator only (org admin/leader also OK)
    if not _can_manage_people(org_role, svc_role):
        raise HTTPException(status_code=403, detail="Solo administradores pueden eliminar personas")
    try:
        smu = uuid.UUID(sm_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")
    # Join to fetch the target member's org_role for the self-delete guard
    row = (await db.execute(
        select(ServiceMember, OrgMember)
        .join(OrgMember, OrgMember.id == ServiceMember.member_id)
        .where(ServiceMember.id == smu, ServiceMember.org_id == org.id)
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Persona no encontrada")
    sm, om = row
    # Org admin cannot remove themselves from Services — another org admin must do it.
    # Caller is None when impersonating (admin from main panel) — that path is allowed.
    if caller is not None and om.role == "admin" and om.id == caller.id:
        raise HTTPException(
            status_code=403,
            detail="No puedes eliminarte a ti mismo. Pide a otro administrador que lo haga.",
        )
    await db.delete(sm)


# ── Send welcome (separate endpoint, idempotent) ──────────────────────────────
@router.post("/{sm_id}/welcome")
async def send_welcome(
    slug: str, sm_id: str,
    background: BackgroundTasks,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Issue a fresh magic-link token + queue the welcome email via SMTP.

    Falls back to legacy temp_password (returned ONCE) when SMTP isn't
    configured yet — admin shares manually until SMTP lands.
    """
    org, caller, org_role, svc_role = await _auth(slug, authorization, tenant_access, db)
    if not _can_manage_people(org_role, svc_role):
        raise HTTPException(status_code=403, detail="Solo administradores")
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
    sm, om = row
    if om.role == "admin":
        raise HTTPException(
            status_code=400,
            detail="El Administrador de la organización ya tiene contraseña del tenant",
        )

    from app.api.v1.endpoints.tenant_email import send_welcome_email  # local import
    from app.services.smtp import load_config
    smtp_cfg = await load_config(db)
    temp = None
    welcome_url: str | None = None
    if smtp_cfg.is_configured():
        _, welcome_url = await send_welcome_email(
            org=org, recipient_member=om, sender_member=caller,
            db=db, background=background,
        )
    elif not om.hashed_password:
        temp = _gen_temp_password()
        om.hashed_password = hash_password(temp)
        sm.debug_password = temp  # TEST-ONLY
    sm.welcomed_at = datetime.now(timezone.utc)
    await db.flush()
    return {
        "id": str(sm.id), "welcomed_at": sm.welcomed_at.isoformat(),
        "temp_password": temp,  # null if SMTP sent or user already has a password
        "welcome_url": welcome_url,
        "email": om.email,
    }


# ── TEST-ONLY: force-regenerate password and expose plaintext ─────────────────
# See /artifacts/CONTEXT.md "Para quitar antes de producción".
@router.post("/{sm_id}/reset-password")
async def reset_password_debug(
    slug: str, sm_id: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """TEST-ONLY. Force-regenerates the member's password and stores the
    plaintext in service_members.debug_password for local QA. Remove before
    going to production."""
    org, caller, org_role, svc_role = await _auth(slug, authorization, tenant_access, db)
    if not _can_manage_people(org_role, svc_role):
        raise HTTPException(status_code=403, detail="Solo administradores")
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
    sm, om = row
    if om.role == "admin":
        raise HTTPException(status_code=400, detail="No se puede resetear la contraseña del Administrador de la org")
    new_pw = _gen_temp_password()
    om.hashed_password = hash_password(new_pw)
    sm.debug_password = new_pw
    sm.welcomed_at = datetime.now(timezone.utc)
    await db.flush()
    return {"id": str(sm.id), "email": om.email, "debug_password": new_pw}


# ── Teams membership (convenience join) ───────────────────────────────────────
@router.get("/{sm_id}/teams")
async def list_person_teams(
    slug: str, sm_id: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Return the teams this person belongs to. Joins team_memberships → teams
    via `org_members.id` (= ServiceMember.member_id).
    """
    org, caller, org_role, svc_role = await _auth(slug, authorization, tenant_access, db)
    if not (org_role in ("admin", "leader") or svc_role is not None):
        raise HTTPException(status_code=403, detail="Sin acceso")
    try:
        smu = uuid.UUID(sm_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")
    sm = (await db.execute(
        select(ServiceMember).where(ServiceMember.id == smu, ServiceMember.org_id == org.id)
    )).scalar_one_or_none()
    if sm is None:
        raise HTTPException(status_code=404, detail="Persona no encontrada")
    rows = (await db.execute(
        select(TeamMembership, Team)
        .join(Team, Team.id == TeamMembership.team_id)
        .where(TeamMembership.member_id == sm.member_id, Team.org_id == org.id)
        .order_by(Team.name)
    )).all()
    return [
        {
            "membership_id": str(tm.id),
            "team_id": str(t.id), "team_name": t.name, "team_color": t.color,
            "role": tm.role,
        }
        for tm, t in rows
    ]
