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
from app.models.models import (
    Organization, OrgMember, ServiceMember, ServiceTeam, ServiceType,
    Team, TeamLeader, TeamMembership, TeamPosition, TeamPositionMember,
    TeamRelated,
)

router = APIRouter(prefix="/tenant/{slug}/teams", tags=["Tenant · Teams"])


async def _auth(slug: str, authorization: str | None, cookie: str | None, db: AsyncSession):
    """Returns (org, caller_or_None, role). caller is None for impersonation."""
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
        return org, None, "admin"
    caller = (await db.execute(
        select(OrgMember).where(OrgMember.id == uuid.UUID(data["sub"]), OrgMember.org_id == org.id)
    )).scalar_one_or_none()
    if caller is None:
        raise HTTPException(status_code=401, detail="Miembro no encontrado")
    return org, caller, caller.role


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


# Default teams every org starts with. Seeded the first time `list_teams` is
# called for an org with zero rows. Once any team exists, this helper is a
# no-op — so if an admin deletes a default team it stays deleted.
DEFAULT_TEAMS: list[tuple[str, str]] = [
    ("Grupo de Alabanza", "#4F46E5"),
    ("Audio/Visual",      "#EF4444"),
    ("Predicadores",      "#10B981"),
    ("Recibo y Orden",    "#F59E0B"),
]


async def _autoseed_defaults(org_id: uuid.UUID, db: AsyncSession) -> None:
    existing = (await db.execute(
        select(Team).where(Team.org_id == org_id).limit(1)
    )).scalar_one_or_none()
    if existing is not None:
        return
    for name, color in DEFAULT_TEAMS:
        db.add(Team(org_id=org_id, name=name, color=color))
    await db.flush()


async def _serialize_team(t: Team, db: AsyncSession) -> dict:
    leaders = (await db.execute(
        select(TeamLeader, OrgMember)
        .join(OrgMember, OrgMember.id == TeamLeader.member_id)
        .where(TeamLeader.team_id == t.id)
        .order_by(OrgMember.full_name)
    )).all()
    stypes = (await db.execute(
        select(ServiceTeam).where(ServiceTeam.team_id == t.id)
    )).scalars().all()
    related = (await db.execute(
        select(TeamRelated.related_team_id).where(TeamRelated.team_id == t.id)
    )).scalars().all()
    return {
        "id": str(t.id), "name": t.name, "color": t.color, "description": t.description,
        "is_rehearsal": t.is_rehearsal, "is_secure": t.is_secure, "is_split": t.is_split,
        "default_status": t.default_status,
        "notify_on_prepare": t.notify_on_prepare,
        "replies_to": t.replies_to,
        "gap_alerts_enabled": t.gap_alerts_enabled,
        "last_scheduled_date_rule": t.last_scheduled_date_rule,
        "scheduled_viewer_access": t.scheduled_viewer_access,
        "signup_sheets_auto_enable": t.signup_sheets_auto_enable,
        "reschedule_on_decline": t.reschedule_on_decline,
        "member_count": await _members_count(t.id, db),
        "leaders": [
            {"member_id": str(om.id), "full_name": om.full_name, "email": om.email}
            for _tl, om in leaders
        ],
        "leader_member_ids": [str(om.id) for _tl, om in leaders],
        "service_type_ids": [str(st.service_type_id) for st in stypes],
        "related_team_ids": [str(r) for r in related],
    }


async def _replace_leaders(team_id: uuid.UUID, org_id: uuid.UUID, ids_raw: list, db: AsyncSession) -> None:
    # Wipe + reinsert. Silently drop unknown / wrong-org member ids.
    existing = (await db.execute(select(TeamLeader).where(TeamLeader.team_id == team_id))).scalars().all()
    for x in existing:
        await db.delete(x)
    seen: set[uuid.UUID] = set()
    for raw in ids_raw or []:
        try:
            mid = uuid.UUID(raw)
        except Exception:
            continue
        if mid in seen:
            continue
        ok = (await db.execute(
            select(OrgMember.id).where(OrgMember.id == mid, OrgMember.org_id == org_id)
        )).scalar_one_or_none()
        if ok is None:
            continue
        db.add(TeamLeader(team_id=team_id, member_id=mid))
        seen.add(mid)
    await db.flush()


async def _replace_related_teams(team_id: uuid.UUID, org_id: uuid.UUID, ids_raw: list, db: AsyncSession) -> None:
    """Replace-all related teams. Drops self-id + cross-org + unknowns silently."""
    existing = (await db.execute(
        select(TeamRelated).where(TeamRelated.team_id == team_id)
    )).scalars().all()
    for x in existing:
        await db.delete(x)
    seen: set[uuid.UUID] = set()
    for raw in ids_raw or []:
        try:
            rid = uuid.UUID(raw)
        except Exception:
            continue
        if rid in seen or rid == team_id:
            continue
        ok = (await db.execute(
            select(Team.id).where(Team.id == rid, Team.org_id == org_id)
        )).scalar_one_or_none()
        if ok is None:
            continue
        db.add(TeamRelated(team_id=team_id, related_team_id=rid))
        seen.add(rid)
    await db.flush()


