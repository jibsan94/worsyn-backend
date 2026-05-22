"""Tenant module: Services.

Owns: service_types, service_times, service_teams, service_plans.

A ServiceType is the *template* — name, recurrence, time slots, participating teams.
ServicePlan is a concrete instance (a specific date). Occurrences for recurring
services are projected on the fly in `/calendar/occurrences` based on
ServiceType.recurrence + ServiceTime rows.

All endpoints scoped to /tenant/{slug}/services and gated by tenant JWT.
Mutations require admin or leader role on the org.
"""
import uuid
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.models.models import (
    Organization, OrgMember, ServicePlan, ServiceTeam, ServiceTime, ServiceType, Team,
)

router = APIRouter(prefix="/tenant/{slug}/services", tags=["Tenant · Services"])

VALID_RECURRENCE = {"none", "random", "daily", "weekly", "weekdays", "biweekly", "monthly"}


# ── Auth helper (mirrors tenant_member_attachments) ───────────────────────────
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


def _parse_time(s: str) -> time:
    try:
        h, m = s.split(":")[:2]
        return time(hour=int(h), minute=int(m))
    except Exception:
        raise HTTPException(status_code=400, detail=f"Hora inválida: {s} (formato HH:MM)")


def _parse_date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Fecha inválida: {s} (formato YYYY-MM-DD)")


async def _serialize_type(t: ServiceType, db: AsyncSession) -> dict:
    times = (await db.execute(
        select(ServiceTime).where(ServiceTime.service_type_id == t.id).order_by(ServiceTime.sort_order, ServiceTime.start_time)
    )).scalars().all()
    teams = (await db.execute(
        select(ServiceTeam).where(ServiceTeam.service_type_id == t.id).order_by(ServiceTeam.sort_order)
    )).scalars().all()
    return {
        "id": str(t.id),
        "name": t.name,
        "color": t.color,
        "sort_order": t.sort_order,
        "recurrence": t.recurrence,
        "description": t.description,
        "times": [
            {
                "id": str(x.id),
                "starts_on": x.starts_on.isoformat(),
                "start_time": x.start_time.strftime("%H:%M"),
                "end_time": x.end_time.strftime("%H:%M"),
                "weekday": x.starts_on.weekday(),
                "sort_order": x.sort_order,
            } for x in times
        ],
        "team_ids": [str(x.team_id) for x in teams],
    }


