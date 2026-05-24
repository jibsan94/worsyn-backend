import uuid
from datetime import date, datetime, time, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, Time, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utcnow():
    return datetime.now(timezone.utc)


class Organization(Base):
    """A church/customer organization (tenant).

    One organization has many OrgMembers.
    This is completely separate from AdminUser (Worsyn platform users).
    """
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    plan: Mapped[str] = mapped_column(String(50), default="free")  # free | pro | teams
    status: Mapped[str] = mapped_column(String(50), default="active")  # active | trial | suspended | cancelled
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    alias: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True, index=True)
    ministries: Mapped[list] = mapped_column(JSON, default=list)
    member_roles: Mapped[list] = mapped_column(JSON, default=list)
    icon: Mapped[str | None] = mapped_column(Text, nullable=True)
    require_2fa_admins: Mapped[bool] = mapped_column(Boolean, default=False)
    # How long received/sent email history is kept (months). Default 3, max 12 — surfaced in org settings.
    email_retention_months: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    members: Mapped[list["OrgMember"]] = relationship("OrgMember", back_populates="organization", cascade="all, delete-orphan")
    tenant: Mapped["Tenant | None"] = relationship("Tenant", back_populates="organization", uselist=False, cascade="all, delete-orphan")


class OrgMember(Base):
    """A member of a tenant organization (NOT a Worsyn platform user).

    Each member belongs to exactly one organization via org_id.
    Roles within the org: owner | admin | member | viewer
    """
    __tablename__ = "org_members"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="member")  # admin | leader | member
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    # Extended profile fields
    prefix: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)
    birthdate: Mapped[date | None] = mapped_column(Date, nullable=True)
    anniversary: Mapped[date | None] = mapped_column(Date, nullable=True)
    ministry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    org_roles: Mapped[list] = mapped_column(JSON, default=list)
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Magic-link token issued by the welcome email — see /api/v1/auth/reset-password/{token}.
    # Also reused for "forgot password" flow (Phase 3). Single active token per member.
    password_reset_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    password_reset_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="members")


class Tenant(Base):
    """Docker tenant provisioned for each organization (one-to-one)."""
    __tablename__ = "tenants"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(String(50), default="provisioning")  # provisioning | running | stopped | error
    db_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    db_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    container_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    compose_dir: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provisioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="tenant")


