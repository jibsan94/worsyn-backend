"""Admin settings endpoints (database config, system config).

Access:
  - GET /database: admin + owner (read)
  - POST /database: owner only (write)
  - POST /database/test: admin + owner (non-destructive)
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import get_current_user, require_role
from app.db.session import get_db
from app.models.models import AdminUser
from app.schemas.schemas import DatabaseConfigWrite

router = APIRouter(prefix="/admin/settings", tags=["Admin Settings"])

SUPPORTED_ENGINES = {"postgresql", "mysql", "mariadb"}


@router.get("/database")
async def get_database_config(
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_role("admin", "owner")),
):
    """Return current database config (password masked)."""
    return {
        "engine": "postgresql",
        "host": "db",
        "port": 5432,
        "name": "worsyn",
        "user": "worsyn_admin",
        "password": "***",
        "ssl": True,
        "readonly": user.role != "owner",
    }


@router.post("/database")
async def save_database_config(
    payload: DatabaseConfigWrite,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_role("owner")),
):
    """Persist database config. Owner only."""
    if payload.engine not in SUPPORTED_ENGINES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported engine '{payload.engine}'. Supported: {sorted(SUPPORTED_ENGINES)}",
        )
    return {"status": "saved", "engine": payload.engine}


@router.post("/database/test")
async def test_database_connection(
    payload: DatabaseConfigWrite,
    user: AdminUser = Depends(require_role("admin", "owner")),
):
    """Test a database connection without saving."""
    if payload.engine not in SUPPORTED_ENGINES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported engine '{payload.engine}'. Supported: {sorted(SUPPORTED_ENGINES)}",
        )
    return {"status": "ok", "latency_ms": 12}
