"""Organization CRUD + tenant management endpoints."""
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import get_current_user, require_role
from app.db.session import get_db
from app.models.models import AdminUser, Organization, OrgMember, Tenant
from app.schemas.schemas import (
    OrganizationCreate, OrganizationRead, OrganizationUpdate, TenantRead,
)
from app.services.tenant_provisioner import (
    allocate_port, check_container_status, destroy_tenant,
    generate_db_password, provision_tenant, start_tenant, stop_tenant,
)

router = APIRouter(prefix="/organizations", tags=["Organizations"])


async def _with_member_count(db: AsyncSession, orgs: list[Organization]) -> list[dict]:
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


async def _get_org_or_404(db: AsyncSession, org_id: uuid.UUID) -> Organization:
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


async def _get_tenant_or_404(db: AsyncSession, org_id: uuid.UUID) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.org_id == org_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not provisioned")
    return tenant


@router.get("/", response_model=list[OrganizationRead])
async def list_organizations(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(get_current_user),
):
    result = await db.execute(
        select(Organization).order_by(Organization.created_at.desc()).offset(skip).limit(limit)
    )
    return await _with_member_count(db, list(result.scalars().all()))


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
    org = await _get_org_or_404(db, org_id)
    orgs = await _with_member_count(db, [org])
    return orgs[0]


@router.post("/", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreate,
    background_tasks: BackgroundTasks,
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

    existing_ports_q = await db.execute(select(Tenant.db_port))
    used_ports = [row[0] for row in existing_ports_q if row[0] is not None]
    port = allocate_port(used_ports)
    password = generate_db_password()

    tenant = Tenant(
        org_id=org.id,
        status="provisioning",
        db_port=port,
        db_password=password,
        container_name=f"worsyn-tenant-{org.slug}-db",
        compose_dir=f"/mnt/tenants/{org.slug}",
    )
    db.add(tenant)
    await db.flush()

    background_tasks.add_task(provision_tenant, str(org.id), org.slug, port, password)

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
    org = await _get_org_or_404(db, org_id)
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
    org = await _get_org_or_404(db, org_id)
    tenant_q = await db.execute(select(Tenant).where(Tenant.org_id == org_id))
    tenant = tenant_q.scalar_one_or_none()
    if tenant and tenant.status in ("running", "stopped"):
        destroy_tenant(org.slug)
    await db.delete(org)


@router.get("/{org_id}/tenant", response_model=TenantRead)
async def get_tenant(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_role("admin", "owner")),
):
    return await _get_tenant_or_404(db, org_id)


@router.post("/{org_id}/tenant/start", response_model=TenantRead)
async def start_org_tenant(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_role("admin", "owner")),
):
    tenant = await _get_tenant_or_404(db, org_id)
    org = await _get_org_or_404(db, org_id)
    ok, err = start_tenant(org.slug)
    tenant.status = "running" if ok else "error"
    if err:
        tenant.error_msg = err
    await db.flush()
    return tenant


@router.post("/{org_id}/tenant/stop", response_model=TenantRead)
async def stop_org_tenant(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_role("admin", "owner")),
):
    tenant = await _get_tenant_or_404(db, org_id)
    org = await _get_org_or_404(db, org_id)
    ok, err = stop_tenant(org.slug)
    tenant.status = "stopped" if ok else "error"
    if err:
        tenant.error_msg = err
    await db.flush()
    return tenant


@router.post("/{org_id}/tenant/refresh", response_model=TenantRead)
async def refresh_tenant_status(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_role("admin", "owner")),
):
    """Sync tenant status with actual Docker container state."""
    tenant = await _get_tenant_or_404(db, org_id)
    if tenant.container_name:
        docker_status = check_container_status(tenant.container_name)
        if docker_status is None:
            if tenant.status not in ("provisioning", "error"):
                tenant.status = "stopped"
        elif docker_status == "running":
            tenant.status = "running"
        else:
            tenant.status = "stopped"
    await db.flush()
    return tenant


@router.delete("/{org_id}/tenant", status_code=status.HTTP_204_NO_CONTENT)
async def destroy_org_tenant(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_role("admin", "owner")),
):
    """Destroy the tenant container without deleting the organization."""
    tenant = await _get_tenant_or_404(db, org_id)
    org = await _get_org_or_404(db, org_id)
    ok, err = destroy_tenant(org.slug)
    if not ok:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=err)
    tenant.status = "stopped"
    tenant.provisioned_at = None
    await db.flush()


@router.post("/{org_id}/tenant/provision", response_model=TenantRead)
async def provision_org_tenant(
    org_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_role("admin", "owner")),
):
    """Re-provision the tenant container (creates a new PostgreSQL container)."""
    tenant = await _get_tenant_or_404(db, org_id)
    org = await _get_org_or_404(db, org_id)

    existing_ports_q = await db.execute(select(Tenant.db_port).where(Tenant.org_id != org_id))
    used_ports = [row[0] for row in existing_ports_q if row[0] is not None]
    port = tenant.db_port if tenant.db_port and tenant.db_port not in used_ports else allocate_port(used_ports)

    from app.services.tenant_provisioner import generate_db_password as _gen
    password = tenant.db_password or _gen()

    tenant.status = "provisioning"
    tenant.db_port = port
    tenant.db_password = password
    tenant.container_name = f"worsyn-tenant-{org.slug}-db"
    tenant.compose_dir = f"/mnt/tenants/{org.slug}"
    tenant.error_msg = None
    await db.flush()

    background_tasks.add_task(provision_tenant, str(org.id), org.slug, port, password)
    return tenant


@router.get("/slug/{slug}")
async def get_org_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint — returns basic org info by slug (no auth required)."""
    from sqlalchemy import select as _sel
    result = await db.execute(_sel(Organization).where(Organization.slug == slug))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return {"id": str(org.id), "name": org.name, "slug": org.slug, "alias": org.alias, "plan": org.plan}
