from typing import Literal
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


# ── Organization ──────────────────────────────────────────────────────────────

class OrganizationBase(BaseModel):
    name: str
    slug: str
    plan: str = "free"
    status: str = "active"


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    name: str | None = None
    plan: str | None = None
    status: str | None = None


class OrganizationRead(OrganizationBase):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ── User ──────────────────────────────────────────────────────────────────────

class UserBase(BaseModel):
    email: EmailStr
    full_name: str | None = None
    role: str = "member"


class UserCreate(UserBase):
    password: str
    org_id: uuid.UUID

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserRead(UserBase):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    org_id: uuid.UUID
    is_active: bool
    created_at: datetime


# ── Auth ──────────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ── Admin ─────────────────────────────────────────────────────────────────────

class AdminUserRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    email: str
    full_name: str | None
    is_superadmin: bool
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


# ── Settings ──────────────────────────────────────────────────────────────────

class DatabaseConfigWrite(BaseModel):
    engine: Literal["postgresql", "mysql", "mariadb"]
    host: str
    port: int
    name: str
    user: str
    password: str


class HealthResponse(BaseModel):
    status: str
    version: str
    db: str
