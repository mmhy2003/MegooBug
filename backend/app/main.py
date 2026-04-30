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
        if result.scalars().first() is not None:
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

    # Meilisearch: configure indexes and bootstrap existing data
    try:
        await _init_meilisearch()
    except Exception:
        logger.exception("Failed to initialise Meilisearch — search may be unavailable")

    logger.info("%s ready to accept connections", settings.APP_NAME)
    yield

    await close_redis()
    await engine.dispose()
    logger.info("%s shut down", settings.APP_NAME)


async def _init_meilisearch():
    """Configure Meilisearch indexes and bootstrap any un-indexed data.

    Runs at startup to ensure:
    1. All indexes exist with correct filterable/sortable attributes.
    2. Existing projects and issues in PostgreSQL are indexed.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    import meilisearch

    from sqlalchemy import select
    from app.database import async_session_factory
    from app.models.project import Project
    from app.models.issue import Issue

    client = meilisearch.Client(
        settings.MEILISEARCH_URL,
        settings.MEILISEARCH_MASTER_KEY,
    )

    # ── Configure indexes (sync Meilisearch calls in executor) ──
    def _configure():
        for name in ("issues", "events", "projects"):
            try:
                client.create_index(name, {"primaryKey": "id"})
            except Exception:
                pass  # Index already exists

        client.index("issues").update_filterable_attributes(["project_id", "status", "level"])
        client.index("issues").update_sortable_attributes(["last_seen", "event_count"])
        client.index("events").update_filterable_attributes(["project_id", "issue_id"])
        client.index("events").update_sortable_attributes(["timestamp"])
        client.index("projects").update_filterable_attributes(["id"])
        client.index("projects").update_sortable_attributes(["created_at"])

    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=1) as executor:
        await loop.run_in_executor(executor, _configure)

    logger.info("Meilisearch indexes configured")

    # ── Bootstrap existing data via async DB session ──
    async with async_session_factory() as db:
        # Projects
        result = await db.execute(select(Project))
        projects = result.scalars().all()
        if projects:
            docs = [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "slug": p.slug,
                    "platform": p.platform or "",
                    "created_at": p.created_at.isoformat() if p.created_at else "",
                }
                for p in projects
            ]
            await loop.run_in_executor(
                None,
                lambda: client.index("projects").add_documents(docs, primary_key="id"),
            )
            logger.info("Bootstrapped %d projects into Meilisearch", len(docs))

        # Issues
        result = await db.execute(select(Issue))
        issues = result.scalars().all()
        if issues:
            docs = [
                {
                    "id": str(i.id),
                    "project_id": str(i.project_id),
                    "title": i.title,
                    "fingerprint": i.fingerprint,
                    "status": i.status.value,
                    "level": i.level.value,
                    "event_count": i.event_count,
                    "first_seen": i.first_seen.isoformat() if i.first_seen else "",
                    "last_seen": i.last_seen.isoformat() if i.last_seen else "",
                    "metadata": i.metadata_ or {},
                }
                for i in issues
            ]
            await loop.run_in_executor(
                None,
                lambda: client.index("issues").add_documents(docs, primary_key="id"),
            )
            logger.info("Bootstrapped %d issues into Meilisearch", len(docs))


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
