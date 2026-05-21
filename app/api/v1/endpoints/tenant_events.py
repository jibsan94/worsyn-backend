"""Tenant module: Events (camps, retreats, conferences)."""
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.models.models import Event, Organization

router = APIRouter(prefix="/tenant/{slug}/events", tags=["Tenant · Events"])


async def _auth_org(slug, authorization, cookie, db) -> Organization:
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else cookie
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado")
    data = decode_token(token)
    if data.get("type") != "tenant_access" or data.get("org_slug") != slug:
        raise HTTPException(status_code=401, detail="Token inválido")
    result = await db.execute(select(Organization).where(Organization.slug == slug))
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Org no encontrada")
    return org


@router.get("")
async def list_events(
    slug: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org = await _auth_org(slug, authorization, tenant_access, db)
    rows = (await db.execute(
        select(Event).where(Event.org_id == org.id).order_by(Event.starts_at.desc().nullslast())
    )).scalars().all()
    return [
        {
            "id": str(r.id), "name": r.name, "location": r.location,
            "starts_at": r.starts_at.isoformat() if r.starts_at else None,
            "ends_at": r.ends_at.isoformat() if r.ends_at else None,
            "description": r.description,
        }
        for r in rows
    ]
