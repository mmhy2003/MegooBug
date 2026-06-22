# Protecting Reads from Ingest Load — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the dashboard and read APIs responsive during ingest storms on a single server by removing read-side contention on Postgres — without changing the message broker.

**Architecture:** Four independent levers from the approved spec ([2026-06-22-ingest-read-protection-design.md](../specs/2026-06-22-ingest-read-protection-design.md)): (1) add the missing indexes behind the dashboard's aggregate queries, (2) cache the dashboard/trends aggregates in Redis with a short TTL, (3) bound the ingest worker's drain rate so it leaves Postgres headroom, and (4) budget connection pools and add docker resource limits so ingest can't crowd out the web tier. No new services, no broker change.

**Tech Stack:** FastAPI (async), SQLAlchemy 2.0 (asyncpg), Alembic, Celery (Redis broker), `redis.asyncio`, Postgres 16, pytest + pytest-asyncio, Docker Compose v2.

## Global Constraints

- **Single server, no new services.** No RabbitMQ/Kafka, no PgBouncer, no read replica. (Spec "Decision" + "Out of scope".)
- **Caching must fail open.** Any Redis error in a cache helper behaves as a miss (get) or a no-op (set) and is logged at `warning` — it must never raise or block a request. (Spec §2.)
- **Preserve RBAC in cache keys.** A cached stats payload must never be served across project scopes; the dashboard cache key is derived from the caller's project scope, and the trends access check runs *before* any cache lookup. (Spec §2.)
- **Run tests inside the backend container:** `docker compose -f docker-compose.dev.yml exec backend pytest ...` (the `Makefile` `test-be` target). The dev stack must be up (`make dev`). The test suite builds its DB from `Base.metadata.create_all` against a throwaway `megoobug_test` database (see `backend/tests/conftest.py`).
- **Schema is declared in BOTH places.** This codebase declares indexes on the SQLAlchemy models (source of truth for `create_all`, used by tests and by the startup safety net in `app/main.py`) AND mirrors them in an Alembic migration (used for existing prod DBs). New indexes must be added to both. (Convention: see `ix_events_timestamp` on `Event.timestamp` + migration `e5f6a7b8c9d0`.)
- **Current Alembic head is `e5f6a7b8c9d0`** — the new migration's `down_revision` is `e5f6a7b8c9d0`.
- **Settings live in `app/config.py`** (`pydantic-settings`, `case_sensitive=True`) and are documented in `.env.example`.
- **Default ingest rate limit is OFF** (`INGEST_RATE_LIMIT` unset = no cap), per the approved spec.

---

### Task 1: New configuration settings

Adds the five settings the later tasks consume. Doing this first means every other task can read its knobs from `settings`.

**Files:**
- Modify: `backend/app/config.py` (add fields in the existing sectioned `Settings` class)
- Modify: `.env.example` (document the new vars)
- Test: `backend/tests/test_config_settings.py` (create)

