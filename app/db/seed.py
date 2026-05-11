"""Seed the database with the default owner user on first boot."""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.models import AdminUser


async def seed_default_owner():
    """Create the default owner user if no system_users exist."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AdminUser).limit(1))
        if result.scalar_one_or_none() is not None:
            return  # Already seeded

        owner = AdminUser(
            username="worsyn",
            email="admin@worsyn.local",
            hashed_password=hash_password("worsyn"),
            full_name="Worsyn Owner",
            role="owner",
            is_active=True,
            must_change_password=True,  # Force change on first login
        )
        session.add(owner)
        await session.commit()
        print("[SEED] Default owner user 'worsyn' created (must_change_password=True)")


if __name__ == "__main__":
    asyncio.run(seed_default_owner())
