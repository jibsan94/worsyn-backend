"""V1 API router — aggregates all endpoint routers.

Each tenant module is independent — owns its own file + DB tables.
If a module needs maintenance, comment its include line to disable it
without affecting the rest of the system.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin_users, auth, health, logs, members, metrics, org_members, org_roles,
    organizations, settings, tenant_portal,
    # Tenant modules — independent, scoped per slug
    tenant_calendar, tenant_events, tenant_finance, tenant_media, tenant_member_attachments,
    tenant_rehearsals, tenant_scores, tenant_service_blockouts, tenant_service_people, tenant_services, tenant_songs, tenant_teams,
)

api_router = APIRouter()

# Platform / admin panel
api_router.include_router(auth.router)
api_router.include_router(health.router)
api_router.include_router(organizations.router)
api_router.include_router(org_members.router)
api_router.include_router(members.router)
api_router.include_router(org_roles.router)
api_router.include_router(settings.router)
api_router.include_router(admin_users.router)
api_router.include_router(metrics.router)
api_router.include_router(logs.router)

# Tenant portal — auth + cross-module (login, switch, settings, profile, members)
api_router.include_router(tenant_portal.router)

# Tenant modules — disable any line below to put that module in maintenance
api_router.include_router(tenant_services.router)
api_router.include_router(tenant_service_people.router)
api_router.include_router(tenant_service_blockouts.router)
api_router.include_router(tenant_songs.router)
api_router.include_router(tenant_media.router)
api_router.include_router(tenant_teams.router)
api_router.include_router(tenant_scores.router)
api_router.include_router(tenant_events.router)
api_router.include_router(tenant_rehearsals.router)
api_router.include_router(tenant_calendar.router)
api_router.include_router(tenant_finance.router)
api_router.include_router(tenant_member_attachments.router)
