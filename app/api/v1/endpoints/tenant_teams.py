"""Tenant module: Teams (volunteer groups) + memberships."""
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.models.models import Organization, Team, TeamMembership

router = APIRouter(prefix="/tenant/{slug}/teams", tags=["Tenant · Teams"])


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
async def list_teams(
    slug: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org = await _auth_org(slug, authorization, tenant_access, db)
    rows = (await db.execute(
        select(Team).where(Team.org_id == org.id).order_by(Team.name)
    )).scalars().all()
    return [
        {"id": str(r.id), "name": r.name, "color": r.color, "description": r.description}
        for r in rows
    ]


@router.get("/{team_id}/members")
async def list_team_members(
    slug: str,
    team_id: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    await _auth_org(slug, authorization, tenant_access, db)
    rows = (await db.execute(
        select(TeamMembership).where(TeamMembership.team_id == team_id)
    )).scalars().all()
    return [
        {"id": str(r.id), "member_id": str(r.member_id), "role": r.role}
        for r in rows
    ]
