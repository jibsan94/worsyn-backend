from typing import Literal
import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


# ── Tenant ────────────────────────────────────────────────────────────────────

class TenantRead(BaseModel):
    model_config = {"from_attributes": True}

    org_id: uuid.UUID
    status: str
    db_port: int | None = None
    container_name: str | None = None
    compose_dir: str | None = None
    provisioned_at: datetime | None = None
    error_msg: str | None = None
    updated_at: datetime


# ── Organization ──────────────────────────────────────────────────────────────

OrgPlan   = Literal["free", "pro", "teams"]
OrgStatus = Literal["active", "trial", "suspended", "cancelled"]


class OrganizationBase(BaseModel):
    name: str
    slug: str
    plan: OrgPlan = "free"
    status: OrgStatus = "active"
    country: str | None = None
    city: str | None = None
    phone: str | None = None
    website: str | None = None
    email: str | None = None
    alias: str | None = None


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    name: str | None = None
    plan: OrgPlan | None = None
    status: OrgStatus | None = None
    country: str | None = None
    city: str | None = None
    phone: str | None = None
    website: str | None = None
    email: str | None = None
    alias: str | None = None


class OrganizationRead(OrganizationBase):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    member_count: int = 0  # populated by the endpoint


# ── OrgMember (tenant user — belongs to one organization) ────────────────────

OrgMemberRole = Literal["admin", "leader", "member"]


class OrgMemberBase(BaseModel):
    email: str
    full_name: str | None = None
    phone: str | None = None
    role: OrgMemberRole = "member"

    @field_validator("email")
    @classmethod
    def email_has_at(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("Invalid email address")
        return v.lower()


class OrgMemberCreate(OrgMemberBase):
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class OrgMemberUpdate(BaseModel):
    email: str | None = None
    full_name: str | None = None
    phone: str | None = None
    role: OrgMemberRole | None = None
    is_active: bool | None = None
    password: str | None = None

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str | None) -> str | None:
        if v is not None and len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class OrgMemberRead(OrgMemberBase):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    org_id: uuid.UUID
    is_active: bool
    joined_at: datetime
    updated_at: datetime


class OrgMemberWithOrg(OrgMemberRead):
    """OrgMemberRead extended with parent org info — used by global /members/ endpoint."""
    org_name: str | None = None
    org_slug: str | None = None


# ── OrgRole ───────────────────────────────────────────────────────────────────

class OrgRoleBase(BaseModel):
    name: str
    description: str | None = None
    sort_order: int = 0


class OrgRoleCreate(OrgRoleBase):
    slug: str

    @field_validator("slug")
    @classmethod
    def slug_valid(cls, v: str) -> str:
        import re
        if not re.match(r'^[a-z0-9_-]+$', v):
            raise ValueError("Slug must contain only lowercase letters, numbers, hyphens and underscores")
        return v


class OrgRoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    sort_order: int | None = None


class OrgRoleRead(OrgRoleBase):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    slug: str
    is_system: bool
    created_at: datetime
    updated_at: datetime
    member_count: int = 0  # populated by the endpoint


# ── Admin ─────────────────────────────────────────────────────────────────────

AdminUserRole = Literal["user", "admin", "owner"]


class AdminUserRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    username: str
    email: str
    full_name: str | None
    role: AdminUserRole
    is_active: bool
    must_change_password: bool
    two_factor_enabled: bool
    avatar: str | None = None
    created_at: datetime
    last_login_at: datetime | None


class AdminUserAvatarUpdate(BaseModel):
    avatar: str | None  # base64 data URL or None to remove


class AdminUserCreate(BaseModel):
    username: str
    email: str  # plain str — internal .local domains are valid for platform users
    password: str
    full_name: str | None = None
    role: AdminUserRole = "user"

    @field_validator("email")
    @classmethod
    def email_has_at(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email address")
        return v.lower()

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("username")
    @classmethod
    def username_no_spaces(cls, v: str) -> str:
        if " " in v:
            raise ValueError("Username must not contain spaces")
        return v.lower()


class AdminUserUpdate(BaseModel):
    username: str | None = None
    email: str | None = None  # plain str — internal .local domains are valid
    full_name: str | None = None
    role: AdminUserRole | None = None
    is_active: bool | None = None
    password: str | None = None
    two_factor_enabled: bool | None = None  # owner-only field

    @field_validator("email")
    @classmethod
    def email_has_at(cls, v: str | None) -> str | None:
        if v is not None and ("@" not in v or "." not in v.split("@")[-1]):
            raise ValueError("Invalid email address")
        return v.lower() if v else v

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str | None) -> str | None:
        if v is not None and len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


# ── Settings ──────────────────────────────────────────────────────────────────

class DatabaseConfigWrite(BaseModel):
    engine: Literal["postgresql", "mysql", "mariadb"]
    host: str
    port: int
    name: str
    user: str
    password: str


class SecurityConfigRead(BaseModel):
    password_min_length: int = 8
    password_require_uppercase: bool = False
    password_require_numbers: bool = False
    password_require_special: bool = False
    password_max_age_days: int = 0
    session_access_token_minutes: int = 30
    session_refresh_token_days: int = 7
    max_sessions_per_user: int = 0
    require_2fa: bool = False
    # SSO / Active Directory — pending implementation
    sso_enabled: bool = False
    sso_provider: str = "ldap"
    sso_ad_server: str = ""
    sso_ad_base_dn: str = ""
    sso_ad_bind_dn: str = ""
    sso_ad_domain: str = ""
    sso_ad_user_filter: str = "(sAMAccountName={username})"
    readonly: bool = False


class SecurityConfigWrite(BaseModel):
    password_min_length: int = 8
    password_require_uppercase: bool = False
    password_require_numbers: bool = False
    password_require_special: bool = False
    password_max_age_days: int = 0
    session_access_token_minutes: int = 30
    session_refresh_token_days: int = 7
    max_sessions_per_user: int = 0
    require_2fa: bool = False
    # SSO / Active Directory
    sso_enabled: bool = False
    sso_provider: str = "ldap"
    sso_ad_server: str = ""
    sso_ad_base_dn: str = ""
    sso_ad_bind_dn: str = ""
    sso_ad_bind_password: str = ""  # stored plain — encrypt before production
    sso_ad_domain: str = ""
    sso_ad_user_filter: str = "(sAMAccountName={username})"


class GeneralConfigRead(BaseModel):
    platform_name: str = "Worsyn"
    support_email: str = ""
    timezone: str = "UTC"
    maintenance_mode: bool = False
    maintenance_message: str = "El sistema está en mantenimiento. Vuelve pronto."
    readonly: bool = False


class GeneralConfigWrite(BaseModel):
    platform_name: str = "Worsyn"
    support_email: str = ""
    timezone: str = "UTC"
    maintenance_mode: bool = False
    maintenance_message: str = ""


class HealthResponse(BaseModel):
    status: str
    version: str
    db: str
