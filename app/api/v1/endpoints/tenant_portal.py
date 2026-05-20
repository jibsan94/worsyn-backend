"""Tenant portal endpoints.

Org-member auth uses its own JWT type (tenant_access) — separate from AdminUser tokens.
CRUD endpoints are currently public (slug-scoped); tenant auth guard to be added later.
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decode_token, verify_password
from app.db.session import get_db
from app.models.models import OrgMember, Organization
from app.schemas.schemas import OrgMemberCreate, OrgMemberRead, OrgMemberUpdate, OrgSettingsUpdate, OrganizationRead

settings = get_settings()
router = APIRouter(prefix="/tenant", tags=["Tenant Portal"])


def _create_tenant_token(member_id: str, org_id: str, org_slug: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    payload = {
        "sub": member_id,
        "org_id": org_id,
        "org_slug": org_slug,
        "exp": expire,
        "type": "tenant_access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)

router = APIRouter(prefix="/tenant", tags=["Tenant Portal"])


async def _get_org_by_slug(db: AsyncSession, slug: str) -> Organization:
    result = await db.execute(select(Organization).where(Organization.slug == slug))
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


from app.api.v1.endpoints.organizations import DEFAULT_MINISTRIES, DEFAULT_MEMBER_ROLES


@router.get("/{slug}/settings/defaults")
async def get_org_defaults(slug: str):
    """Returns the platform default ministries and roles (for reset-to-defaults UI)."""
    return {"ministries": DEFAULT_MINISTRIES, "member_roles": DEFAULT_MEMBER_ROLES}


async def _get_tenant_admin(
    authorization: str | None, slug: str, db: AsyncSession
) -> OrgMember:
    """Validate tenant JWT and require admin role."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    data = decode_token(authorization[7:])
    if data.get("type") != "tenant_access" or data.get("org_slug") != slug:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    org = await _get_org_by_slug(db, slug)
    result = await db.execute(
        select(OrgMember).where(OrgMember.id == data["sub"], OrgMember.org_id == org.id)
    )
    member = result.scalar_one_or_none()
    if not member or not member.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida")
    if member.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere rol de admin")
    return member