# ── Service types CRUD ────────────────────────────────────────────────────────
@router.get("/types")
async def list_types(
    slug: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, _ = await _auth(slug, authorization, tenant_access, db)
    rows = (await db.execute(
        select(ServiceType).where(ServiceType.org_id == org.id).order_by(ServiceType.sort_order, ServiceType.name)
    )).scalars().all()
    return [await _serialize_type(t, db) for t in rows]


@router.post("/types", status_code=status.HTTP_201_CREATED)
async def create_type(
    slug: str,
    body: dict,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Create service type with nested times + team picks.

    Body: { name, color?, recurrence?, description?, times: [{starts_on, start_time, end_time}], team_ids: [uuid] }
    """
    org, role = await _auth(slug, authorization, tenant_access, db)
    _require_priv(role)

    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="El nombre es obligatorio")
    recurrence = (body.get("recurrence") or "weekly").lower()
    if recurrence not in VALID_RECURRENCE:
        raise HTTPException(status_code=400, detail=f"Recurrencia inválida: {recurrence}")

    times_in = body.get("times") or []
    if not isinstance(times_in, list) or not times_in:
        raise HTTPException(status_code=400, detail="Debes definir al menos un horario")

    team_ids = body.get("team_ids") or []
    if not isinstance(team_ids, list):
        team_ids = []

    st = ServiceType(
        org_id=org.id,
        name=name,
        color=body.get("color"),
        sort_order=int(body.get("sort_order") or 0),
        recurrence=recurrence,
        description=body.get("description"),
    )
    db.add(st)
    await db.flush()

    for i, t in enumerate(times_in):
        d = _parse_date(t.get("starts_on") or "")
        st_t = _parse_time(t.get("start_time") or "")
        en_t = _parse_time(t.get("end_time") or "")
        db.add(ServiceTime(
            org_id=org.id, service_type_id=st.id, starts_on=d,
            start_time=st_t, end_time=en_t, sort_order=int(t.get("sort_order") or i),
        ))

    for i, tid in enumerate(team_ids):
        try:
            tu = uuid.UUID(tid)
        except Exception:
            continue
        # Validate team belongs to org
        team_ok = (await db.execute(
            select(Team).where(Team.id == tu, Team.org_id == org.id)
        )).scalar_one_or_none()
        if team_ok is None:
            continue
        db.add(ServiceTeam(service_type_id=st.id, team_id=tu, sort_order=i))

    await db.flush()
    await db.refresh(st)
    return await _serialize_type(st, db)


@router.patch("/types/{type_id}")
async def update_type(
    slug: str, type_id: str, body: dict,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, role = await _auth(slug, authorization, tenant_access, db)
    _require_priv(role)
    try:
        tu = uuid.UUID(type_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")
    st = (await db.execute(
        select(ServiceType).where(ServiceType.id == tu, ServiceType.org_id == org.id)
    )).scalar_one_or_none()
    if st is None:
        raise HTTPException(status_code=404, detail="Tipo no encontrado")

    if "name" in body:
        n = (body["name"] or "").strip()
        if not n:
            raise HTTPException(status_code=400, detail="Nombre vacío")
        st.name = n
    if "color" in body: st.color = body["color"]
    if "description" in body: st.description = body["description"]
    if "sort_order" in body: st.sort_order = int(body["sort_order"] or 0)
    if "recurrence" in body:
        r = (body["recurrence"] or "").lower()
        if r not in VALID_RECURRENCE:
            raise HTTPException(status_code=400, detail=f"Recurrencia inválida: {r}")
        st.recurrence = r

    # Replace nested collections if supplied
    if "times" in body and isinstance(body["times"], list):
        existing = (await db.execute(select(ServiceTime).where(ServiceTime.service_type_id == st.id))).scalars().all()
        for x in existing:
            await db.delete(x)
        for i, t in enumerate(body["times"]):
            d = _parse_date(t.get("starts_on") or "")
            st_t = _parse_time(t.get("start_time") or "")
            en_t = _parse_time(t.get("end_time") or "")
            db.add(ServiceTime(
                org_id=org.id, service_type_id=st.id, starts_on=d,
                start_time=st_t, end_time=en_t, sort_order=int(t.get("sort_order") or i),
            ))

    if "team_ids" in body and isinstance(body["team_ids"], list):
        existing = (await db.execute(select(ServiceTeam).where(ServiceTeam.service_type_id == st.id))).scalars().all()
        for x in existing:
            await db.delete(x)
        for i, tid in enumerate(body["team_ids"]):
            try:
                tu = uuid.UUID(tid)
            except Exception:
                continue
            team_ok = (await db.execute(
                select(Team).where(Team.id == tu, Team.org_id == org.id)
            )).scalar_one_or_none()
            if team_ok is None:
                continue
            db.add(ServiceTeam(service_type_id=st.id, team_id=tu, sort_order=i))

    await db.flush()
    await db.refresh(st)
    return await _serialize_type(st, db)


@router.delete("/types/{type_id}", status_code=204)
async def delete_type(
    slug: str, type_id: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, role = await _auth(slug, authorization, tenant_access, db)
    _require_priv(role)
    try:
        tu = uuid.UUID(type_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")
    st = (await db.execute(
        select(ServiceType).where(ServiceType.id == tu, ServiceType.org_id == org.id)
    )).scalar_one_or_none()
    if st is None:
        raise HTTPException(status_code=404, detail="Tipo no encontrado")
    await db.delete(st)


# ── Service plans (concrete instances) ────────────────────────────────────────
@router.get("/plans")
async def list_plans(
    slug: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, _ = await _auth(slug, authorization, tenant_access, db)
    rows = (await db.execute(
        select(ServicePlan).where(ServicePlan.org_id == org.id).order_by(ServicePlan.scheduled_at.desc().nullslast())
    )).scalars().all()
    return [
        {
            "id": str(r.id), "title": r.title, "status": r.status,
            "scheduled_at": r.scheduled_at.isoformat() if r.scheduled_at else None,
            "service_type_id": str(r.service_type_id) if r.service_type_id else None,
        } for r in rows
    ]


@router.post("/plans", status_code=201)
async def create_plan(
    slug: str, body: dict,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, role = await _auth(slug, authorization, tenant_access, db)
    _require_priv(role)
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Título requerido")
    sched = None
    if body.get("scheduled_at"):
        try:
            sched = datetime.fromisoformat(body["scheduled_at"].replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(status_code=400, detail="scheduled_at inválido (ISO 8601)")
    type_id = None
    if body.get("service_type_id"):
        try:
            type_id = uuid.UUID(body["service_type_id"])
        except Exception:
            raise HTTPException(status_code=400, detail="service_type_id inválido")

    sp = ServicePlan(
        org_id=org.id, service_type_id=type_id, title=title,
        scheduled_at=sched, status=(body.get("status") or "draft"), notes=body.get("notes"),
    )
    db.add(sp)
    await db.flush()
    await db.refresh(sp)
    return {
        "id": str(sp.id), "title": sp.title, "status": sp.status,
        "scheduled_at": sp.scheduled_at.isoformat() if sp.scheduled_at else None,
        "service_type_id": str(sp.service_type_id) if sp.service_type_id else None,
    }


# ── Occurrence projection (used by calendar) ──────────────────────────────────
def _project(t_recurrence: str, anchor: date, until: date) -> list[date]:
    """Return all occurrence dates >= anchor and <= until for a recurrence rule."""
    out: list[date] = []
    if anchor > until:
        return out
    cur = anchor
    if t_recurrence == "none":
        return [anchor] if anchor <= until else []
    if t_recurrence == "random":
        return [anchor] if anchor <= until else []
    step: timedelta | None = None
    if t_recurrence == "daily": step = timedelta(days=1)
    elif t_recurrence == "weekly": step = timedelta(weeks=1)
    elif t_recurrence == "biweekly": step = timedelta(weeks=2)
    elif t_recurrence == "weekdays":
        while cur <= until:
            if cur.weekday() < 5:
                out.append(cur)
            cur += timedelta(days=1)
        return out
    elif t_recurrence == "monthly":
        while cur <= until:
            out.append(cur)
            # next same-day-of-month
            y, m = cur.year, cur.month + 1
            if m > 12: m, y = 1, y + 1
            try:
                cur = date(y, m, cur.day)
            except ValueError:
                # day exceeds month length — use last day of month
                if m == 12: nm, ny = 1, y + 1
                else: nm, ny = m + 1, y
                cur = date(ny, nm, 1) - timedelta(days=1)
        return out
    if step is None:
        return out
    while cur <= until:
        out.append(cur)
        cur += step
    return out


@router.get("/occurrences")
async def list_occurrences(
    slug: str,
    range_from: str | None = None,
    range_to: str | None = None,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Project service_times forward into concrete occurrences. Default window: 90 days from today."""
    org, _ = await _auth(slug, authorization, tenant_access, db)
    today = date.today()
    rf = _parse_date(range_from) if range_from else today
    rt = _parse_date(range_to) if range_to else today + timedelta(days=90)
    types = (await db.execute(
        select(ServiceType).where(ServiceType.org_id == org.id)
    )).scalars().all()
    out: list[dict] = []
    for t in types:
        times = (await db.execute(
            select(ServiceTime).where(ServiceTime.service_type_id == t.id)
        )).scalars().all()
        for st in times:
            anchor = st.starts_on if st.starts_on >= rf else st.starts_on
            # If the anchor is in the past, advance forward via recurrence
            if t.recurrence in ("weekly", "biweekly", "daily", "weekdays", "monthly") and anchor < rf:
                # generate from anchor → align cursor into window
                projected = _project(t.recurrence, anchor, rt)
                projected = [d for d in projected if d >= rf]
                dates = projected
            else:
                dates = _project(t.recurrence, max(anchor, rf), rt)
            for d in dates:
                out.append({
                    "service_type_id": str(t.id),
                    "service_type_name": t.name,
                    "color": t.color,
                    "date": d.isoformat(),
                    "start_time": st.start_time.strftime("%H:%M"),
                    "end_time": st.end_time.strftime("%H:%M"),
                })
    out.sort(key=lambda x: (x["date"], x["start_time"]))
    return out
