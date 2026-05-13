"""V1 API router — aggregates all endpoint routers."""
from fastapi import APIRouter

from app.api.v1.endpoints import admin_users, auth, health, members, metrics, org_members, org_roles, organizations, settings

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(health.router)
api_router.include_router(organizations.router)
api_router.include_router(org_members.router)
api_router.include_router(members.router)
api_router.include_router(org_roles.router)
api_router.include_router(settings.router)
api_router.include_router(admin_users.router)
api_router.include_router(metrics.router)
