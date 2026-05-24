"""Tenant module: Email templates + Message log + Send.

Two surfaces under one router (shared auth helpers):

  /tenant/{slug}/email/templates           — per-org reusable templates (4 kinds)
  /tenant/{slug}/email/messages            — log of sent/received messages
  /tenant/{slug}/email/messages/preview    — server-side render preview
  /tenant/{slug}/services/people/{sm_id}/messages — view a person's mailbox

Sending is a NO-OP for now: SMTP isn't wired. New messages are stored with
status='queued'. When SMTP lands (worsyn-integrations), a worker dispatches
queued rows and flips status to 'sent' or 'failed'.

Retention: rows older than `organizations.email_retention_months` (default 3,
max 12) are eligible for cleanup. Cron not yet wired.

Variable engine docs → `artifacts/EMAIL-VARIABLES.md`.
"""
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, Header, HTTPException, status

from app.services.smtp import dispatch_queued

WELCOME_TOKEN_TTL_DAYS = 7

# Default welcome template — auto-seeded per org the first time templates are
# listed if no `welcome` template exists. Editable + deletable from the UI.
DEFAULT_WELCOME_SUBJECT = "¡Bienvenido(a) {{ to.first_name }} a {{ organization.name }} en Worsyn!"
DEFAULT_WELCOME_BODY = """<p>Hola {{ to.name }},</p>

<p>¡{{ from.name }} te ha invitado a usar la cuenta de Services de {{ organization.name }} en Worsyn!</p>

<p>Worsyn Services es una herramienta en línea que ayuda a las iglesias a organizar a su equipo y planificar los próximos servicios. Con tus permisos de <strong>{{ to.max_plan_permissions_s }}</strong>, podrás iniciar sesión en cualquier momento para activar las notificaciones, marcar los días en los que no estarás disponible y ajustar tus preferencias de programación.</p>

<h3>Cómo iniciar sesión</h3>

<p>Para acceder a Worsyn, necesitas establecer tu contraseña:</p>

<p style="text-align: center; margin: 24px 0;">
  <a href="{{ to.welcome_url }}" style="background:#4F46E5;color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600;display:inline-block">Establecer mi contraseña</a>
</p>

<p style="font-size: 12px; color: #64748B;">El enlace caduca en {{ to.welcome_ttl_days }} días. Tu método de inicio de sesión es: <strong>{{ to.login_method }}</strong>. Recuerda no compartir tu contraseña con nadie.</p>

<hr/>

<h3>Enlaces útiles</h3>
<p>Si es tu primera vez usando Worsyn Services, te recomendamos visitar la página de Primeros pasos. También puedes:</p>
<ul>
  <li>Ver tu horario y planes asignados</li>
  <li>Configurar tus preferencias de programación</li>
  <li>Actualizar tu perfil</li>
  <li>Descargar la app móvil (próximamente)</li>
</ul>

{% if to.scheduler_at_all? %}
<hr/>
<p>Con tus permisos de <strong>{{ to.max_plan_permissions_s }}</strong>, también podrás gestionar equipos y programar personas en los planes. Tendrás acceso a las guías de coordinador y planificador de servicios.</p>
{% endif %}

<p style="margin-top: 24px;">{{ from.signature }}</p>
"""
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.models.models import (
    EmailMessage, EmailTemplate, Organization, OrgMember, ServiceMember,
)
from app.services.email_render import build_context, render

router = APIRouter(prefix="/tenant/{slug}/email", tags=["Tenant · Email"])
people_router = APIRouter(prefix="/tenant/{slug}/services/people", tags=["Tenant · Service People · Messages"])

VALID_KINDS = {"general", "schedule", "signup", "welcome"}


# ── Auth helper (mirror of service_people._auth) ──────────────────────────────
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
        return org, None, "admin", "administrator"
    caller = (await db.execute(
        select(OrgMember).where(OrgMember.id == uuid.UUID(data["sub"]), OrgMember.org_id == org.id)
    )).scalar_one_or_none()
    if caller is None:
        raise HTTPException(status_code=401, detail="Miembro no encontrado")
    sm = (await db.execute(
        select(ServiceMember).where(ServiceMember.member_id == caller.id)
    )).scalar_one_or_none()
    return org, caller, caller.role, (sm.service_role if sm else None)


