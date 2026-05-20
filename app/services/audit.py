"""Audit logging utility — appends to the current DB session, caller commits."""
import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AdminUser, AuditLog


async def log_action(
    db: AsyncSession,
    actor: "AdminUser | None",
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    resource_name: str | None = None,
    details: dict | None = None,
) -> None:
    db.add(AuditLog(
        actor_id=actor.id if actor else None,
        actor_username=actor.username if actor else "system",
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
        resource_name=resource_name,
        details=json.dumps(details, ensure_ascii=False) if details else None,
    ))
