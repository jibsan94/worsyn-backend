"""OrgMember CRUD — tenant organization members.

These are users that belong to a church/customer organization.
They are completely separate from AdminUser (Worsyn platform users).

Nested under /organizations/{org_id}/members.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import get_current_user, require_role
from app.core.security import hash_password
from app.db.session import get_db
from app.models.models import AdminUser, OrgMember, Organization
from app.schemas.schemas import OrgMemberCreate, OrgMemberRead, OrgMemberUpdate

router = APIRouter(
    prefix="/organizations/{org_id}/members",
    tags=["Org Members"],
)


async def _get_org_or_404(db: AsyncSession, org_id: uuid.UUID) -> Organization:
    result = await db.get(Organization, org_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return result


async def _get_member_or_404(db: AsyncSession, org_id: uuid.UUID, member_id: uuid.UUID) -> OrgMember:
    result = await db.execute(
        select(OrgMember).where(OrgMember.id == member_id, OrgMember.org_id == org_id)
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    return member


@router.get("", response_model=list[OrgMemberRead])
async def list_members(
    org_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(get_current_user),
):
    """List all members of an organization."""
    await _get_org_or_404(db, org_id)
    result = await db.execute(
        select(OrgMember)
        .where(OrgMember.org_id == org_id)
        .order_by(OrgMember.joined_at)
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


@router.post("", response_model=OrgMemberRead, status_code=status.HTTP_201_CREATED)
async def create_member(
    org_id: uuid.UUID,
    payload: OrgMemberCreate,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(require_role("admin", "owner")),
):
    """Add a new member to an organization."""
    await _get_org_or_404(db, org_id)

    # email must be unique within the org
    dup = await db.execute(
        select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.email == payload.email.lower())
    )
    if dup.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A member with that email already exists in this organization",
        )

    member = OrgMember(
        org_id=org_id,
        email=payload.email.lower(),
        full_name=payload.full_name,
        phone=payload.phone,
        role=payload.role,
        hashed_password=hash_password(payload.password) if payload.password else None,
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


@router.get("/{member_id}", response_model=OrgMemberRead)
async def get_member(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(get_current_user),
):
    return await _get_member_or_404(db, org_id, member_id)


@router.put("/{member_id}", response_model=OrgMemberRead)
async def update_member(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    payload: OrgMemberUpdate,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(require_role("admin", "owner")),
):
    """Update an org member (partial)."""
    member = await _get_member_or_404(db, org_id, member_id)

    if payload.email is not None:
        new_email = payload.email.lower()
        if new_email != member.email:
            dup = await db.execute(
                select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.email == new_email)
            )
            if dup.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use in this org")
            member.email = new_email

    if payload.full_name is not None:
        member.full_name = payload.full_name
    if payload.phone is not None:
        member.phone = payload.phone
    if payload.role is not None:
        member.role = payload.role
    if payload.is_active is not None:
        member.is_active = payload.is_active
    if payload.password is not None:
        member.hashed_password = hash_password(payload.password)
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


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_member(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(require_role("admin", "owner")),
):
    """Remove a member from an organization."""
    member = await _get_member_or_404(db, org_id, member_id)
    await db.delete(member)
