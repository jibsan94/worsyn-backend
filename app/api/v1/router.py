"""V1 API router — aggregates all endpoint routers."""
from fastapi import APIRouter

from app.api.v1.endpoints import health, organizations, settings

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(organizations.router)
api_router.include_router(settings.router)
