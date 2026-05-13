"""Global OrgMember endpoints — lists members across all organizations.

Used by the admin dashboard Users page (/users).
Write operations (update/delete) still go through the nested
/organizations/{org_id}/members/{id} endpoints.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import get_current_user, require_role
from app.core.security import hash_password
from app.db.session import get_db
from app.models.models import AdminUser, OrgMember, Organization
from app.schemas.schemas import OrgMemberUpdate, OrgMemberWithOrg

router = APIRouter(prefix="/members", tags=["Members"])


def _row_to_dict(member: OrgMember, org_name: str | None, org_slug: str | None) -> dict:
    return {
        "id": member.id,
        "org_id": member.org_id,
        "email": member.email,
        "full_name": member.full_name,
        "phone": member.phone,
        "role": member.role,
        "is_active": member.is_active,
        "joined_at": member.joined_at,
        "updated_at": member.updated_at,
        "org_name": org_name,
        "org_slug": org_slug,
    }


@router.get("/", response_model=list[OrgMemberWithOrg])
async def list_all_members(
    org_id: Optional[uuid.UUID] = Query(None, description="Filter by organization"),
    role: Optional[str] = Query(None, description="Filter by role (admin | leader)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search by name or email"),
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(get_current_user),
):
    """List all org members across every organization, with optional filters."""
    q = (
        select(OrgMember, Organization.name.label("org_name"), Organization.slug.label("org_slug"))
        .join(Organization, Organization.id == OrgMember.org_id)
    )
    if org_id:
        q = q.where(OrgMember.org_id == org_id)
    if role:
        q = q.where(OrgMember.role == role)
    if is_active is not None:
        q = q.where(OrgMember.is_active == is_active)
    if search:
        pattern = f"%{search}%"
        q = q.where(
            or_(OrgMember.email.ilike(pattern), OrgMember.full_name.ilike(pattern))
        )
    q = q.order_by(OrgMember.joined_at.desc()).offset(skip).limit(limit)
    rows = (await db.execute(q)).all()
    return [_row_to_dict(r[0], r[1], r[2]) for r in rows]


@router.get("/{member_id}", response_model=OrgMemberWithOrg)
async def get_member(
    member_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(get_current_user),
):
    """Get a single org member by ID (any org)."""
    q = (
        select(OrgMember, Organization.name.label("org_name"), Organization.slug.label("org_slug"))
        .join(Organization, Organization.id == OrgMember.org_id)
        .where(OrgMember.id == member_id)
    )
    row = (await db.execute(q)).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    return _row_to_dict(row[0], row[1], row[2])


@router.patch("/{member_id}", response_model=OrgMemberWithOrg)
async def update_member(
    member_id: uuid.UUID,
    payload: OrgMemberUpdate,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(require_role("admin", "owner")),
):
    """Update an org member (partial). Used by the global Users page."""
    member = await db.get(OrgMember, member_id)
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    if payload.email is not None:
        new_email = payload.email.lower()
        if new_email != member.email:
            dup = await db.execute(
                select(OrgMember).where(
                    OrgMember.org_id == member.org_id, OrgMember.email == new_email
                )
            )
            if dup.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already in use in this organization",
                )
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

    await db.flush()
    await db.refresh(member)

    org = await db.get(Organization, member.org_id)
    return _row_to_dict(member, org.name if org else None, org.slug if org else None)


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_member(
    member_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(require_role("admin", "owner")),
):
    """Delete an org member."""
    member = await db.get(OrgMember, member_id)
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    await db.delete(member)
