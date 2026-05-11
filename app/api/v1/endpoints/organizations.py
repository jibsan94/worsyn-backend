"""Organization CRUD endpoints."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import get_current_user, require_role
from app.db.session import get_db
from app.models.models import AdminUser, Organization, OrgMember
from app.schemas.schemas import OrganizationCreate, OrganizationRead, OrganizationUpdate

router = APIRouter(prefix="/organizations", tags=["Organizations"])


async def _with_member_count(db: AsyncSession, orgs: list[Organization]) -> list[dict]:
    """Attach member_count to each org dict."""
    if not orgs:
        return []
    org_ids = [o.id for o in orgs]
    counts_q = await db.execute(
        select(OrgMember.org_id, func.count(OrgMember.id).label("cnt"))
        .where(OrgMember.org_id.in_(org_ids))
        .group_by(OrgMember.org_id)
    )
    count_map = {row.org_id: row.cnt for row in counts_q}
    result = []
    for org in orgs:
        d = OrganizationRead.model_validate(org).model_dump()
        d["member_count"] = count_map.get(org.id, 0)
        result.append(d)
    return result


@router.get("/", response_model=list[OrganizationRead])
async def list_organizations(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(get_current_user),
):
    result = await db.execute(select(Organization).order_by(Organization.created_at.desc()).offset(skip).limit(limit))
    orgs = result.scalars().all()
    return await _with_member_count(db, list(orgs))


@router.get("/count")
async def count_organizations(
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(get_current_user),
):
    result = await db.execute(select(func.count()).select_from(Organization))
    return {"count": result.scalar_one()}


@router.get("/{org_id}", response_model=OrganizationRead)
async def get_organization(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(get_current_user),
):
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    orgs = await _with_member_count(db, [org])
    return orgs[0]


@router.post("/", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_role("admin", "owner")),
):
    existing = await db.execute(select(Organization).where(Organization.slug == payload.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already in use")
    org = Organization(**payload.model_dump())
    db.add(org)
    await db.flush()
    await db.refresh(org)
    d = OrganizationRead.model_validate(org).model_dump()
    d["member_count"] = 0
    return d


@router.patch("/{org_id}", response_model=OrganizationRead)
async def update_organization(
    org_id: uuid.UUID,
    payload: OrganizationUpdate,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_role("admin", "owner")),
):
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(org, field, value)
    await db.flush()
    await db.refresh(org)
    orgs = await _with_member_count(db, [org])
    return orgs[0]


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_role("owner")),
):
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    await db.delete(org)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(org, field, value)
    await db.flush()
    await db.refresh(org)
    return org


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    await db.delete(org)
