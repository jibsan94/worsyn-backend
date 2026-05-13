"""OrgRole CRUD — manages the configurable roles for org members.

System roles (is_system=True) can be edited but not deleted.
Custom roles can be freely created and deleted as long as they have no members.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import get_current_user, require_role
from app.db.session import get_db
from app.models.models import AdminUser, OrgMember, OrgRole
from app.schemas.schemas import OrgRoleCreate, OrgRoleRead, OrgRoleUpdate

router = APIRouter(prefix="/org-roles", tags=["Org Roles"])


async def _with_counts(db: AsyncSession, roles: list[OrgRole]) -> list[dict]:
    """Attach member_count to each role."""
    if not roles:
        return []
    counts_q = await db.execute(
        select(OrgMember.role, func.count(OrgMember.id).label("cnt"))
        .group_by(OrgMember.role)
    )
    counts = {row[0]: row[1] for row in counts_q}
    result = []
    for r in roles:
        d = OrgRoleRead.model_validate(r).model_dump()
        d["member_count"] = counts.get(r.slug, 0)
        result.append(d)
    return result


@router.get("/", response_model=list[OrgRoleRead])
async def list_org_roles(
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(get_current_user),
):
    """List all org roles ordered by sort_order, with member counts."""
    result = await db.execute(select(OrgRole).order_by(OrgRole.sort_order, OrgRole.name))
    roles = result.scalars().all()
    return await _with_counts(db, list(roles))


@router.get("/{role_id}", response_model=OrgRoleRead)
async def get_org_role(
    role_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(get_current_user),
):
    role = await db.get(OrgRole, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    rows = await _with_counts(db, [role])
    return rows[0]


@router.post("/", response_model=OrgRoleRead, status_code=status.HTTP_201_CREATED)
async def create_org_role(
    payload: OrgRoleCreate,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(require_role("admin", "owner")),
):
    """Create a new custom org role."""
    dup = await db.execute(select(OrgRole).where(OrgRole.slug == payload.slug))
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A role with that slug already exists")

    role = OrgRole(
        slug=payload.slug,
        name=payload.name,
        description=payload.description,
        sort_order=payload.sort_order,
        is_system=False,
    )
    db.add(role)
    await db.flush()
    await db.refresh(role)
    rows = await _with_counts(db, [role])
    return rows[0]


@router.patch("/{role_id}", response_model=OrgRoleRead)
async def update_org_role(
    role_id: uuid.UUID,
    payload: OrgRoleUpdate,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(require_role("admin", "owner")),
):
    """Update a role's display metadata. Works for both system and custom roles."""
    role = await db.get(OrgRole, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    if payload.name is not None:
        role.name = payload.name
    if payload.description is not None:
        role.description = payload.description
    if payload.sort_order is not None:
        role.sort_order = payload.sort_order

    await db.flush()
    await db.refresh(role)
    rows = await _with_counts(db, [role])
    return rows[0]


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_org_role(
    role_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(require_role("owner")),
):
    """Delete a custom org role. System roles and roles with active members cannot be deleted."""
    role = await db.get(OrgRole, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System roles cannot be deleted")

    count_q = await db.execute(
        select(func.count(OrgMember.id)).where(OrgMember.role == role.slug)
    )
    if count_q.scalar_one() > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete role: it is assigned to one or more members",
        )
    await db.delete(role)
