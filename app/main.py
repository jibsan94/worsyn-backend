from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: run migrations + seed
    from app.db.session import engine, Base
    import app.models.models  # noqa: F401 — ensure all models are imported
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    from app.db.seed import seed_default_owner
    await seed_default_owner()
    yield
    # Shutdown: close db engine
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")
