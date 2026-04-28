"""Seed the initial admin user from environment variables.

Usage: python -m app.scripts.seed
"""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory, engine, Base
from app.logging import setup_logging, get_logger
from app.models.user import User, UserRole
from app.services.auth import hash_password

# Ensure all models are imported for table creation
from app.models import *  # noqa: F401, F403

setup_logging()
logger = get_logger("seed")


async def seed_admin():
    """Create initial admin user if none exists."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.role == UserRole.ADMIN)
        )
        existing_admin = result.scalar_one_or_none()

        if existing_admin is not None:
            logger.info("Admin already exists: %s", existing_admin.email)
            return

        admin = User(
            email=settings.ADMIN_EMAIL,
            name=settings.ADMIN_NAME,
            password_hash=hash_password(settings.ADMIN_PASSWORD),
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        logger.info("Admin user created: %s", settings.ADMIN_EMAIL)


async def main():
    logger.info("Seeding %s database...", settings.APP_NAME)

    # Create tables if they don't exist (fallback for first run)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await seed_admin()
    logger.info("Seeding complete")


if __name__ == "__main__":
    asyncio.run(main())
