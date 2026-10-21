"""Reset a user's 2FA from the server — the last resort when no admin can.

Usage: python -m app.scripts.reset_2fa <email>
       make reset-2fa email=<email> [COMPOSE_FILE=docker-compose.yml]
"""
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models import *  # noqa: F401, F403 — register all models
from app.models.user import User
from app.services.mfa import clear_all_mfa


async def reset_2fa(session: AsyncSession, email: str) -> bool:
    """Remove every 2FA method of the user with `email` and sign them out."""
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        return False
    clear_all_mfa(user)
    user.token_version += 1
    await session.flush()
    return True


async def _main(email: str) -> int:
    async with async_session_factory() as session:
        if not await reset_2fa(session, email):
            print(f"No user with email {email}", file=sys.stderr)
            return 1
        await session.commit()
    print(f"2FA reset for {email}")
    return 0


def main() -> None:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print("Usage: python -m app.scripts.reset_2fa <email>", file=sys.stderr)
        sys.exit(2)
    sys.exit(asyncio.run(_main(sys.argv[1].strip())))


if __name__ == "__main__":
    main()
