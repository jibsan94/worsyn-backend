"""Tenant module: Songs library."""
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.models.models import Organization, Song

router = APIRouter(prefix="/tenant/{slug}/songs", tags=["Tenant · Songs"])


async def _auth_org(slug: str, authorization: str | None, cookie: str | None, db: AsyncSession) -> Organization:
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
async def list_songs(
    slug: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org = await _auth_org(slug, authorization, tenant_access, db)
    rows = (await db.execute(
        select(Song).where(Song.org_id == org.id).order_by(Song.title)
    )).scalars().all()
    return [
        {
            "id": str(r.id), "title": r.title, "author": r.author, "key": r.song_key,
            "tempo": r.tempo, "ccli": r.ccli, "tags": r.tags or [],
        }
        for r in rows
    ]
