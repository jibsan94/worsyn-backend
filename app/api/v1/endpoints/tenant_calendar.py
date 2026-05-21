"""Tenant module: Calendar (aggregates events + rehearsals + service plans).

This module is read-only — it doesn't own its own table. It composes data
from events, rehearsals, and service_plans into a unified feed.
"""
from datetime import datetime

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.models.models import Event, Organization, Rehearsal, ServicePlan

router = APIRouter(prefix="/tenant/{slug}/calendar", tags=["Tenant · Calendar"])


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
async def calendar_feed(
    slug: str,
    from_date: datetime | None = Query(default=None, alias="from"),
    to_date: datetime | None = Query(default=None, alias="to"),
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Unified calendar feed — events + rehearsals + service plans within a range."""
    org = await _auth_org(slug, authorization, tenant_access, db)
    items: list[dict] = []

    events = (await db.execute(select(Event).where(Event.org_id == org.id))).scalars().all()
    for e in events:
        items.append({
            "kind": "event", "id": str(e.id), "title": e.name,
            "starts_at": e.starts_at.isoformat() if e.starts_at else None,
            "ends_at": e.ends_at.isoformat() if e.ends_at else None,
            "location": e.location,
        })

    rehs = (await db.execute(select(Rehearsal).where(Rehearsal.org_id == org.id))).scalars().all()
    for r in rehs:
        items.append({
            "kind": "rehearsal", "id": str(r.id), "title": "Ensayo",
            "starts_at": r.scheduled_at.isoformat() if r.scheduled_at else None,
            "location": r.location,
        })

    plans = (await db.execute(select(ServicePlan).where(ServicePlan.org_id == org.id))).scalars().all()
    for p in plans:
        items.append({
            "kind": "service", "id": str(p.id), "title": p.title,
            "starts_at": p.scheduled_at.isoformat() if p.scheduled_at else None,
            "status": p.status,
        })

    items.sort(key=lambda x: x["starts_at"] or "")
    return items
