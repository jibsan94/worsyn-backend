"""Admin settings endpoints (database config, system config)."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.schemas import DatabaseConfigWrite

router = APIRouter(prefix="/admin/settings", tags=["Admin Settings"])

SUPPORTED_ENGINES = {"postgresql", "mysql", "mariadb"}


@router.get("/database")
async def get_database_config(db: AsyncSession = Depends(get_db)):
    """Return current database config (password masked)."""
    # TODO: fetch from system_settings table (key=db_*)
    return {
        "engine": "postgresql",
        "host": "db",
        "port": 5432,
        "name": "worsyn",
        "user": "worsyn_admin",
        "password": "***",
        "ssl": True,
    }


@router.post("/database")
async def save_database_config(
    payload: DatabaseConfigWrite,
    db: AsyncSession = Depends(get_db),
):
    """Persist database config. Password stored encrypted."""
    if payload.engine not in SUPPORTED_ENGINES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported engine '{payload.engine}'. Supported: {sorted(SUPPORTED_ENGINES)}",
        )
    # TODO: encrypt password and store in system_settings
    return {"status": "saved", "engine": payload.engine}


@router.post("/database/test")
async def test_database_connection(payload: DatabaseConfigWrite):
    """Test a database connection without saving."""
    if payload.engine not in SUPPORTED_ENGINES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported engine '{payload.engine}'. Supported: {sorted(SUPPORTED_ENGINES)}",
        )
    # TODO: attempt real connection with provided credentials
    return {"status": "ok", "latency_ms": 12}