async def _get_member_or_404(db: AsyncSession, org_id: uuid.UUID, member_id: uuid.UUID) -> OrgMember:
    result = await db.execute(
        select(OrgMember).where(OrgMember.id == member_id, OrgMember.org_id == org_id)
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    return member


@router.get("/{slug}/members", response_model=list[OrgMemberRead])
async def list_members(slug: str, db: AsyncSession = Depends(get_db)):
    org = await _get_org_by_slug(db, slug)
    result = await db.execute(
        select(OrgMember)
        .where(OrgMember.org_id == org.id)
        .order_by(OrgMember.joined_at)
    )
    return result.scalars().all()


@router.post("/{slug}/members", response_model=OrgMemberRead, status_code=status.HTTP_201_CREATED)
async def create_member(slug: str, payload: OrgMemberCreate, db: AsyncSession = Depends(get_db)):
    org = await _get_org_by_slug(db, slug)

    dup = await db.execute(
        select(OrgMember).where(OrgMember.org_id == org.id, OrgMember.email == payload.email)
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe un miembro con ese correo")

    member = OrgMember(
        org_id=org.id,
        email=payload.email,
        full_name=payload.full_name,
        phone=payload.phone,
        role=payload.role,
        hashed_password=None,          # password set separately when portal auth is wired
        prefix=payload.prefix,
        gender=payload.gender,
        birthdate=payload.birthdate,
        anniversary=payload.anniversary,
        ministry=payload.ministry,
        org_roles=payload.org_roles,
    )
    db.add(member)
    await db.flush()
    await db.refresh(member)
    return member


@router.put("/{slug}/members/{member_id}", response_model=OrgMemberRead)
async def update_member(
    slug: str,
    member_id: uuid.UUID,
    payload: OrgMemberUpdate,
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org_by_slug(db, slug)
    member = await _get_member_or_404(db, org.id, member_id)

    if payload.email is not None:
        new_email = payload.email.lower()
        if new_email != member.email:
            dup = await db.execute(
                select(OrgMember).where(OrgMember.org_id == org.id, OrgMember.email == new_email)
            )
            if dup.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email ya está en uso en esta org")
            member.email = new_email

    if payload.full_name is not None:
        member.full_name = payload.full_name
    if payload.phone is not None:
        member.phone = payload.phone
    if payload.role is not None:
        member.role = payload.role
    if payload.is_active is not None:
        member.is_active = payload.is_active
    if payload.prefix is not None:
        member.prefix = payload.prefix
    if payload.gender is not None:
        member.gender = payload.gender
    if payload.birthdate is not None:
        member.birthdate = payload.birthdate
    if payload.anniversary is not None:
        member.anniversary = payload.anniversary
    if payload.ministry is not None:
        member.ministry = payload.ministry
    if payload.org_roles is not None:
        member.org_roles = payload.org_roles

    await db.flush()
    await db.refresh(member)
    return member


@router.delete("/{slug}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_member(slug: str, member_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    org = await _get_org_by_slug(db, slug)
    member = await _get_member_or_404(db, org.id, member_id)
    await db.delete(member)


# ── Org settings ─────────────────────────────────────────────────────────────

@router.get("/{slug}/settings", response_model=OrganizationRead)
async def get_org_settings(slug: str, db: AsyncSession = Depends(get_db)):
    """Returns org data including settings fields. Public (slug-scoped)."""
    org = await _get_org_by_slug(db, slug)
    result = await db.execute(select(OrgMember).where(OrgMember.org_id == org.id))
    count = len(result.scalars().all())
    read = OrganizationRead.model_validate(org)
    read.member_count = count
    return read


@router.patch("/{slug}/settings", response_model=OrganizationRead)
async def update_org_settings(
    slug: str,
    payload: OrgSettingsUpdate,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Update org settings. Requires admin tenant token."""
    await _get_tenant_admin(authorization, slug, db)
    org = await _get_org_by_slug(db, slug)

    if payload.name is not None:
        org.name = payload.name.strip()
    if payload.alias is not None:
        new_alias = payload.alias.strip() or None
        if new_alias and new_alias != org.alias:
            dup = await db.execute(
                select(Organization).where(Organization.alias == new_alias, Organization.id != org.id)
            )
            if dup.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese alias ya está en uso")
        org.alias = new_alias
    if payload.ministries is not None:
        org.ministries = payload.ministries
    if payload.member_roles is not None:
        org.member_roles = payload.member_roles
    if payload.icon is not None:
        org.icon = payload.icon if payload.icon else None
    if payload.require_2fa_admins is not None:
        org.require_2fa_admins = payload.require_2fa_admins

    await db.flush()
    await db.refresh(org)

    result = await db.execute(select(OrgMember).where(OrgMember.org_id == org.id))
    count = len(result.scalars().all())
    read = OrganizationRead.model_validate(org)
    read.member_count = count
    return read


# ── Tenant portal auth ────────────────────────────────────────────────────────

@router.post("/{slug}/auth/login")
async def tenant_login(slug: str, body: dict, db: AsyncSession = Depends(get_db)):
    """Login as an org member. Returns tenant JWT (7-day access token).

    Members without a password set (hashed_password is null) are accepted with
    any password until portal auth is fully wired up.
    """
    org = await _get_org_by_slug(db, slug)
    email = (body.get("email") or "").lower().strip()
    password = body.get("password") or ""

    result = await db.execute(
        select(OrgMember).where(OrgMember.org_id == org.id, OrgMember.email == email)
    )
    member = result.scalar_one_or_none()

    if not member:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")
    if not member.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cuenta inactiva")
    if member.hashed_password is not None:
        if not verify_password(password, member.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")

    token = _create_tenant_token(str(member.id), str(org.id), slug)
    return {
        "access_token": token,
        "token_type": "bearer",
        "member": {
            "id": str(member.id),
            "email": member.email,
            "full_name": member.full_name,
            "role": member.role,
            "org_id": str(org.id),
            "org_name": org.name,
            "org_slug": slug,
        },
    }


@router.get("/{slug}/auth/me")
async def tenant_me(
    slug: str,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Validate an existing tenant token. Returns member info."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    token = authorization[7:]
    data = decode_token(token)
    if data.get("type") != "tenant_access" or data.get("org_slug") != slug:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

    org = await _get_org_by_slug(db, slug)
    result = await db.execute(
        select(OrgMember).where(OrgMember.id == data["sub"], OrgMember.org_id == org.id)
    )
    member = result.scalar_one_or_none()
    if not member or not member.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida")

    return {
        "id": str(member.id),
        "email": member.email,
        "full_name": member.full_name,
        "role": member.role,
        "org_id": str(org.id),
        "org_name": org.name,
        "org_slug": slug,
    }
