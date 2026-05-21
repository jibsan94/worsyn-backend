"""Tenant module: Member attachments.

Endpoints scoped to /tenant/{slug}/members/{member_id}/attachments.
Files stored as base64 in the DB. Max 10 MB per file.
Access: admin or leader role only (upload, download, delete). Members can list.
"""
import base64
import uuid

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, UploadFile, File, Form, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.models.models import MemberAttachment, OrgMember, Organization

router = APIRouter(
    prefix="/tenant/{slug}/members/{member_id}/attachments",
    tags=["Tenant · Member Attachments"],
)

MAX_BYTES = 10 * 1024 * 1024  # 10 MB


async def _auth_org(slug: str, authorization: str | None, cookie: str | None, db: AsyncSession):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else cookie
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    data = decode_token(token)
    if data.get("type") != "tenant_access" or data.get("org_slug") != slug:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    org = (await db.execute(select(Organization).where(Organization.slug == slug))).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Org no encontrada")
    caller_id = data.get("sub")
    # Impersonation: admin Worsyn entra como admin sintético
    if data.get("impersonating"):
        return org, caller_id, "admin"
    # Role real desde BD (no del JWT — puede haber cambiado)
    caller = (await db.execute(
        select(OrgMember).where(OrgMember.id == uuid.UUID(caller_id), OrgMember.org_id == org.id)
    )).scalar_one_or_none()
    if caller is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Miembro no encontrado")
    return org, caller_id, caller.role


def _require_priv(caller_role: str):
    if caller_role not in ("admin", "leader"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo administradores y líderes")


async def _get_member(member_id: str, org_id: uuid.UUID, db: AsyncSession) -> OrgMember:
    try:
        mid = uuid.UUID(member_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de miembro inválido")
    row = (await db.execute(
        select(OrgMember).where(OrgMember.id == mid, OrgMember.org_id == org_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Miembro no encontrado")
    return row


@router.get("")
async def list_attachments(
    slug: str, member_id: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, _, _ = await _auth_org(slug, authorization, tenant_access, db)
    await _get_member(member_id, org.id, db)
    rows = (await db.execute(
        select(MemberAttachment)
        .where(MemberAttachment.member_id == uuid.UUID(member_id), MemberAttachment.org_id == org.id)
        .order_by(MemberAttachment.uploaded_at.desc())
    )).scalars().all()
    return [
        {
            "id": str(r.id), "label": r.label, "original_name": r.original_name,
            "mime_type": r.mime_type, "size_bytes": r.size_bytes,
            "uploaded_at": r.uploaded_at.isoformat(),
        }
        for r in rows
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    slug: str, member_id: str,
    file: UploadFile = File(...),
    label: str = Form(...),
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, _, caller_role = await _auth_org(slug, authorization, tenant_access, db)
    _require_priv(caller_role)
    await _get_member(member_id, org.id, db)

    raw = await file.read()
    if len(raw) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="Archivo demasiado grande (máx. 10 MB)")

    label = label.strip()
    if not label:
        raise HTTPException(status_code=400, detail="La etiqueta es obligatoria")

    b64 = base64.b64encode(raw).decode("ascii")
    att = MemberAttachment(
        org_id=org.id,
        member_id=uuid.UUID(member_id),
        label=label,
        original_name=file.filename or "archivo",
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=len(raw),
        file_data=b64,
    )
    db.add(att)
    await db.flush()
    await db.refresh(att)
    return {
        "id": str(att.id), "label": att.label, "original_name": att.original_name,
        "mime_type": att.mime_type, "size_bytes": att.size_bytes,
        "uploaded_at": att.uploaded_at.isoformat(),
    }


@router.get("/{att_id}/data")
async def get_attachment_data(
    slug: str, member_id: str, att_id: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Returns base64 file_data + mime_type for preview/download. Admin/leader only."""
    org, _, caller_role = await _auth_org(slug, authorization, tenant_access, db)
    _require_priv(caller_role)
    try:
        aid = uuid.UUID(att_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID inválido")
    row = (await db.execute(
        select(MemberAttachment).where(
            MemberAttachment.id == aid,
            MemberAttachment.member_id == uuid.UUID(member_id),
            MemberAttachment.org_id == org.id,
        )
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Adjunto no encontrado")
    return {
        "id": str(row.id), "label": row.label, "original_name": row.original_name,
        "mime_type": row.mime_type, "size_bytes": row.size_bytes,
        "file_data": row.file_data,
        "uploaded_at": row.uploaded_at.isoformat(),
    }


@router.patch("/{att_id}")
async def rename_attachment(
    slug: str, member_id: str, att_id: str,
    body: dict,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, _, caller_role = await _auth_org(slug, authorization, tenant_access, db)
    _require_priv(caller_role)
    label = (body.get("label") or "").strip()
    if not label:
        raise HTTPException(status_code=400, detail="La etiqueta es obligatoria")
    try:
        aid = uuid.UUID(att_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID inválido")
    row = (await db.execute(
        select(MemberAttachment).where(
            MemberAttachment.id == aid,
            MemberAttachment.member_id == uuid.UUID(member_id),
            MemberAttachment.org_id == org.id,
        )
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Adjunto no encontrado")
    row.label = label
    await db.flush()
    return {"id": str(row.id), "label": row.label}


@router.delete("/{att_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    slug: str, member_id: str, att_id: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org, _, caller_role = await _auth_org(slug, authorization, tenant_access, db)
    _require_priv(caller_role)
    try:
        aid = uuid.UUID(att_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID inválido")
    row = (await db.execute(
        select(MemberAttachment).where(
            MemberAttachment.id == aid,
            MemberAttachment.member_id == uuid.UUID(member_id),
            MemberAttachment.org_id == org.id,
        )
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Adjunto no encontrado")
    await db.delete(row)
