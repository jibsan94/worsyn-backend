"""Tenant module: Services (service types + service plans).

Independent module — owns service_types and service_plans tables.
All endpoints scoped by slug → org_id. Tenant JWT required.
"""
import uuid

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.models.models import Organization, ServicePlan, ServiceType

router = APIRouter(prefix="/tenant/{slug}/services", tags=["Tenant · Services"])


async def _auth_org(slug: str, authorization: str | None, cookie: str | None, db: AsyncSession) -> Organization:
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else cookie
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    data = decode_token(token)
    if data.get("type") != "tenant_access" or data.get("org_slug") != slug:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    result = await db.execute(select(Organization).where(Organization.slug == slug))
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Org no encontrada")
    return org


@router.get("/types")
async def list_service_types(
    slug: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org = await _auth_org(slug, authorization, tenant_access, db)
    rows = (await db.execute(
        select(ServiceType).where(ServiceType.org_id == org.id).order_by(ServiceType.sort_order, ServiceType.name)
    )).scalars().all()
    return [
        {"id": str(r.id), "name": r.name, "color": r.color, "sort_order": r.sort_order}
        for r in rows
    ]


@router.post("/types", status_code=status.HTTP_201_CREATED)
async def create_service_type(
    slug: str,
    body: dict,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org = await _auth_org(slug, authorization, tenant_access, db)
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nombre requerido")
    st = ServiceType(org_id=org.id, name=name, color=body.get("color"), sort_order=int(body.get("sort_order") or 0))
    db.add(st)
    await db.flush()
    await db.refresh(st)
    return {"id": str(st.id), "name": st.name, "color": st.color, "sort_order": st.sort_order}


@router.get("/plans")
async def list_service_plans(
    slug: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org = await _auth_org(slug, authorization, tenant_access, db)
    rows = (await db.execute(
        select(ServicePlan).where(ServicePlan.org_id == org.id).order_by(ServicePlan.scheduled_at.desc().nullslast())
    )).scalars().all()
    return [
        {
            "id": str(r.id), "title": r.title, "status": r.status,
            "scheduled_at": r.scheduled_at.isoformat() if r.scheduled_at else None,
            "service_type_id": str(r.service_type_id) if r.service_type_id else None,
        }
        for r in rows
    ]