async def _replace_service_types(team_id: uuid.UUID, org_id: uuid.UUID, ids_raw: list, db: AsyncSession) -> None:
    existing = (await db.execute(select(ServiceTeam).where(ServiceTeam.team_id == team_id))).scalars().all()
    for x in existing:
        await db.delete(x)
    seen: set[uuid.UUID] = set()
    for raw in ids_raw or []:
        try:
            stid = uuid.UUID(raw)
        except Exception:
            continue
        if stid in seen:
            continue
        ok = (await db.execute(
            select(ServiceType.id).where(ServiceType.id == stid, ServiceType.org_id == org_id)
        )).scalar_one_or_none()
        if ok is None:
            continue
        db.add(ServiceTeam(team_id=team_id, service_type_id=stid))
        seen.add(stid)
    await db.flush()


@router.get("")
async def list_teams(
    slug: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = await _auth(slug, authorization, tenant_access, db)
    await _autoseed_defaults(org.id, db)
    rows = (await db.execute(
        select(Team).where(Team.org_id == org.id).order_by(Team.name)
    )).scalars().all()
    return [await _serialize_team(r, db) for r in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_team(
    slug: str, body: dict,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, caller, role = await _auth(slug, authorization, tenant_access, db)
    _require_priv(role)
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nombre requerido")
    t = Team(
        org_id=org.id, name=name,
        color=body.get("color"), description=body.get("description"),
        is_rehearsal=bool(body.get("is_rehearsal", False)),
        is_secure=bool(body.get("is_secure", False)),
        is_split=bool(body.get("is_split", False)),
    )
    db.add(t)
    await db.flush()

    # Leaders — default to the caller if list missing/empty (matches PCO UX)
    leader_ids_raw = body.get("leader_member_ids")
    if not leader_ids_raw and caller is not None:
        leader_ids_raw = [str(caller.id)]
    await _replace_leaders(t.id, org.id, leader_ids_raw or [], db)

    # Service-types binding
    await _replace_service_types(t.id, org.id, body.get("service_type_ids") or [], db)

    await db.refresh(t)
    return await _serialize_team(t, db)


@router.patch("/{team_id}")
async def update_team(
    slug: str, team_id: str, body: dict,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, _, role = await _auth(slug, authorization, tenant_access, db)
    _require_priv(role)
    t = await _team(team_id, org.id, db)
    if "name" in body:
        n = (body["name"] or "").strip()
        if not n:
            raise HTTPException(status_code=400, detail="Nombre vacío")
        t.name = n
    if "color" in body: t.color = body["color"]
    if "description" in body: t.description = body["description"]
    if "is_rehearsal" in body: t.is_rehearsal = bool(body["is_rehearsal"])
    if "is_secure" in body:    t.is_secure    = bool(body["is_secure"])
    if "is_split" in body:     t.is_split     = bool(body["is_split"])
    _STR_FIELDS = ("default_status", "replies_to", "last_scheduled_date_rule",
                   "scheduled_viewer_access", "reschedule_on_decline")
    _BOOL_FIELDS = ("notify_on_prepare", "gap_alerts_enabled", "signup_sheets_auto_enable")
    for f in _STR_FIELDS:
        if f in body: setattr(t, f, str(body[f]))
    for f in _BOOL_FIELDS:
        if f in body: setattr(t, f, bool(body[f]))
    if "leader_member_ids" in body and isinstance(body["leader_member_ids"], list):
        await _replace_leaders(t.id, org.id, body["leader_member_ids"], db)
    if "service_type_ids" in body and isinstance(body["service_type_ids"], list):
        # Mínimo 1 tipo de servicio requerido si se modifica la lista.
        # Filtra UUIDs válidos del mismo org para contar correctamente.
        valid_count = 0
        for raw in body["service_type_ids"]:
            try:
                stid = uuid.UUID(raw)
            except Exception:
                continue
            ok = (await db.execute(
                select(ServiceType.id).where(ServiceType.id == stid, ServiceType.org_id == org.id)
            )).scalar_one_or_none()
            if ok is not None:
                valid_count += 1
        if valid_count < 1:
            raise HTTPException(status_code=400, detail="Selecciona al menos un tipo de servicio.")
        await _replace_service_types(t.id, org.id, body["service_type_ids"], db)
    if "related_team_ids" in body and isinstance(body["related_team_ids"], list):
        await _replace_related_teams(t.id, org.id, body["related_team_ids"], db)
    await db.flush()
    return await _serialize_team(t, db)


@router.delete("/{team_id}", status_code=204)
async def delete_team(
    slug: str, team_id: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, _, role = await _auth(slug, authorization, tenant_access, db)
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
    org, _, _ = await _auth(slug, authorization, tenant_access, db)
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
    org, _, role = await _auth(slug, authorization, tenant_access, db)
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
    org, _, role = await _auth(slug, authorization, tenant_access, db)
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


# ─────────────────────────────────────────────────────────────────────────────
# Team Positions — Piano, Bajo, Guitarra Acústica, etc.
# Lives under a Team. Members joined via team_position_members (M2M).
# "All team members" = DISTINCT union across all positions in the team.
# ─────────────────────────────────────────────────────────────────────────────

async def _position(pos_id: str, team_id: uuid.UUID, db: AsyncSession) -> TeamPosition:
    try:
        pu = uuid.UUID(pos_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")
    row = (await db.execute(
        select(TeamPosition).where(TeamPosition.id == pu, TeamPosition.team_id == team_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Posición no encontrada")
    return row


async def _build_person_payload(om: OrgMember, sm: ServiceMember | None) -> dict:
    """Shape used in detail/list responses for any team-person view."""
    return {
        "member_id": str(om.id),
        "full_name": om.full_name,
        "email": om.email,
        "avatar": om.avatar,
        "preferences": {
            "max_per_month": sm.scheduling_max_per_month if sm else None,
            "max_per_day": sm.scheduling_max_per_day if sm else None,
        },
    }


async def _members_with_prefs(member_ids: list[uuid.UUID], org_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    if not member_ids:
        return []
    pairs = (await db.execute(
        select(OrgMember, ServiceMember)
        .outerjoin(ServiceMember, ServiceMember.member_id == OrgMember.id)
        .where(OrgMember.id.in_(member_ids), OrgMember.org_id == org_id)
        .order_by(OrgMember.full_name)
    )).all()
    return [await _build_person_payload(om, sm) for om, sm in pairs]


@router.get("/{team_id}/detail")
async def team_detail(
    slug: str, team_id: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Full team payload used by the detail view. Includes leaders, positions
    (with their members), and the deduplicated "all members" view.
    """
    org, _, _ = await _auth(slug, authorization, tenant_access, db)
    t = await _team(team_id, org.id, db)

    base = await _serialize_team(t, db)

    # Leaders with preferences
    leader_ids = [uuid.UUID(x) for x in base["leader_member_ids"]]
    leaders_full = await _members_with_prefs(leader_ids, org.id, db)

    # Positions + their members
    positions = (await db.execute(
        select(TeamPosition).where(TeamPosition.team_id == t.id)
        .order_by(TeamPosition.sort_order, TeamPosition.name)
    )).scalars().all()

    position_payload: list[dict] = []
    all_member_ids: set[uuid.UUID] = set()
    for p in positions:
        pm_rows = (await db.execute(
            select(TeamPositionMember.member_id).where(TeamPositionMember.position_id == p.id)
        )).scalars().all()
        all_member_ids.update(pm_rows)
        members = await _members_with_prefs(list(pm_rows), org.id, db)
        position_payload.append({
            "id": str(p.id),
            "name": p.name,
            "sort_order": p.sort_order,
            "member_count": len(members),
            "members": members,
        })

    all_members = await _members_with_prefs(list(all_member_ids), org.id, db)

    return {
        "team": base,
        "leaders": leaders_full,
        "positions": position_payload,
        "all_members": all_members,
    }


# ── Position CRUD ────────────────────────────────────────────────────────────
@router.post("/{team_id}/positions", status_code=201)
async def create_position(
    slug: str, team_id: str, body: dict,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, _, role = await _auth(slug, authorization, tenant_access, db)
    _require_priv(role)
    t = await _team(team_id, org.id, db)
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nombre requerido")
    dup = (await db.execute(
        select(TeamPosition).where(TeamPosition.team_id == t.id, TeamPosition.name == name)
    )).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(status_code=409, detail="Ya existe una posición con ese nombre")
    # Append at end
    last = (await db.execute(
        select(TeamPosition.sort_order).where(TeamPosition.team_id == t.id)
        .order_by(TeamPosition.sort_order.desc()).limit(1)
    )).scalar_one_or_none()
    p = TeamPosition(team_id=t.id, name=name, sort_order=(last or 0) + 1)
    db.add(p)
    await db.flush()
    await db.refresh(p)
    return {"id": str(p.id), "name": p.name, "sort_order": p.sort_order, "member_count": 0, "members": []}


@router.patch("/{team_id}/positions/{pos_id}")
async def rename_position(
    slug: str, team_id: str, pos_id: str, body: dict,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, _, role = await _auth(slug, authorization, tenant_access, db)
    _require_priv(role)
    t = await _team(team_id, org.id, db)
    p = await _position(pos_id, t.id, db)
    if "name" in body:
        n = (body["name"] or "").strip()
        if not n:
            raise HTTPException(status_code=400, detail="Nombre vacío")
        # uniqueness check (excluding self)
        dup = (await db.execute(
            select(TeamPosition).where(
                TeamPosition.team_id == t.id,
                TeamPosition.name == n,
                TeamPosition.id != p.id,
            )
        )).scalar_one_or_none()
        if dup is not None:
            raise HTTPException(status_code=409, detail="Ya existe una posición con ese nombre")
        p.name = n
    if "sort_order" in body:
        try:
            p.sort_order = int(body["sort_order"])
        except Exception:
            pass
    await db.flush()
    return {"id": str(p.id), "name": p.name, "sort_order": p.sort_order}


@router.delete("/{team_id}/positions/{pos_id}", status_code=204)
async def delete_position(
    slug: str, team_id: str, pos_id: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, _, role = await _auth(slug, authorization, tenant_access, db)
    _require_priv(role)
    t = await _team(team_id, org.id, db)
    p = await _position(pos_id, t.id, db)
    await db.delete(p)


# ── Position members ─────────────────────────────────────────────────────────
@router.post("/{team_id}/positions/{pos_id}/members", status_code=201)
async def add_position_members(
    slug: str, team_id: str, pos_id: str, body: dict,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Bulk-add. Idempotent: existing pairs are skipped, unknown ids dropped.

    Auto-enroll: any picked org_member without a `service_members` row is
    silently enrolled in Services with default viewer permissions. These are
    returned in `newly_enrolled` so the frontend can launch a welcome-email
    compose flow.

    Body: { "member_ids": [...] }
    Returns: {
      "added": [member_id, ...],
      "skipped": [member_id, ...],
      "newly_enrolled": [{member_id, full_name, email, service_member_id}, ...]
    }
    """
    org, _, role = await _auth(slug, authorization, tenant_access, db)
    _require_priv(role)
    t = await _team(team_id, org.id, db)
    p = await _position(pos_id, t.id, db)
    raw_ids = body.get("member_ids") or []
    if not isinstance(raw_ids, list):
        raise HTTPException(status_code=400, detail="member_ids debe ser lista")

    # Already-present set
    present = set((await db.execute(
        select(TeamPositionMember.member_id).where(TeamPositionMember.position_id == p.id)
    )).scalars().all())

    # Existing ServiceMember member_ids in this org (to detect "new to Services")
    existing_sm = set((await db.execute(
        select(ServiceMember.member_id).where(ServiceMember.org_id == org.id)
    )).scalars().all())

    added: list[str] = []
    skipped: list[str] = []
    newly_enrolled: list[dict] = []
    seen: set[uuid.UUID] = set()
    for raw in raw_ids:
        try:
            mid = uuid.UUID(raw)
        except Exception:
            continue
        if mid in seen:
            continue
        seen.add(mid)
        om = (await db.execute(
            select(OrgMember).where(OrgMember.id == mid, OrgMember.org_id == org.id)
        )).scalar_one_or_none()
        if om is None:
            continue
        # Auto-enroll into Services if not present (skip for org admins —
        # they already have full access via org role).
        if mid not in existing_sm and om.role != "admin":
            sm = ServiceMember(
                org_id=org.id, member_id=mid,
                service_role="viewer", songs_role="viewer", media_role="viewer",
                file_access_plans=True, file_access_songs=True, file_access_media=True,
            )
            db.add(sm)
            await db.flush()
            existing_sm.add(mid)
            newly_enrolled.append({
                "member_id": str(mid),
                "service_member_id": str(sm.id),
                "full_name": om.full_name,
                "email": om.email,
            })
        if mid in present:
            skipped.append(str(mid))
            continue
        db.add(TeamPositionMember(position_id=p.id, member_id=mid))
        added.append(str(mid))
    await db.flush()
    return {"added": added, "skipped": skipped, "newly_enrolled": newly_enrolled}


@router.delete("/{team_id}/positions/{pos_id}/members/{member_id}", status_code=204)
async def remove_position_member(
    slug: str, team_id: str, pos_id: str, member_id: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, _, role = await _auth(slug, authorization, tenant_access, db)
    _require_priv(role)
    t = await _team(team_id, org.id, db)
    p = await _position(pos_id, t.id, db)
    try:
        mid = uuid.UUID(member_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")
    row = (await db.execute(
        select(TeamPositionMember).where(
            TeamPositionMember.position_id == p.id,
            TeamPositionMember.member_id == mid,
        )
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="No está en la posición")
    await db.delete(row)
