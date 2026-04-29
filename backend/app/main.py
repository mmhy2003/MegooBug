from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.v1 import router as api_v1_router
from app.api.ingest import router as ingest_router
from app.api.sentry_compat import router as sentry_compat_router
from app.api.websocket import router as ws_router
from app.database import engine, Base
from app.logging import setup_logging, get_logger
from app.services.pubsub import init_redis, close_redis

# Initialize logging before anything else
setup_logging()
logger = get_logger("app")


async def _auto_migrate():
    """Run Alembic migrations on startup to keep the schema up to date.

    Also ensures all tables exist via create_all as a safety net — the
    initial Alembic migration is a no-op baseline, so on a completely
    fresh database the tables wouldn't otherwise be created.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    def _run_upgrade():
        from alembic.config import Config
        from alembic import command
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")

    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=1) as executor:
        await loop.run_in_executor(executor, _run_upgrade)

    logger.info("Database migrations applied")

    # Import all models so Base.metadata knows about every table
    import app.models  # noqa: F401

    # Safety net: create any tables that migrations didn't cover
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database schema verified")


async def _auto_seed():
    """Auto-seed admin user if none exists."""
    from sqlalchemy import select
    from app.database import async_session_factory
    from app.models.user import User, UserRole
    from app.services.auth import hash_password

    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.role == UserRole.ADMIN)
        )
        if result.scalar_one_or_none() is not None:
            logger.debug("Admin user already exists, skipping seed")
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
        logger.info("Admin user seeded: %s", settings.ADMIN_EMAIL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    logger.info("%s starting up (env=%s, signup=%s)",
                settings.APP_NAME, settings.ENVIRONMENT, settings.ALLOW_SIGNUP)

    try:
        await _auto_migrate()
    except Exception:
        logger.exception("Failed to run database migrations — aborting startup")
        raise

    try:
        await _auto_seed()
    except Exception:
        logger.exception("Failed to seed admin user — aborting startup")
        raise

    try:
        await init_redis()
    except Exception:
        logger.exception("Failed to initialise Redis — aborting startup")
        raise

    logger.info("%s ready to accept connections", settings.APP_NAME)
    yield

    await close_redis()
    await engine.dispose()
    logger.info("%s shut down", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    description="Open-source real-time bug tracking platform",
    version="0.1.0",
    docs_url="/api/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/api/redoc" if settings.ENVIRONMENT == "development" else None,
    lifespan=lifespan,
    redirect_slashes=False,  # Sentry CLI expects trailing slashes
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(api_v1_router)
app.include_router(ingest_router, prefix="/api")       # Sentry ingest: /api/{project_id}/store/
app.include_router(sentry_compat_router)                # Sentry compat: /api/0/...
app.include_router(ws_router)                           # WebSocket: /ws/notifications


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "app": settings.APP_NAME}