class AdminUser(Base):
    """Worsyn platform users with role-based access.

    Roles:
      - user:  read-only access to Principal section (Dashboard, Orgs, Users, Billing, System)
      - admin: access to Configuración (read-only on DB settings)
      - owner: full system control, can edit all settings
    """
    __tablename__ = "system_users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")  # user | admin | owner
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    two_factor_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    two_factor_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SystemSetting(Base):
    """Key-value store for system configuration."""
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class OrgRole(Base):
    """Configurable roles for org members (organization-level users).

    System roles (is_system=True) cannot be deleted but their display
    metadata (name, description, sort_order) can be updated.
    Custom roles can be freely created and deleted.
    """
    __tablename__ = "org_roles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    """Immutable record of every significant platform action."""
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_username: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resource_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), index=True
    )


# ── Tenant-scoped module tables ───────────────────────────────────────────────
# Each table FKs to organizations(id) ON DELETE CASCADE. Modules independent.

class ServiceType(Base):
    """Category/template of services. Drives the recurrence + the list of
    weekly/recurring time slots (ServiceTime) + the participating teams (ServiceTeam).

    Recurrence values: none | random | daily | weekly | weekdays | biweekly | monthly
    """
    __tablename__ = "service_types"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    recurrence: Mapped[str] = mapped_column(String(20), nullable=False, default="weekly")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ServiceTime(Base):
    """One time slot for a ServiceType. Multiple per type allowed
    (e.g. Sunday 8am + Sunday 11am, or Sunday + Saturday).
    starts_on is the first occurrence date — used to compute weekday and to project
    future occurrences according to the parent ServiceType.recurrence.
    """
    __tablename__ = "service_times"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    service_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("service_types.id", ondelete="CASCADE"), nullable=False, index=True)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())


class ServiceTeam(Base):
    """M2M between ServiceType and Team — which teams participate in this service."""
    __tablename__ = "service_teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("service_types.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())


class ServicePlan(Base):
    """Instance of a service (a specific Sunday morning, etc.)."""
    __tablename__ = "service_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    service_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("service_types.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | published | completed
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Song(Base):
    """Song library (lyrics, chords, metadata)."""
    __tablename__ = "songs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    song_key: Mapped[str | None] = mapped_column(String(10), nullable=True)
    tempo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ccli: Mapped[str | None] = mapped_column(String(50), nullable=True)
    lyrics: Mapped[str | None] = mapped_column(Text, nullable=True)
    chords: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MediaAsset(Base):
    """Multimedia files (image / video / audio / doc) per org."""
    __tablename__ = "media_assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # image | video | audio | doc
    url: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime: Mapped[str | None] = mapped_column(String(100), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())


class Team(Base):
    """A volunteer team within an org (e.g. Alabanza, Audio/Visual)."""
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class TeamMembership(Base):
    """Many-to-many between teams and org_members."""
    __tablename__ = "team_memberships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("org_members.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())


class Score(Base):
    """Sheet music / score for a song, instrument-specific."""
    __tablename__ = "scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    song_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("songs.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    score_key: Mapped[str | None] = mapped_column(String(10), nullable=True)
    instrument: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())


class Event(Base):
    """A scheduled event (camp, retreat, conference, etc.)."""
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Rehearsal(Base):
    """Practice session, optionally linked to a service plan."""
    __tablename__ = "rehearsals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    service_plan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("service_plans.id", ondelete="SET NULL"), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MemberAttachment(Base):
    """File attachment linked to an org_member (stored as base64 in DB)."""
    __tablename__ = "member_attachments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("org_members.id", ondelete="CASCADE"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)         # user-defined name
    original_name: Mapped[str] = mapped_column(String(255), nullable=False) # original filename
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    file_data: Mapped[str] = mapped_column(Text, nullable=False)            # base64-encoded content
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())


class ServiceMember(Base):
    """A member's permission profile within the Services module.

    Inspired by Planning Center. The org-level role (admin/leader/member in
    org_members.role) is separate from the service-module role here.

    service_role values: administrator | editor | coordinator | viewer | scheduled_viewer
      - administrator: full control of services module (add/edit/delete people, types, plans)
      - editor: edit services, types, plans (no delete people, no add people)
      - coordinator: coordinate plans within a type (no add/modify types, no delete plans)
      - viewer: read-only across all services
      - scheduled_viewer: read-only of *assigned* services only (assignments via teams/plans)

    songs_role / media_role: subset (administrator | editor | viewer | scheduled_viewer)
    file_access_*: download permission per area
    welcomed_at: when the welcome email was sent (manual share workflow for now)
    password_set_at: when the member set their own password (post-welcome)
    """
    __tablename__ = "service_members"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("org_members.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    service_role: Mapped[str] = mapped_column(String(30), nullable=False, default="viewer")
    songs_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    media_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    file_access_plans: Mapped[bool] = mapped_column(Boolean, default=True)
    file_access_songs: Mapped[bool] = mapped_column(Boolean, default=True)
    file_access_media: Mapped[bool] = mapped_column(Boolean, default=True)
    welcomed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_set_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Scheduling preferences — soft caps consumed by the Phase-3 scheduler/cuadrante
    # NULL = unlimited (default). Integers 1..N = upper bound.
    # Example: a member who can serve once a month even if the church has 4
    # services on Sundays → scheduling_max_per_month=1, scheduling_max_per_day=1.
    scheduling_max_per_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scheduling_max_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Email signature (used by outgoing tenant emails once SMTP is wired).
    # `signature_image` is a base64 data URL — capped at 1 MB decoded.
    signature_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    signature_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Preferred notification app: 'servicios' (default, web/mobile portal) | 'worsyn' (future)
    preferred_notif_app: Mapped[str] = mapped_column(String(20), nullable=False, default="servicios")
    # TEST-ONLY plaintext debug field — see /artifacts/CONTEXT.md "Para quitar antes de producción"
    debug_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ServiceMemberBlockout(Base):
    """Unavailability range for a ServiceMember (won't be scheduled on these days).

    `start_date` and `end_date` define the inclusive range (single-day blockouts
    have start == end). `all_day=False` is reserved for future hour-range support.

    Recurrence:
      repeat_kind     none | day | week | month | year   (none = one-off)
      repeat_interval 1..N   (Cada / Cada dos / Cada tres … → 1, 2, 3 …)
      repeat_until    DATE | NULL                        (NULL = forever)

    `reason` is optional. Projection of recurring blockouts onto a calendar
    range happens on the frontend (small enough scope) or could move to a
    dedicated endpoint later.
    """
    __tablename__ = "service_member_blockouts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    service_member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("service_members.id", ondelete="CASCADE"), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    all_day: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    repeat_kind: Mapped[str] = mapped_column(String(10), default="none", nullable=False)
    repeat_interval: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    repeat_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ServiceMemberTypePerm(Base):
    """Per-service-type override of a ServiceMember's role.

    role = NULL means *inherit* from ServiceMember.service_role (same as parent).
    Absence of a row also means inherit (default).
    """
    __tablename__ = "service_member_type_perms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("service_members.id", ondelete="CASCADE"), nullable=False, index=True)
    service_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("service_types.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str | None] = mapped_column(String(30), nullable=True)


class FinanceTransaction(Base):
    """Tithes, offerings, expenses — single ledger per org."""
    __tablename__ = "finance_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # income | expense | tithe | offering
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    occurred_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())


# ── Email (templates + message log) ───────────────────────────────────────────

class EmailTemplate(Base):
    """Per-org reusable email body.

    kind values:
      general   → General messages (no plan context)
      schedule  → Plan/Matrix-related (carry accept/decline buttons in render)
      signup    → Signup Sheets emails
      welcome   → New-member welcome
    Body uses Worsyn variable syntax: `{{ var }}` and `{% if var %}…{% else %}…{% endif %}`.
    See `artifacts/EMAIL-VARIABLES.md` for the full catalog.
    """
    __tablename__ = "email_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="general")
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("org_members.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EmailMessage(Base):
    """One email sent OR received within a tenant. Body is stored rendered
    (with variables substituted) AND the raw template body kept for audit.

    Retention: rows older than `organizations.email_retention_months` are
    eligible for cleanup. The cron is not wired yet — see TODO in
    `artifacts/CONTEXT.md` → "Para quitar antes de producción / TODOs".

    direction: 'sent' | 'received'
    status:    'queued' (SMTP not wired yet) | 'sent' | 'delivered' | 'failed' | 'received'
    """
    __tablename__ = "email_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("email_templates.id", ondelete="SET NULL"), nullable=True)
    sender_member_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("org_members.id", ondelete="SET NULL"), nullable=True, index=True)
    recipient_member_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("org_members.id", ondelete="SET NULL"), nullable=True, index=True)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False, default="sent")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    subject: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    body_rendered: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now(), index=True)
