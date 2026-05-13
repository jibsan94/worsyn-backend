"""System metrics endpoint — real-time host + service health data."""
import time
from datetime import datetime, timezone

import httpx
import psutil
import redis as redis_lib
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import get_current_user, require_role
from app.core.config import get_settings
from app.db.session import get_db
from app.models.models import AdminUser

router = APIRouter(prefix="/admin/metrics", tags=["Metrics"])
settings = get_settings()


# ── Response schemas ──────────────────────────────────────────────────────────

class HostInfo(BaseModel):
    hostname: str
    os: str
    kernel: str
    uptime_seconds: int
    boot_time: str


class CpuInfo(BaseModel):
    percent: float
    cores_physical: int
    cores_logical: int
    freq_mhz: float | None


class RamInfo(BaseModel):
    total_gb: float
    used_gb: float
    free_gb: float
    percent: float


class DiskInfo(BaseModel):
    total_gb: float
    used_gb: float
    free_gb: float
    percent: float


class ServiceStatus(BaseModel):
    name: str
    status: str   # "ok" | "error"
    latency_ms: float


class MetricsResponse(BaseModel):
    host: HostInfo
    cpu: CpuInfo
    ram: RamInfo
    disk: DiskInfo
    services: list[ServiceStatus]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _gb(bytes_: int) -> float:
    return round(bytes_ / (1024 ** 3), 2)


async def _check_api() -> ServiceStatus:
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("http://localhost:8000/api/v1/health", timeout=3.0)
            r.raise_for_status()
        latency = round((time.perf_counter() - t0) * 1000, 2)
        return ServiceStatus(name="API", status="ok", latency_ms=latency)
    except Exception:
        return ServiceStatus(name="API", status="error", latency_ms=0)


async def _check_db(db: AsyncSession) -> ServiceStatus:
    t0 = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        latency = round((time.perf_counter() - t0) * 1000, 2)
        return ServiceStatus(name="PostgreSQL", status="ok", latency_ms=latency)
    except Exception:
        return ServiceStatus(name="PostgreSQL", status="error", latency_ms=0)


def _check_redis() -> ServiceStatus:
    t0 = time.perf_counter()
    try:
        r = redis_lib.from_url(settings.redis_url, socket_connect_timeout=2)
        r.ping()
        latency = round((time.perf_counter() - t0) * 1000, 2)
        return ServiceStatus(name="Redis", status="ok", latency_ms=latency)
    except Exception:
        return ServiceStatus(name="Redis", status="error", latency_ms=0)


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("", response_model=MetricsResponse)
async def get_metrics(
    db: AsyncSession = Depends(get_db),
    _current_user: AdminUser = Depends(get_current_user),
):
    import platform

    # Host
    boot_ts = psutil.boot_time()
    uptime_s = int(time.time() - boot_ts)
    boot_dt = datetime.fromtimestamp(boot_ts, tz=timezone.utc).isoformat()
    uname = platform.uname()
    host = HostInfo(
        hostname=uname.node,
        os=f"{uname.system} {uname.release}",
        kernel=uname.version[:80],
        uptime_seconds=uptime_s,
        boot_time=boot_dt,
    )

    # CPU — first call returns 0.0 so we use interval=0.2
    cpu_percent = psutil.cpu_percent(interval=0.2)
    freq = psutil.cpu_freq()
    cpu = CpuInfo(
        percent=cpu_percent,
        cores_physical=psutil.cpu_count(logical=False) or 1,
        cores_logical=psutil.cpu_count(logical=True) or 1,
        freq_mhz=round(freq.current, 1) if freq else None,
    )

    # RAM
    vm = psutil.virtual_memory()
    ram = RamInfo(
        total_gb=_gb(vm.total),
        used_gb=_gb(vm.used),
        free_gb=_gb(vm.available),
        percent=vm.percent,
    )

    # Disk (root partition)
    du = psutil.disk_usage("/")
    disk = DiskInfo(
        total_gb=_gb(du.total),
        used_gb=_gb(du.used),
        free_gb=_gb(du.free),
        percent=du.percent,
    )

    # Services
    api_svc = await _check_api()
    db_svc = await _check_db(db)
    redis_svc = _check_redis()

    return MetricsResponse(
        host=host,
        cpu=cpu,
        ram=ram,
        disk=disk,
        services=[api_svc, db_svc, redis_svc],
    )