def _can_manage_templates(org_role: str | None, svc_role: str | None) -> bool:
    return org_role in ("admin", "leader") or svc_role in ("administrator", "editor", "coordinator")


def _can_send(org_role: str | None, svc_role: str | None) -> bool:
    return org_role in ("admin", "leader") or svc_role in ("administrator", "editor", "coordinator")


# ─────────────────────────────────────────────────────────────────────────────
# Templates
# ─────────────────────────────────────────────────────────────────────────────
def _serialize_template(t: EmailTemplate) -> dict:
    return {
        "id": str(t.id), "kind": t.kind, "name": t.name,
        "subject": t.subject, "body": t.body,
        "is_default": t.is_default,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


@router.get("/templates")
async def list_templates(
    slug: str,
    kind: str | None = None,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, _, _, _ = await _auth(slug, authorization, tenant_access, db)
    await autoseed_default_templates(org.id, db)  # ensure default Welcome exists
    q = select(EmailTemplate).where(EmailTemplate.org_id == org.id)
    if kind:
        if kind not in VALID_KINDS:
            raise HTTPException(status_code=400, detail=f"kind inválido: {kind}")
        q = q.where(EmailTemplate.kind == kind)
    q = q.order_by(EmailTemplate.kind, EmailTemplate.name)
    rows = (await db.execute(q)).scalars().all()
    return [_serialize_template(t) for t in rows]


@router.post("/templates", status_code=201)
async def create_template(
    slug: str, body: dict,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, caller, org_role, svc_role = await _auth(slug, authorization, tenant_access, db)
    if not _can_manage_templates(org_role, svc_role):
        raise HTTPException(status_code=403, detail="Sin permiso")
    kind = (body.get("kind") or "general").lower()
    if kind not in VALID_KINDS:
        raise HTTPException(status_code=400, detail=f"kind inválido: {kind}")
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nombre requerido")
    t = EmailTemplate(
        org_id=org.id, kind=kind, name=name,
        subject=(body.get("subject") or "").strip(),
        body=(body.get("body") or ""),
        is_default=bool(body.get("is_default", False)),
        created_by=caller.id if caller else None,
    )
    db.add(t)
    await db.flush()
    await db.refresh(t)
    return _serialize_template(t)


@router.patch("/templates/{tpl_id}")
async def update_template(
    slug: str, tpl_id: str, body: dict,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, _, org_role, svc_role = await _auth(slug, authorization, tenant_access, db)
    if not _can_manage_templates(org_role, svc_role):
        raise HTTPException(status_code=403, detail="Sin permiso")
    try:
        tid = uuid.UUID(tpl_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")
    t = (await db.execute(
        select(EmailTemplate).where(EmailTemplate.id == tid, EmailTemplate.org_id == org.id)
    )).scalar_one_or_none()
    if t is None:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    if "kind" in body:
        k = (body["kind"] or "").lower()
        if k not in VALID_KINDS:
            raise HTTPException(status_code=400, detail=f"kind inválido: {k}")
        t.kind = k
    if "name" in body:
        n = (body["name"] or "").strip()
        if not n:
            raise HTTPException(status_code=400, detail="Nombre vacío")
        t.name = n
    if "subject" in body: t.subject = (body["subject"] or "")
    if "body" in body:    t.body    = (body["body"] or "")
    if "is_default" in body: t.is_default = bool(body["is_default"])
    await db.flush()
    return _serialize_template(t)


@router.delete("/templates/{tpl_id}", status_code=204)
async def delete_template(
    slug: str, tpl_id: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, _, org_role, svc_role = await _auth(slug, authorization, tenant_access, db)
    if not _can_manage_templates(org_role, svc_role):
        raise HTTPException(status_code=403, detail="Sin permiso")
    try:
        tid = uuid.UUID(tpl_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")
    t = (await db.execute(
        select(EmailTemplate).where(EmailTemplate.id == tid, EmailTemplate.org_id == org.id)
    )).scalar_one_or_none()
    if t is None:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    await db.delete(t)


# ─────────────────────────────────────────────────────────────────────────────
# Send (preview + dispatch) + messages list
# ─────────────────────────────────────────────────────────────────────────────
def _serialize_message(m: EmailMessage, who_name: str | None = None) -> dict:
    return {
        "id": str(m.id),
        "direction": m.direction, "status": m.status,
        "subject": m.subject, "body": m.body_rendered,
        "recipient_email": m.recipient_email, "sender_email": m.sender_email,
        "recipient_member_id": str(m.recipient_member_id) if m.recipient_member_id else None,
        "sender_member_id": str(m.sender_member_id) if m.sender_member_id else None,
        "template_id": str(m.template_id) if m.template_id else None,
        "sent_at": m.sent_at.isoformat() if m.sent_at else None,
        "created_at": m.created_at.isoformat(),
        "error": m.error,
        "counterparty_name": who_name,
    }


async def _enrich_messages(rows: list[EmailMessage], db: AsyncSession) -> list[dict]:
    ids: set[uuid.UUID] = set()
    for r in rows:
        for x in (r.sender_member_id, r.recipient_member_id):
            if x is not None:
                ids.add(x)
    name_by_id: dict[uuid.UUID, str] = {}
    if ids:
        oms = (await db.execute(select(OrgMember).where(OrgMember.id.in_(ids)))).scalars().all()
        name_by_id = {om.id: (om.full_name or om.email) for om in oms}
    out = []
    for r in rows:
        # counterparty = the "other side" — for a sent msg, the recipient; for received, the sender
        cp_id = r.recipient_member_id if r.direction == "sent" else r.sender_member_id
        out.append(_serialize_message(r, name_by_id.get(cp_id) if cp_id else None))
    return out


@router.post("/messages/preview")
async def preview_message(
    slug: str, body: dict,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Render a template against a specific recipient and return subject + body."""
    org, caller, org_role, svc_role = await _auth(slug, authorization, tenant_access, db)
    if not _can_send(org_role, svc_role):
        raise HTTPException(status_code=403, detail="Sin permiso")
    try:
        rid = uuid.UUID(body.get("recipient_member_id") or "")
    except Exception:
        raise HTTPException(status_code=400, detail="recipient_member_id inválido")
    recipient = (await db.execute(
        select(OrgMember).where(OrgMember.id == rid, OrgMember.org_id == org.id)
    )).scalar_one_or_none()
    if recipient is None:
        raise HTTPException(status_code=404, detail="Destinatario no encontrado")
    rsm = (await db.execute(
        select(ServiceMember).where(ServiceMember.member_id == recipient.id)
    )).scalar_one_or_none()
    sender_sm = (await db.execute(
        select(ServiceMember).where(ServiceMember.member_id == caller.id)
    )).scalar_one_or_none() if caller else None
    sig = (sender_sm.signature_text if sender_sm else "") or ""
    sig_img = (sender_sm.signature_image if sender_sm else None)
    ctx = build_context(
        sender_member=caller, sender_signature=sig, sender_signature_image=sig_img,
        recipient_member=recipient,
        recipient_service_role=(rsm.service_role if rsm else None),
        recipient_has_password=bool(recipient.hashed_password),
        organization=org,
    )
    return {
        "subject": render(body.get("subject") or "", ctx),
        "body": render(body.get("body") or "", ctx),
        "context_keys_used": sorted(set([])),  # could surface used keys later
    }


@router.get("/messages")
async def list_messages(
    slug: str,
    direction: str | None = None,
    limit: int = 100,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """List ALL messages in the org (admin/leader). Personal mailbox uses the
    per-person endpoint under /services/people."""
    org, _, org_role, svc_role = await _auth(slug, authorization, tenant_access, db)
    if org_role not in ("admin", "leader") and svc_role not in ("administrator", "editor", "coordinator"):
        raise HTTPException(status_code=403, detail="Sin permiso")
    q = select(EmailMessage).where(EmailMessage.org_id == org.id)
    if direction:
        if direction not in ("sent", "received"):
            raise HTTPException(status_code=400, detail="direction inválido")
        q = q.where(EmailMessage.direction == direction)
    q = q.order_by(EmailMessage.created_at.desc()).limit(max(1, min(500, limit)))
    rows = (await db.execute(q)).scalars().all()
    return await _enrich_messages(rows, db)


@router.get("/messages/{msg_id}")
async def get_message(
    slug: str, msg_id: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, caller, org_role, svc_role = await _auth(slug, authorization, tenant_access, db)
    try:
        mid = uuid.UUID(msg_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")
    m = (await db.execute(
        select(EmailMessage).where(EmailMessage.id == mid, EmailMessage.org_id == org.id)
    )).scalar_one_or_none()
    if m is None:
        raise HTTPException(status_code=404, detail="Mensaje no encontrado")
    # Admin/leader can read all; otherwise the person must be sender or recipient
    if not (org_role in ("admin", "leader") or svc_role == "administrator"):
        if caller is None or (m.sender_member_id != caller.id and m.recipient_member_id != caller.id):
            raise HTTPException(status_code=403, detail="Sin permiso")
    enriched = await _enrich_messages([m], db)
    return enriched[0]


@router.delete("/messages/{msg_id}", status_code=204)
async def delete_message(
    slug: str, msg_id: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Delete a message row from Worsyn's log. Does NOT remove from the user's
    actual email inbox (Gmail/iCloud/etc.) — that's out of our control.

    Allowed: admin/leader/coord/svc-editor for any row; otherwise the sender or
    the recipient may delete only their own.
    """
    org, caller, org_role, svc_role = await _auth(slug, authorization, tenant_access, db)
    try:
        mid = uuid.UUID(msg_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")
    m = (await db.execute(
        select(EmailMessage).where(EmailMessage.id == mid, EmailMessage.org_id == org.id)
    )).scalar_one_or_none()
    if m is None:
        raise HTTPException(status_code=404, detail="Mensaje no encontrado")
    is_admin = org_role in ("admin", "leader") or svc_role in ("administrator", "editor", "coordinator")
    is_party = caller is not None and (m.sender_member_id == caller.id or m.recipient_member_id == caller.id)
    if not (is_admin or is_party):
        raise HTTPException(status_code=403, detail="Sin permiso para eliminar")
    await db.delete(m)


@router.post("/messages", status_code=201)
async def send_message(
    slug: str, body: dict,
    background: BackgroundTasks,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Compose and "send" one email per recipient. SMTP is not wired yet — each
    message is stored with status='queued' and timestamped on dispatch later.

    Body:
      {
        "recipient_member_ids": ["<uuid>", ...],   // 1..50
        "template_id": "<uuid>",                   // optional
        "subject": "Hola {{ to.first_name }}",
        "body": "..."
      }
    Returns the list of created messages (one per recipient).
    """
    org, caller, org_role, svc_role = await _auth(slug, authorization, tenant_access, db)
    if not _can_send(org_role, svc_role):
        raise HTTPException(status_code=403, detail="Sin permiso para enviar correos")
    rids_raw = body.get("recipient_member_ids") or []
    if not isinstance(rids_raw, list) or not rids_raw:
        raise HTTPException(status_code=400, detail="Debes indicar al menos un destinatario")
    if len(rids_raw) > 50:
        raise HTTPException(status_code=400, detail="Máximo 50 destinatarios por envío")
    try:
        rids = [uuid.UUID(x) for x in rids_raw]
    except Exception:
        raise HTTPException(status_code=400, detail="recipient_member_ids contiene IDs inválidos")
    subject_tpl = body.get("subject") or ""
    body_tpl    = body.get("body") or ""
    if not subject_tpl.strip():
        raise HTTPException(status_code=400, detail="Asunto requerido")
    if not body_tpl.strip():
        raise HTTPException(status_code=400, detail="Cuerpo requerido")
    template_id = None
    if body.get("template_id"):
        try:
            template_id = uuid.UUID(body["template_id"])
        except Exception:
            raise HTTPException(status_code=400, detail="template_id inválido")
        ok_t = (await db.execute(
            select(EmailTemplate).where(EmailTemplate.id == template_id, EmailTemplate.org_id == org.id)
        )).scalar_one_or_none()
        if ok_t is None:
            raise HTTPException(status_code=400, detail="Plantilla no encontrada")

    recipients = (await db.execute(
        select(OrgMember).where(OrgMember.id.in_(rids), OrgMember.org_id == org.id)
    )).scalars().all()
    rec_by_id = {r.id: r for r in recipients}
    sender_sm = (await db.execute(
        select(ServiceMember).where(ServiceMember.member_id == caller.id)
    )).scalar_one_or_none() if caller else None
    sender_sig = (sender_sm.signature_text if sender_sm else None) or ""
    sender_sig_img = (sender_sm.signature_image if sender_sm else None)
    sender_email = (caller.email if caller else (org.email or "")) or ""

    created: list[EmailMessage] = []
    for rid in rids:
        rec = rec_by_id.get(rid)
        if rec is None:
            continue
        rsm = (await db.execute(
            select(ServiceMember).where(ServiceMember.member_id == rec.id)
        )).scalar_one_or_none()
        ctx = build_context(
            sender_member=caller, sender_signature=sender_sig, sender_signature_image=sender_sig_img,
            recipient_member=rec,
            recipient_service_role=(rsm.service_role if rsm else None),
            recipient_has_password=bool(rec.hashed_password),
            organization=org,
        )
        m = EmailMessage(
            org_id=org.id, template_id=template_id,
            sender_member_id=(caller.id if caller else None),
            recipient_member_id=rec.id,
            recipient_email=rec.email, sender_email=sender_email,
            direction="sent",
            status="queued",  # SMTP wiring will flip to 'sent' or 'failed'
            subject=render(subject_tpl, ctx),
            body_rendered=render(body_tpl, ctx),
            body_template=body_tpl,
        )
        db.add(m)
        created.append(m)
    await db.flush()
    for m in created:
        await db.refresh(m)
    # Capture IDs BEFORE the request session closes — the BackgroundTask opens
    # its own session and may not see the rows otherwise. Commit before scheduling.
    msg_ids = [m.id for m in created]
    await db.commit()
    background.add_task(dispatch_queued, msg_ids)
    return await _enrich_messages(created, db)


# ─────────────────────────────────────────────────────────────────────────────
# Per-person mailbox view
# ─────────────────────────────────────────────────────────────────────────────
@people_router.get("/{sm_id}/messages")
async def list_person_messages(
    slug: str, sm_id: str,
    direction: str | None = None,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """List messages for a person: anything they sent OR received."""
    org, caller, org_role, svc_role = await _auth(slug, authorization, tenant_access, db)
    try:
        smu = uuid.UUID(sm_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID inválido")
    sm = (await db.execute(
        select(ServiceMember).where(ServiceMember.id == smu, ServiceMember.org_id == org.id)
    )).scalar_one_or_none()
    if sm is None:
        raise HTTPException(status_code=404, detail="Persona no encontrada")
    # Self OR admin/leader OR svc admin
    if not (org_role in ("admin", "leader") or svc_role == "administrator"
            or (caller is not None and caller.id == sm.member_id)):
        raise HTTPException(status_code=403, detail="Sin permiso")
    q = select(EmailMessage).where(
        EmailMessage.org_id == org.id,
        or_(EmailMessage.sender_member_id == sm.member_id,
            EmailMessage.recipient_member_id == sm.member_id),
    )
    if direction in ("sent", "received"):
        q = q.where(EmailMessage.direction == direction)
    q = q.order_by(EmailMessage.created_at.desc()).limit(200)
    rows = (await db.execute(q)).scalars().all()
    return await _enrich_messages(rows, db)


# ─────────────────────────────────────────────────────────────────────────────
# Welcome flow (reusable from tenant_service_people)
# ─────────────────────────────────────────────────────────────────────────────
async def autoseed_default_templates(org_id: uuid.UUID, db: AsyncSession) -> None:
    """Insert the default Welcome template for an org if it has none yet.
    Idempotent — once any `welcome` template exists, no-op."""
    existing = (await db.execute(
        select(EmailTemplate).where(EmailTemplate.org_id == org_id, EmailTemplate.kind == "welcome").limit(1)
    )).scalar_one_or_none()
    if existing is not None:
        return
    db.add(EmailTemplate(
        org_id=org_id, kind="welcome",
        name="Bienvenida (por defecto)",
        subject=DEFAULT_WELCOME_SUBJECT,
        body=DEFAULT_WELCOME_BODY,
        is_default=True,
    ))
    await db.flush()


def _gen_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


async def _resolve_app_url(db: AsyncSession) -> str:
    """Read general.app_url from system_settings, fall back to localhost dev."""
    from app.models.models import SystemSetting  # local import to avoid cycle
    row = (await db.execute(
        select(SystemSetting).where(SystemSetting.key == "general.app_url")
    )).scalar_one_or_none()
    return (row.value if row and row.value else "http://10.211.55.11").rstrip("/")


async def send_welcome_email(
    *, org, recipient_member, sender_member, db: AsyncSession, background: BackgroundTasks,
) -> tuple[uuid.UUID, str]:
    """Issue a magic-link reset token + render the org's welcome template +
    queue an email + schedule SMTP dispatch.

    Returns (email_message_id, welcome_url). Idempotent on the membership row;
    caller is responsible for blocking duplicate sends if desired.
    """
    # Ensure org has a welcome template (auto-seed default)
    await autoseed_default_templates(org.id, db)
    tpl = (await db.execute(
        select(EmailTemplate).where(EmailTemplate.org_id == org.id, EmailTemplate.kind == "welcome")
        .order_by(EmailTemplate.is_default.desc(), EmailTemplate.created_at.asc())
        .limit(1)
    )).scalar_one()

    # Issue a fresh magic-link token (7d TTL). Overwrites any previous.
    token = _gen_token()
    recipient_member.password_reset_token = token
    recipient_member.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(days=WELCOME_TOKEN_TTL_DAYS)

    app_url = await _resolve_app_url(db)
    welcome_url = f"{app_url}/set-password/{token}"

    # Build render context. Use service_member role if any (else 'member').
    rsm = (await db.execute(
        select(ServiceMember).where(ServiceMember.member_id == recipient_member.id)
    )).scalar_one_or_none()
    sender_sm = (await db.execute(
        select(ServiceMember).where(ServiceMember.member_id == sender_member.id)
    )).scalar_one_or_none() if sender_member else None
    ctx = build_context(
        sender_member=sender_member,
        sender_signature=(sender_sm.signature_text if sender_sm else None) or "",
        sender_signature_image=(sender_sm.signature_image if sender_sm else None),
        recipient_member=recipient_member,
        recipient_service_role=(rsm.service_role if rsm else None),
        recipient_has_password=False,  # always false on welcome
        organization=org,
    )
    # Inject welcome-specific vars
    ctx["to"]["welcome_url"] = welcome_url
    ctx["to"]["welcome_ttl_days"] = WELCOME_TOKEN_TTL_DAYS

    # Fail-fast: render the subject + body NOW (before insert) and verify the
    # link survived substitution. If the URL got swallowed (corrupt template,
    # engine bug, missing app_url) we abort instead of sending a broken email.
    subject = render(tpl.subject, ctx)
    body    = render(tpl.body, ctx)
    if welcome_url not in body:
        raise RuntimeError(
            f"Welcome render lost the link. Template missing {{{{ to.welcome_url }}}}? "
            f"Edit the welcome template to include the placeholder."
        )

    sender_email = (sender_member.email if sender_member else (org.email or "")) or ""
    m = EmailMessage(
        org_id=org.id, template_id=tpl.id,
        sender_member_id=(sender_member.id if sender_member else None),
        recipient_member_id=recipient_member.id,
        recipient_email=recipient_member.email, sender_email=sender_email,
        direction="sent", status="queued",
        subject=subject,
        body_rendered=body,
        body_template=tpl.body,
    )
    db.add(m)
    await db.flush()
    mid = m.id
    background.add_task(dispatch_queued, [mid])
    return mid, welcome_url