**Interfaces:**
- Produces: `settings.STATS_CACHE_TTL: int` (default `30`), `settings.INGEST_CONCURRENCY: int` (default `4`), `settings.INGEST_RATE_LIMIT: Optional[str]` (default `None`), `settings.DB_POOL_SIZE: int` (default `10`), `settings.DB_MAX_OVERFLOW: int` (default `5`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_config_settings.py`:

```python
"""The new read-protection / ingest-throttle settings expose the right defaults."""


def test_read_protection_settings_defaults():
    from app.config import Settings

    f = Settings.model_fields
    assert f["STATS_CACHE_TTL"].default == 30
    assert f["INGEST_CONCURRENCY"].default == 4
    assert f["INGEST_RATE_LIMIT"].default is None
    assert f["DB_POOL_SIZE"].default == 10
    assert f["DB_MAX_OVERFLOW"].default == 5
```

(Asserting on `model_fields[...].default` checks the *declared* defaults regardless of any values present in the container's `.env`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f docker-compose.dev.yml exec backend pytest tests/test_config_settings.py -v`
Expected: FAIL with `KeyError: 'STATS_CACHE_TTL'`.

- [ ] **Step 3: Add the settings**

In `backend/app/config.py`, extend the existing `# ── Ingestion ──` block and add a `# ── Database pool ──` and `# ── Stats cache ──` block. The class already imports `Optional`.

```python
    # ── Ingestion ──
    # Reject decompressed event payloads larger than this (bytes).
    MAX_EVENT_BYTES: int = 1_048_576
    # Return 429 when the Redis ingest queue is deeper than this.
    INGEST_QUEUE_MAX: int = 50_000
    # Prefork concurrency for the celery-ingest worker.
    INGEST_CONCURRENCY: int = 4
    # Optional Celery per-worker rate limit for ingest_event (e.g. "200/s").
    # Unset = no cap; the queue + INGEST_QUEUE_MAX backpressure absorb bursts.
    INGEST_RATE_LIMIT: Optional[str] = None

    # ── Database pool (per process) ──
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 5

    # ── Stats cache ──
    # Seconds to cache dashboard aggregate results in Redis. The dashboard
    # layers live deltas on top via the stats_update websocket, so a short
    # stale base is invisible while removing repeated heavy counts from Postgres.
    STATS_CACHE_TTL: int = 30
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f docker-compose.dev.yml exec backend pytest tests/test_config_settings.py -v`
Expected: PASS.

- [ ] **Step 5: Document the new vars in `.env.example`**

In `.env.example`, replace the `# ── Ingestion ──` block with the version below and add the two new blocks after it:

```env
# ── Ingestion ──
# Reject decompressed event payloads larger than this (bytes).
MAX_EVENT_BYTES=1048576
# Return 429 when the Redis ingest queue is deeper than this.
INGEST_QUEUE_MAX=50000
# Uvicorn worker processes for the production backend container.
UVICORN_WORKERS=2
# Prefork concurrency for the celery-ingest worker.
INGEST_CONCURRENCY=4
# Optional Celery rate limit for ingest_event, e.g. "200/s". Empty = no cap.
INGEST_RATE_LIMIT=

# ── Database pool (per process) ──
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=5

# ── Stats cache ──
# Seconds to cache dashboard aggregate results in Redis.
STATS_CACHE_TTL=30
```

(The `UVICORN_WORKERS=2` line already exists in `.env.example` — keep a single copy; the block above folds it in.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/tests/test_config_settings.py .env.example
git commit -m "feat(config): add stats-cache, ingest-throttle, and db-pool settings"
```

---

### Task 2: Performance indexes for dashboard aggregates

Adds the three indexes behind the hot read queries, declared on the models (so `create_all`/tests get them) and mirrored in an Alembic migration (so existing prod DBs get them without a long write-lock).

**Deviation from spec (deliberate):** the spec proposed a *partial* index `ON issues(project_id) WHERE status = 'unresolved'`. `IssueStatus` is a SQLAlchemy `Enum(IssueStatus)` whose stored label is the member *name*, making a hand-written `WHERE status = '...'` literal fragile. We instead use a plain composite `(project_id, status)` index (no predicate literal). It serves the project-scoped unresolved count *and* the project issues-list filter (`app/api/v1/issues.py` filters `project_id == X AND status == ...`); the admin-wide unresolved count is now a cold path (cached), so the non-partial index is the robust choice.

**Files:**
- Modify: `backend/app/models/event.py` (add `index=True` to `received_at`; add `__table_args__`)
- Modify: `backend/app/models/issue.py` (append an `Index` to the existing `__table_args__`)
- Create: `backend/alembic/versions/f6a7b8c9d0e1_add_dashboard_read_indexes.py`
- Test: `backend/tests/test_read_indexes.py` (create)

**Interfaces:**
- Produces (index names, relied on by the test and the migration): `ix_events_received_at`, `ix_events_project_received_at`, `ix_issues_project_status`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_read_indexes.py`:

```python
"""The dashboard read indexes are present in the schema built from the models."""
import pytest
from sqlalchemy import text

EXPECTED = {
    "ix_events_received_at",
    "ix_events_project_received_at",
    "ix_issues_project_status",
}


async def test_dashboard_read_indexes_exist(db):
    rows = (await db.execute(text(
        "SELECT indexname FROM pg_indexes "
        "WHERE tablename IN ('events', 'issues')"
    ))).scalars().all()
    missing = EXPECTED - set(rows)
    assert not missing, f"missing indexes: {missing}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f docker-compose.dev.yml exec backend pytest tests/test_read_indexes.py -v`
Expected: FAIL — `missing indexes: {...}` (the `db_engine` fixture rebuilds `megoobug_test` from the current models, which don't yet declare these indexes).

- [ ] **Step 3: Declare the indexes on the models**

In `backend/app/models/event.py`, add the `Index` import, mark `received_at` indexed, and add `__table_args__` for the composite. The full file:

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_project_received_at", "project_id", "received_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    # Relationships
    issue = relationship("Issue", back_populates="events")
    project = relationship("Project", back_populates="events")

    def __repr__(self) -> str:
        return f"<Event {self.event_id}>"
```

In `backend/app/models/issue.py`, add `Index` to the `sqlalchemy` import and append it to the existing `__table_args__` tuple:

```python
from sqlalchemy import String, Integer, DateTime, ForeignKey, Enum, UniqueConstraint, Sequence, Index
```

```python
    __table_args__ = (
        UniqueConstraint("fingerprint", "project_id", name="uq_issues_fingerprint_project"),
        Index("ix_issues_project_status", "project_id", "status"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f docker-compose.dev.yml exec backend pytest tests/test_read_indexes.py -v`
Expected: PASS (the session-scoped `db_engine` rebuilds the test DB from the updated models).

- [ ] **Step 5: Write the Alembic migration (mirror for existing prod DBs)**

Create `backend/alembic/versions/f6a7b8c9d0e1_add_dashboard_read_indexes.py`:

```python
"""Add indexes behind the dashboard aggregate read queries.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-22

Built CONCURRENTLY (inside an autocommit block) so a large existing `events`
table is not write-locked during deploy. `if_not_exists` keeps this idempotent
alongside the create_all safety net in app/main.py, which builds the same
indexes from model metadata.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            'ix_events_received_at', 'events', ['received_at'],
            postgresql_concurrently=True, if_not_exists=True,
        )
        op.create_index(
            'ix_events_project_received_at', 'events', ['project_id', 'received_at'],
            postgresql_concurrently=True, if_not_exists=True,
        )
        op.create_index(
            'ix_issues_project_status', 'issues', ['project_id', 'status'],
            postgresql_concurrently=True, if_not_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            'ix_issues_project_status', table_name='issues',
            postgresql_concurrently=True, if_exists=True,
        )
        op.drop_index(
            'ix_events_project_received_at', table_name='events',
            postgresql_concurrently=True, if_exists=True,
        )
        op.drop_index(
            'ix_events_received_at', table_name='events',
            postgresql_concurrently=True, if_exists=True,
        )
```

- [ ] **Step 6: Verify the migration applies cleanly against the dev DB**

Run: `docker compose -f docker-compose.dev.yml exec backend alembic upgrade head`
Expected: completes without error; `alembic current` shows `f6a7b8c9d0e1`. (The dev `events`/`issues` tables already exist, so the CONCURRENTLY builds succeed; re-running is a no-op thanks to `if_not_exists`.)

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/event.py backend/app/models/issue.py backend/alembic/versions/f6a7b8c9d0e1_add_dashboard_read_indexes.py backend/tests/test_read_indexes.py
git commit -m "feat(db): add indexes behind dashboard aggregate queries"
```

---

### Task 3: Redis JSON cache helpers

Adds the small fail-open cache primitives the stats endpoints use, reusing the existing async Redis pool in `pubsub.py`.

**Files:**
- Modify: `backend/app/services/pubsub.py` (add two helpers near the bottom)
- Test: `backend/tests/test_cache_helpers.py` (create)

**Interfaces:**
- Produces: `async def cache_get_json(key: str) -> dict | None` (returns parsed JSON, or `None` on miss / any error / uninitialized pool); `async def cache_set_json(key: str, value, ttl: int) -> None` (best-effort set with expiry; swallows all errors).
- Consumes: the module's existing `_get_redis()` (raises `RuntimeError` when the pool is not initialised) and the `json`/`logger` already imported in the module.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_cache_helpers.py`:

```python
"""cache_get_json / cache_set_json: round-trip plus fail-open behavior."""
import pytest

from app.services import pubsub


async def test_cache_get_returns_none_when_pool_uninitialised(monkeypatch):
    # No pool initialised in the test process -> _get_redis() raises -> miss.
    monkeypatch.setattr(pubsub, "_redis_pool", None)
    assert await pubsub.cache_get_json("stats:dashboard:all") is None


async def test_cache_set_is_noop_when_pool_uninitialised(monkeypatch):
    monkeypatch.setattr(pubsub, "_redis_pool", None)
    # Must not raise.
    await pubsub.cache_set_json("k", {"a": 1}, 30)


async def test_cache_round_trip_with_fake_redis(monkeypatch):
    store = {}

    class _FakeRedis:
        async def get(self, key):
            return store.get(key)

        async def set(self, key, value, ex=None):
            store[key] = value

    monkeypatch.setattr(pubsub, "_get_redis", lambda: _FakeRedis())

    await pubsub.cache_set_json("k", {"errors_24h": 7}, 30)
    assert await pubsub.cache_get_json("k") == {"errors_24h": 7}


async def test_cache_get_fails_open_on_redis_error(monkeypatch):
    class _BoomRedis:
        async def get(self, key):
            raise ConnectionError("redis down")

    monkeypatch.setattr(pubsub, "_get_redis", lambda: _BoomRedis())
    assert await pubsub.cache_get_json("k") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose -f docker-compose.dev.yml exec backend pytest tests/test_cache_helpers.py -v`
Expected: FAIL with `AttributeError: module 'app.services.pubsub' has no attribute 'cache_get_json'`.

- [ ] **Step 3: Add the helpers**

In `backend/app/services/pubsub.py`, append after the `queue_depth` function (the module already imports `json` and defines `logger` and `_get_redis`):

```python
# ── JSON cache (best-effort, fail-open) ──────────────────────────────

async def cache_get_json(key: str):
    """Return the cached JSON value for `key`, or None on miss/any error.

    Fail-open: a missing pool or a Redis error is treated as a cache miss so
    the caller falls through to its source of truth. Never raises.
    """
    try:
        r = _get_redis()
        raw = await r.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.warning("cache_get_json failed for %s: %s", key, e)
        return None


async def cache_set_json(key: str, value, ttl: int) -> None:
    """Best-effort cache write with a TTL (seconds). Swallows all errors."""
    try:
        r = _get_redis()
        await r.set(key, json.dumps(value), ex=ttl)
    except Exception as e:
        logger.warning("cache_set_json failed for %s: %s", key, e)
```

(The pool is created with `decode_responses=True`, so `r.get` returns `str` — `json.loads` accepts it directly.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose -f docker-compose.dev.yml exec backend pytest tests/test_cache_helpers.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/pubsub.py backend/tests/test_cache_helpers.py
git commit -m "feat(cache): fail-open Redis JSON cache helpers"
```

---

### Task 4: Cache the dashboard stats endpoint

Wraps `GET /stats/dashboard` in the scope-keyed cache. This is the keystone change — it pulls the repeated `COUNT` aggregates off Postgres under load.

**Files:**
- Modify: `backend/app/api/v1/stats.py` (`dashboard_stats` + a new key helper)
- Test: `backend/tests/test_stats_cache.py` (create)

**Interfaces:**
- Consumes: `cache_get_json` / `cache_set_json` (Task 3); `settings.STATS_CACHE_TTL` (Task 1); existing `get_user_project_ids(current_user, db) -> list | None`.
- Produces: `_dashboard_cache_key(project_ids) -> str` (`"stats:dashboard:all"` for admins / `None` scope; `"stats:dashboard:{sha1}"` otherwise, order-independent). `dashboard_stats` now returns the cached dict on hit.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_stats_cache.py`:

```python
"""Dashboard stats caching: key derivation, hit short-circuits DB, miss sets cache."""
import uuid

import pytest

from app.api.v1 import stats
from app.config import settings


def test_dashboard_cache_key_admin_is_stable():
    assert stats._dashboard_cache_key(None) == "stats:dashboard:all"


def test_dashboard_cache_key_is_scope_specific_and_order_independent():
    a, b = uuid.uuid4(), uuid.uuid4()
    k_ab = stats._dashboard_cache_key([a, b])
    k_ba = stats._dashboard_cache_key([b, a])
    assert k_ab == k_ba                       # order-independent
    assert k_ab != stats._dashboard_cache_key([a])   # scope-specific
    assert k_ab != "stats:dashboard:all"      # never collides with admin


async def test_dashboard_cache_hit_skips_db(monkeypatch):
    sentinel = {"total_projects": 7, "errors_24h": 3,
                "unresolved_issues": 1, "active_users": 2}

    async def _hit(key):
        assert key == "stats:dashboard:all"
        return sentinel

    async def _admin_scope(user, db):
        return None

    monkeypatch.setattr(stats, "cache_get_json", _hit)
    monkeypatch.setattr(stats, "get_user_project_ids", _admin_scope)

    class _NoDB:
        async def execute(self, *a, **k):
            raise AssertionError("DB must not be queried on a cache hit")

    result = await stats.dashboard_stats(current_user=object(), db=_NoDB())
    assert result == sentinel


async def test_dashboard_cache_miss_queries_and_sets(monkeypatch, db):
    async def _miss(key):
        return None

    sets = []

    async def _set(key, value, ttl):
        sets.append((key, value, ttl))

    async def _admin_scope(user, db_):
        return None

    monkeypatch.setattr(stats, "cache_get_json", _miss)
    monkeypatch.setattr(stats, "cache_set_json", _set)
    monkeypatch.setattr(stats, "get_user_project_ids", _admin_scope)

    result = await stats.dashboard_stats(current_user=object(), db=db)

    assert set(result) == {"total_projects", "errors_24h",
                           "unresolved_issues", "active_users"}
    assert len(sets) == 1
    key, value, ttl = sets[0]
    assert key == "stats:dashboard:all"
    assert value == result
    assert ttl == settings.STATS_CACHE_TTL
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose -f docker-compose.dev.yml exec backend pytest tests/test_stats_cache.py -v`
Expected: FAIL — `AttributeError: ... has no attribute '_dashboard_cache_key'`.

- [ ] **Step 3: Implement caching in `dashboard_stats`**

In `backend/app/api/v1/stats.py`, add imports near the top (after the existing imports):

```python
import hashlib

from app.config import settings
from app.services.pubsub import cache_get_json, cache_set_json
```

Add the key helper above `dashboard_stats`:

```python
def _dashboard_cache_key(project_ids) -> str:
    """Cache key scoped to the caller's project access (preserves RBAC).

    Admins (project_ids is None) share one key; scoped users get a key derived
    from their sorted project ids so two callers with the same scope share a
    cache entry and no payload leaks across scopes.
    """
    if project_ids is None:
        return "stats:dashboard:all"
    digest = hashlib.sha1(
        ",".join(sorted(str(pid) for pid in project_ids)).encode()
    ).hexdigest()
    return f"stats:dashboard:{digest}"
```

Then rewrite the body of `dashboard_stats` to check the cache first and store on miss:

```python
@router.get("/stats/dashboard")
async def dashboard_stats(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated dashboard stats. Non-admins see only their assigned projects."""
    # Get user's project scope (cheap; also forms the cache key)
    project_ids = await get_user_project_ids(current_user, db)

    cache_key = _dashboard_cache_key(project_ids)
    cached = await cache_get_json(cache_key)
    if cached is not None:
        return cached

    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)

    # Total projects
    projects_query = select(func.count(Project.id))
    if project_ids is not None:
        projects_query = projects_query.where(Project.id.in_(project_ids))
    projects_count = await db.execute(projects_query)

    # Errors in last 24h (events received)
    errors_query = select(func.count(Event.id)).where(Event.received_at >= last_24h)
    if project_ids is not None:
        errors_query = errors_query.where(Event.project_id.in_(project_ids))
    errors_24h = await db.execute(errors_query)

    # Unresolved issues
    unresolved_query = select(func.count(Issue.id)).where(Issue.status == IssueStatus.UNRESOLVED)
    if project_ids is not None:
        unresolved_query = unresolved_query.where(Issue.project_id.in_(project_ids))
    unresolved = await db.execute(unresolved_query)

    # Active users (global count — not scoped)
    active_users = await db.execute(
        select(func.count(User.id)).where(User.is_active == True)
    )

    result = {
        "total_projects": projects_count.scalar() or 0,
        "errors_24h": errors_24h.scalar() or 0,
        "unresolved_issues": unresolved.scalar() or 0,
        "active_users": active_users.scalar() or 0,
    }
    await cache_set_json(cache_key, result, settings.STATS_CACHE_TTL)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose -f docker-compose.dev.yml exec backend pytest tests/test_stats_cache.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/stats.py backend/tests/test_stats_cache.py
git commit -m "feat(stats): cache dashboard aggregates per project scope"
```

---

### Task 5: Cache the project trends endpoint

Caches `GET /stats/projects/{slug}/trends` per `(project_id, days)`, with the authorization check kept strictly before the cache lookup.

**Files:**
- Modify: `backend/app/api/v1/stats.py` (`project_trends`)
- Test: `backend/tests/test_stats_trends_cache.py` (create)

**Interfaces:**
- Consumes: `cache_get_json` / `cache_set_json` (Task 3); existing `check_project_access(current_user, project_id, db) -> bool`.
- Produces: a module constant `_TRENDS_CACHE_TTL = 60`; `project_trends` returns the cached dict on hit and only after a passing access check.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_stats_trends_cache.py`:

```python
"""Project trends caching: access check runs before any cache lookup; hits short-circuit."""
import uuid

import pytest
from fastapi import HTTPException

from app.api.v1 import stats
from app.models.user import User
from app.models.project import Project


@pytest.fixture
async def project(db):
    user = User(email=f"trends-{uuid.uuid4().hex[:8]}@example.com", name="T", password_hash="x")
    db.add(user)
    await db.flush()
    proj = Project(
        name="Trend Proj", slug=f"trend-{uuid.uuid4().hex[:8]}",
        dsn_public_key=uuid.uuid4().hex, created_by=user.id,
    )
    db.add(proj)
    await db.flush()
    return proj


async def test_trends_denied_before_cache_lookup(monkeypatch, db, project):
    async def _deny(user, project_id, db_):
        return False

    async def _cache_must_not_run(key):
        raise AssertionError("cache must not be consulted for an unauthorized caller")

    monkeypatch.setattr(stats, "check_project_access", _deny)
    monkeypatch.setattr(stats, "cache_get_json", _cache_must_not_run)

    with pytest.raises(HTTPException) as exc:
        await stats.project_trends(
            slug=project.slug, current_user=object(), db=db, days=7,
        )
    assert exc.value.status_code == 404


async def test_trends_cache_hit_short_circuits(monkeypatch, db, project):
    sentinel = {"project": project.slug, "days": 7, "data": [{"date": "2026-06-20", "count": 5}]}

    async def _allow(user, project_id, db_):
        return True

    async def _hit(key):
        assert key == f"stats:trends:{project.id}:7"
        return sentinel

    monkeypatch.setattr(stats, "check_project_access", _allow)
    monkeypatch.setattr(stats, "cache_get_json", _hit)

    result = await stats.project_trends(
        slug=project.slug, current_user=object(), db=db, days=7,
    )
    assert result == sentinel
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose -f docker-compose.dev.yml exec backend pytest tests/test_stats_trends_cache.py -v`
Expected: FAIL — the current `project_trends` never calls `cache_get_json`, so the hit test fails (and the deny test passes only incidentally). Confirm both are collected and the hit test fails with an assertion/`KeyError` mismatch.

- [ ] **Step 3: Implement caching in `project_trends`**

In `backend/app/api/v1/stats.py`, add the module constant near the top (below the imports):

```python
_TRENDS_CACHE_TTL = 60  # seconds; daily buckets move slowly
```

Rewrite `project_trends` so the cache check sits *after* the access check and before the heavy query:

```python
@router.get("/stats/projects/{slug}/trends")
async def project_trends(
    slug: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    days: int = 7,
):
    """Get error trend data for a project. Must be a member or admin."""
    result = await db.execute(
        select(Project).where(Project.slug == slug)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not await check_project_access(current_user, project.id, db):
        raise HTTPException(status_code=404, detail="Project not found")

    cache_key = f"stats:trends:{project.id}:{days}"
    cached = await cache_get_json(cache_key)
    if cached is not None:
        return cached

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    # Get daily event counts using date_trunc
    day_col = func.date_trunc("day", Event.received_at).label("day")
    trend_query = (
        select(
            day_col,
            func.count(Event.id).label("count"),
        )
        .where(
            Event.project_id == project.id,
            Event.received_at >= start,
        )
        .group_by(day_col)
        .order_by(day_col)
    )
    trend_result = await db.execute(trend_query)

    # Build day-by-day data (fill gaps with 0)
    trend_map = {row.day.date(): row.count for row in trend_result}
    data = []
    for i in range(days):
        day = (start + timedelta(days=i + 1)).date()
        data.append({
            "date": day.isoformat(),
            "count": trend_map.get(day, 0),
        })

    payload = {
        "project": slug,
        "days": days,
        "data": data,
    }
    await cache_set_json(cache_key, payload, _TRENDS_CACHE_TTL)
    return payload
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose -f docker-compose.dev.yml exec backend pytest tests/test_stats_trends_cache.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/stats.py backend/tests/test_stats_trends_cache.py
git commit -m "feat(stats): cache per-project trends, access check before cache"
```

---

### Task 6: Budget the backend connection pool

Makes the backend engine pool size configurable and lowers the default so the web tier fits comfortably under Postgres `max_connections` alongside the ingest/worker pools.

**Files:**
- Modify: `backend/app/database.py`
- Test: `backend/tests/test_db_pool.py` (create)

**Interfaces:**
- Consumes: `settings.DB_POOL_SIZE`, `settings.DB_MAX_OVERFLOW` (Task 1).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_db_pool.py`:

```python
"""The backend engine sizes its pool from settings (budgeted under max_connections)."""
from app.config import settings
from app.database import engine


def test_engine_pool_size_from_settings():
    assert engine.sync_engine.pool.size() == settings.DB_POOL_SIZE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f docker-compose.dev.yml exec backend pytest tests/test_db_pool.py -v`
Expected: FAIL — `assert 20 == 10` (the engine is currently hard-coded to `pool_size=20`).

- [ ] **Step 3: Wire the pool to settings**

In `backend/app/database.py`, replace the hard-coded pool arguments:

```python
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ENVIRONMENT == "development",
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f docker-compose.dev.yml exec backend pytest tests/test_db_pool.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/database.py backend/tests/test_db_pool.py
git commit -m "feat(db): size backend connection pool from settings"
```

---

### Task 7: Bound the ingest worker drain rate

Applies a configurable Celery `rate_limit` to `ingest_event` so a storm drains at a sustainable pace and leaves Postgres headroom for reads. Default is no cap.

**Files:**
- Modify: `backend/app/worker.py`
- Test: `backend/tests/test_worker_rate_limit.py` (create)

**Interfaces:**
- Consumes: `settings.INGEST_RATE_LIMIT` (Task 1).
- Produces: `_apply_ingest_rate_limit(app, rate_limit) -> Celery` — sets `app.conf.task_annotations["ingest_event"]["rate_limit"]` when `rate_limit` is truthy; no-ops otherwise. Called at module load with `(celery_app, settings.INGEST_RATE_LIMIT)`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_worker_rate_limit.py`:

```python
"""ingest_event gets a Celery rate_limit only when INGEST_RATE_LIMIT is set."""
from celery import Celery

from app.worker import _apply_ingest_rate_limit


def test_rate_limit_applied_when_set():
    app = Celery("t")
    _apply_ingest_rate_limit(app, "200/s")
    assert app.conf.task_annotations["ingest_event"]["rate_limit"] == "200/s"


def test_rate_limit_absent_when_unset():
    app = Celery("t")
    _apply_ingest_rate_limit(app, None)
    assert not app.conf.task_annotations  # None (Celery default) -> falsy
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose -f docker-compose.dev.yml exec backend pytest tests/test_worker_rate_limit.py -v`
Expected: FAIL — `ImportError: cannot import name '_apply_ingest_rate_limit'`.

- [ ] **Step 3: Add the helper and call it at module load**

In `backend/app/worker.py`, after the existing `celery_app.conf.task_routes = {...}` block and before the `beat_schedule` block, add:

```python
def _apply_ingest_rate_limit(app, rate_limit):
    """Cap the per-worker drain rate of ingest_event so storms leave Postgres
    headroom for reads. Unset = no cap (the queue + INGEST_QUEUE_MAX absorb bursts)."""
    if rate_limit:
        app.conf.task_annotations = {
            "ingest_event": {"rate_limit": rate_limit},
        }
    return app


_apply_ingest_rate_limit(celery_app, settings.INGEST_RATE_LIMIT)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose -f docker-compose.dev.yml exec backend pytest tests/test_worker_rate_limit.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/worker.py backend/tests/test_worker_rate_limit.py
git commit -m "feat(ingest): optional Celery rate_limit on the ingest worker"
```

---

### Task 8: Compose resource limits, ingest concurrency env, and Postgres max_connections

Infra/config only (no unit test — verified with `docker compose config` and `docker stats`). Caps ingest's CPU/memory footprint, makes ingest concurrency env-driven, and raises Postgres connection headroom to fit the budgeted pools.

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.dev.yml`

- [ ] **Step 1: Raise Postgres connection headroom (both files)**

In **both** `docker-compose.yml` and `docker-compose.dev.yml`, give the `postgres` service an explicit `command` so the budgeted pools fit. Add this line to the `postgres:` service (alongside `image:`/`restart:`):

```yaml
    command: postgres -c max_connections=200
```

- [ ] **Step 2: Make ingest concurrency env-driven (both files)**

In **both** compose files, change the `celery-ingest` `command` to interpolate the concurrency:

`docker-compose.yml`:
```yaml
    command: celery -A app.worker worker -Q ingest --concurrency=${INGEST_CONCURRENCY:-4} --loglevel=info
```

`docker-compose.dev.yml`:
```yaml
    command: celery -A app.worker worker -Q ingest --concurrency=${INGEST_CONCURRENCY:-4} --loglevel=info
```

- [ ] **Step 3: Add resource limits to `celery-ingest` (both files)**

In **both** compose files, add a `deploy.resources.limits` block to the `celery-ingest` service (Docker Compose v2 honors these for `docker compose up`). Tune the numbers to the host; these are conservative starting values that keep at least one core free for the backend + Postgres:

```yaml
    deploy:
      resources:
        limits:
          cpus: "1.5"
          memory: 1g
```

- [ ] **Step 4: Validate both compose files render**

Run:
```bash
docker compose -f docker-compose.yml config >/dev/null && echo PROD_OK
docker compose -f docker-compose.dev.yml config >/dev/null && echo DEV_OK
```
Expected: `PROD_OK` and `DEV_OK` (no YAML/interpolation errors).

- [ ] **Step 5: Recreate the affected services and confirm limits apply (dev)**

Run:
```bash
docker compose -f docker-compose.dev.yml up -d postgres celery-ingest
docker stats --no-stream
```
Expected: services healthy; `celery-ingest` shows a `MEM LIMIT` of ~1GiB in `docker stats`. Confirm Postgres accepts connections: `docker compose -f docker-compose.dev.yml exec postgres psql -U megoo -d megoobug -c "show max_connections;"` → `200`.

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml docker-compose.dev.yml
git commit -m "feat(infra): cap ingest resources, env-drive concurrency, raise pg max_connections"
```

---

### Task 9: Full verification and manual storm check

No code — proves the whole change works together and the read path is actually faster under load.

**Files:** none (verification only).

- [ ] **Step 1: Run the full backend suite**

Run: `docker compose -f docker-compose.dev.yml exec backend pytest`
Expected: all tests pass — the pre-existing suite plus the new `test_config_settings`, `test_read_indexes`, `test_cache_helpers`, `test_stats_cache`, `test_stats_trends_cache`, `test_db_pool`, `test_worker_rate_limit`.

- [ ] **Step 2: Lint**

Run: `docker compose -f docker-compose.dev.yml exec backend ruff check .`
Expected: no errors.

- [ ] **Step 3: Confirm the dashboard count uses the new index**

Run:
```bash
docker compose -f docker-compose.dev.yml exec postgres \
  psql -U megoo -d megoobug -c \
  "EXPLAIN SELECT count(id) FROM events WHERE received_at >= now() - interval '24 hours';"
```
Expected: the plan references `ix_events_received_at` (index/bitmap scan) rather than a bare `Seq Scan` (once the table holds enough rows for the planner to prefer the index).

- [ ] **Step 4: Manual storm check (read responsiveness)**

With the dev stack up, in one shell drive a burst of events at the ingest endpoint (reuse a real project DSN public key from the dev DB); in another shell, repeatedly time the dashboard:

```bash
# Shell A — burst (adjust the key/project id to a real dev project)
for i in $(seq 1 3000); do \
  curl -s -o /dev/null "http://localhost:8000/api/1/store/?sentry_key=<dev_key>" \
    -H 'Content-Type: application/json' \
    -d '{"message":"storm '"$i"'","level":"error"}'; \
done

# Shell B — read latency during the storm (needs a valid auth cookie/JWT)
for i in $(seq 1 20); do \
  curl -s -o /dev/null -w "%{time_total}\n" \
    -H "Authorization: Bearer <token>" \
    http://localhost:8000/api/v1/stats/dashboard; \
  sleep 1; \
done
```

Expected: dashboard response times stay low and roughly flat through the storm (cache hits after the first per-scope miss); the `ingest` queue drains afterward. Contrast is clearest if you also try it with `STATS_CACHE_TTL=0` to see the uncached behavior.

- [ ] **Step 5: Final no-op commit check**

Run: `git status`
Expected: clean working tree (everything committed in Tasks 1–8). If `make reindex`/migrations left artifacts, do not commit them.

---

## Self-Review

**Spec coverage:**
- §1 Indexes → Task 2 (all three indexes; partial→composite deviation documented). ✅
- §2 Cached aggregates (helpers, dashboard scope-key, trends, fail-open, access-before-cache) → Tasks 3, 4, 5. ✅
- §3 Ingest throttle (`INGEST_CONCURRENCY`, `INGEST_RATE_LIMIT`) → Tasks 1, 7, 8. ✅
- §4 Connection & resource budgeting (pools, docker limits, `max_connections`, new settings, `.env.example`) → Tasks 1, 6, 8. ✅
- §5 Unchanged surfaces → no task touches ingest URLs/auth, `process_event`, or the websocket flow. ✅
- Testing section (cache hit/miss, fail-open, scope-keying, TTL, migration/index presence, throttle config, suite stays green, manual storm) → Tasks 2–9. ✅

**Placeholder scan:** No TBD/TODO; every code step shows full code; commands have expected output. The only intentionally host-specific values are the docker resource limits and the manual-storm DSN/token, each flagged as "tune to host / use a real dev value." ✅

**Type consistency:** `cache_get_json`/`cache_set_json` signatures match across Tasks 3–5; `_dashboard_cache_key` returns `str` and is used consistently; `_apply_ingest_rate_limit(app, rate_limit)` matches its test; index names (`ix_events_received_at`, `ix_events_project_received_at`, `ix_issues_project_status`) are identical in the model, the migration, and the test; settings names match across config, `.env.example`, compose, and consumers. ✅
