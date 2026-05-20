"""Audit log endpoint — owner-only system audit trail."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func as sqlfunc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import require_role
from app.db.session import get_db
from app.models.models import AdminUser, AuditLog
from app.schemas.schemas import AuditLogRead

router = APIRouter(prefix="/admin/logs", tags=["Audit Logs"])


@router.get("", response_model=list[AuditLogRead])
async def list_audit_logs(
    page: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    action: str | None = Query(None),
    resource_type: str | None = Query(None),
    actor_username: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_role("owner")),
):
    """Return audit logs in reverse chronological order. Owner only."""
    query = select(AuditLog).order_by(desc(AuditLog.created_at))
    if action:
        query = query.where(AuditLog.action == action)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if actor_username:
        query = query.where(AuditLog.actor_username.ilike(f"%{actor_username}%"))
    query = query.offset(page * limit).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/count")
async def count_audit_logs(
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_role("owner")),
):
    result = await db.execute(select(sqlfunc.count()).select_from(AuditLog))
    return {"total": result.scalar()}
