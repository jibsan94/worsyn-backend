"""Admin user management endpoints.

Access matrix:
  - GET  /admin/users          admin + owner  (list all)
  - POST /admin/users          admin + owner  (create)
  - GET  /admin/users/{id}     admin + owner  (detail)
  - PUT  /admin/users/{id}     admin + owner  (edit — admin cannot touch owners)
  - DELETE /admin/users/{id}   admin + owner  (delete — admin cannot delete owners)

Rule: an 'admin' can never delete or modify an 'owner' user.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import get_current_user, require_role
from app.core.security import hash_password
from app.db.session import get_db
from app.models.models import AdminUser
from app.schemas.schemas import AdminUserAvatarUpdate, AdminUserCreate, AdminUserRead, AdminUserUpdate

router = APIRouter(prefix="/admin/users", tags=["Admin User Management"])


# ── helpers ───────────────────────────────────────────────────────────────────

async def _get_or_404(db: AsyncSession, user_id: uuid.UUID) -> AdminUser:
    result = await db.get(AdminUser, user_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return result


def _guard_owner_target(actor: AdminUser, target: AdminUser) -> None:
    """Raise 403 if an admin tries to act on an owner."""
    if actor.role == "admin" and target.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot modify or delete owner accounts",
        )


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[AdminUserRead])
async def list_admin_users(
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(require_role("admin", "owner")),
):
    """Return all platform users. Admins see all but cannot mutate owners."""
    result = await db.execute(select(AdminUser).order_by(AdminUser.created_at))
    return result.scalars().all()


@router.post("", response_model=AdminUserRead, status_code=status.HTTP_201_CREATED)
async def create_admin_user(
    payload: AdminUserCreate,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(require_role("admin", "owner")),
):
    """Create a new platform user.

    An admin can only create users with role 'user' or 'admin', not 'owner'.
    """
    if actor.role == "admin" and payload.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot create owner accounts",
        )

    # Check uniqueness
    dup_username = await db.execute(
        select(AdminUser).where(AdminUser.username == payload.username)
    )
    if dup_username.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")

    dup_email = await db.execute(
        select(AdminUser).where(AdminUser.email == payload.email)
    )
    if dup_email.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    new_user = AdminUser(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        must_change_password=True,  # always force on first login
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


@router.get("/{user_id}", response_model=AdminUserRead)
async def get_admin_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(require_role("admin", "owner")),
):
    return await _get_or_404(db, user_id)


@router.put("/{user_id}", response_model=AdminUserRead)
async def update_admin_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(require_role("admin", "owner")),
):
    """Edit a platform user. Admin cannot modify owner accounts."""
    target = await _get_or_404(db, user_id)
    _guard_owner_target(actor, target)

    # Admin cannot promote someone to owner
    if actor.role == "admin" and payload.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot assign the owner role",
        )

    # Check username uniqueness if changing
    if payload.username is not None and payload.username != target.username:
        dup = await db.execute(
            select(AdminUser).where(AdminUser.username == payload.username)
        )
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")
        target.username = payload.username

    if payload.email is not None:
        dup = await db.execute(
            select(AdminUser).where(AdminUser.email == payload.email)
        )
        existing = dup.scalar_one_or_none()
        if existing and existing.id != target.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        target.email = payload.email

    if payload.full_name is not None:
        target.full_name = payload.full_name

    if payload.role is not None:
        target.role = payload.role

    if payload.is_active is not None:
        target.is_active = payload.is_active

    if payload.password is not None:
        target.hashed_password = hash_password(payload.password)
        target.must_change_password = True

    # Only owner can change 2FA status of another user
    if payload.two_factor_enabled is not None:
        if actor.role != "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only owners can modify another user's 2FA status",
            )
        target.two_factor_enabled = payload.two_factor_enabled

    await db.commit()
    await db.refresh(target)
    return target


@router.put("/{user_id}/avatar", response_model=AdminUserRead)
async def update_avatar(
    user_id: uuid.UUID,
    payload: AdminUserAvatarUpdate,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(get_current_user),
):
    """Update (or remove) a user's avatar. Any user can update their own; admin/owner can update others."""
    target = await _get_or_404(db, user_id)

    if actor.id != target.id:
        if actor.role not in ("admin", "owner"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        _guard_owner_target(actor, target)

    if payload.avatar is not None and len(payload.avatar) > 13_631_489:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Avatar too large (max 10 MB)")

    target.avatar = payload.avatar
    await db.commit()
    await db.refresh(target)
    return target


@router.delete("/{user_id}/2fa", status_code=status.HTTP_204_NO_CONTENT)
async def reset_2fa(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(require_role("owner")),
):
    """Reset (disable) 2FA for a user. Owner only."""
    target = await _get_or_404(db, user_id)
    target.two_factor_enabled = False
    await db.commit()


@router.put("/{user_id}/2fa", response_model=AdminUserRead)
async def toggle_own_2fa(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(get_current_user),
):
    """Toggle 2FA on/off for own account. Any authenticated user can manage their own."""
    target = await _get_or_404(db, user_id)
    if actor.id != target.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only manage your own 2FA",
        )
    target.two_factor_enabled = not target.two_factor_enabled
    await db.commit()
    await db.refresh(target)
    return target


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(require_role("admin", "owner")),
):
    """Delete a platform user. Admin cannot delete owner accounts."""
    target = await _get_or_404(db, user_id)
    _guard_owner_target(actor, target)

    # Prevent self-deletion
    if target.id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    await db.delete(target)
    await db.commit()
