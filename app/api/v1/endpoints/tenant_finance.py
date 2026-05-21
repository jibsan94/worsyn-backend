"""Tenant module: Finance (tithes, offerings, transactions)."""
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.models.models import FinanceTransaction, Organization

router = APIRouter(prefix="/tenant/{slug}/finance", tags=["Tenant · Finance"])


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


@router.get("/transactions")
async def list_transactions(
    slug: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    org = await _auth_org(slug, authorization, tenant_access, db)
    rows = (await db.execute(
        select(FinanceTransaction).where(FinanceTransaction.org_id == org.id).order_by(FinanceTransaction.occurred_on.desc().nullslast())
    )).scalars().all()
    return [
        {
            "id": str(r.id), "amount_cents": r.amount_cents, "currency": r.currency,
            "kind": r.kind, "description": r.description, "category": r.category,
            "occurred_on": r.occurred_on.isoformat() if r.occurred_on else None,
        }
        for r in rows
    ]


@router.get("/summary")
async def finance_summary(
    slug: str,
    authorization: str | None = Header(default=None),
    tenant_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate totals per kind (income/expense/tithe/offering)."""
    org = await _auth_org(slug, authorization, tenant_access, db)
    rows = (await db.execute(
        select(FinanceTransaction).where(FinanceTransaction.org_id == org.id)
    )).scalars().all()
    totals: dict[str, int] = {}
    for r in rows:
        totals[r.kind] = totals.get(r.kind, 0) + r.amount_cents
    return {"totals_cents": totals, "currency": "EUR"}
