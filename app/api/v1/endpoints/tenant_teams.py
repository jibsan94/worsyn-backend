"""Tenant module: Teams (volunteer groups) + memberships.

A Team groups org_members for service assignments (Alabanza, Audio/Visual,
Recibo, Desayunos, etc.). Used by services module via ServiceTeam M2M.

All endpoints scoped /tenant/{slug}/teams. Mutations require admin or leader.
"""
import uuid

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.models.models import Organization, OrgMember, Team, TeamMembership

router = APIRouter(prefix="/tenant/{slug}/teams", tags=["Tenant · Teams"])


async def _auth(slug: str, authorization: str | None, cookie: str | None, db: AsyncSession):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else cookie
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado")
    data = decode_token(token)
    if data.get("type") != "tenant_access" or data.get("org_slug") != slug:
        raise HTTPException(status_code=401, detail="Token inválido")
    org = (await db.execute(select(Organization).where(Organization.slug == slug))).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Org no encontrada")
    if data.get("impersonating"):
        return org, "admin"
    caller = (await db.execute(
        select(OrgMember).where(OrgMember.id == uuid.UUID(data["sub"]), OrgMember.org_id == org.id)
    )).scalar_one_or_none()
    if caller is None:
        raise HTTPException(status_code=401, detail="Miembro no encontrado")
    return org, caller.role


def _require_priv(role: str):
    if role not in ("admin", "leader"):
        raise HTTPException(status_code=403, detail="Solo administradores y líderes")


async def _team(team_id: str, org_id: uuid.UUID, db: AsyncSession) -> Team:
    try:
        tu = uuid.UUID(team_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")
    row = (await db.execute(
        select(Team).where(Team.id == tu, Team.org_id == org_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    return row


async def _members_count(team_id: uuid.UUID, db: AsyncSession) -> int:
    rows = (await db.execute(
        select(TeamMembership).where(TeamMembership.team_id == team_id)
    )).scalars().all()
    return len(rows)


@router.get("")
async def list_teams(
    slug: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, _ = await _auth(slug, authorization, tenant_access, db)
    rows = (await db.execute(
        select(Team).where(Team.org_id == org.id).order_by(Team.name)
    )).scalars().all()
    out = []
    for r in rows:
        out.append({
            "id": str(r.id), "name": r.name, "color": r.color, "description": r.description,
            "member_count": await _members_count(r.id, db),
        })
    return out


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_team(
    slug: str, body: dict,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, role = await _auth(slug, authorization, tenant_access, db)
    _require_priv(role)
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nombre requerido")
    t = Team(org_id=org.id, name=name, color=body.get("color"), description=body.get("description"))
    db.add(t)
    await db.flush()
    await db.refresh(t)
    return {"id": str(t.id), "name": t.name, "color": t.color, "description": t.description, "member_count": 0}


@router.patch("/{team_id}")
async def update_team(
    slug: str, team_id: str, body: dict,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, role = await _auth(slug, authorization, tenant_access, db)
    _require_priv(role)
    t = await _team(team_id, org.id, db)
    if "name" in body:
        n = (body["name"] or "").strip()
        if not n:
            raise HTTPException(status_code=400, detail="Nombre vacío")
        t.name = n
    if "color" in body: t.color = body["color"]
    if "description" in body: t.description = body["description"]
    await db.flush()
    return {"id": str(t.id), "name": t.name, "color": t.color, "description": t.description,
            "member_count": await _members_count(t.id, db)}


@router.delete("/{team_id}", status_code=204)
async def delete_team(
    slug: str, team_id: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, role = await _auth(slug, authorization, tenant_access, db)
    _require_priv(role)
    t = await _team(team_id, org.id, db)
    await db.delete(t)


# ── Memberships ───────────────────────────────────────────────────────────────
@router.get("/{team_id}/members")
async def list_team_members(
    slug: str, team_id: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, _ = await _auth(slug, authorization, tenant_access, db)
    t = await _team(team_id, org.id, db)
    rows = (await db.execute(
        select(TeamMembership, OrgMember)
        .join(OrgMember, OrgMember.id == TeamMembership.member_id)
        .where(TeamMembership.team_id == t.id)
    )).all()
    return [
        {
            "id": str(tm.id),
            "member_id": str(om.id),
            "full_name": om.full_name, "email": om.email,
            "role": tm.role,
        } for tm, om in rows
    ]


@router.post("/{team_id}/members", status_code=201)
async def add_team_member(
    slug: str, team_id: str, body: dict,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, role = await _auth(slug, authorization, tenant_access, db)
    _require_priv(role)
    t = await _team(team_id, org.id, db)
    try:
        mid = uuid.UUID(body.get("member_id") or "")
    except Exception:
        raise HTTPException(status_code=400, detail="member_id inválido")
    mem = (await db.execute(
        select(OrgMember).where(OrgMember.id == mid, OrgMember.org_id == org.id)
    )).scalar_one_or_none()
    if mem is None:
        raise HTTPException(status_code=404, detail="Miembro no encontrado")
    # Reject duplicates
    dup = (await db.execute(
        select(TeamMembership).where(TeamMembership.team_id == t.id, TeamMembership.member_id == mid)
    )).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(status_code=409, detail="Ya está en el equipo")
    tm = TeamMembership(team_id=t.id, member_id=mid, role=body.get("role"))
    db.add(tm)
    await db.flush()
    await db.refresh(tm)
    return {"id": str(tm.id), "member_id": str(mid), "role": tm.role}


@router.delete("/{team_id}/members/{member_id}", status_code=204)
async def remove_team_member(
    slug: str, team_id: str, member_id: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, role = await _auth(slug, authorization, tenant_access, db)
    _require_priv(role)
    t = await _team(team_id, org.id, db)
    try:
        mid = uuid.UUID(member_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")
    row = (await db.execute(
        select(TeamMembership).where(TeamMembership.team_id == t.id, TeamMembership.member_id == mid)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Pertenencia no encontrada")
    await db.delete(row)
