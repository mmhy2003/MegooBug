# Async Ingestion Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest endpoints accept-and-enqueue in ~1ms (DSN cache, size cap, queue-depth 429, 503 on broker failure); a dedicated `celery-ingest` worker drains a dedicated `ingest` queue and runs the existing `process_event` unchanged.

**Architecture:** The API stops touching Postgres on the ingest hot path (DSN snapshot cache with negative caching; short-lived session only on cache miss). Events transit Redis as Celery task payloads. Each prefork ingest-worker child keeps ONE persistent event loop + async engine + pubsub pool, reused across tasks — that's what makes async `process_event` sustainable at hundreds of events/sec from sync Celery. Backpressure: `LLEN ingest` > cap → 429.

**Tech Stack:** FastAPI, Celery 5.5 / Redis, SQLAlchemy async (asyncpg), httpx ASGITransport for endpoint tests, existing pytest scaffold.

**Spec:** `docs/superpowers/specs/2026-06-10-async-ingestion-pipeline-design.md`

## File Structure

- Modify: `backend/app/config.py` — `MAX_EVENT_BYTES`, `INGEST_QUEUE_MAX`.
- Modify: `.env.example` — the two settings + `UVICORN_WORKERS`.
- Modify: `backend/app/services/pubsub.py` — add `queue_depth(queue)`.
- Modify: `backend/app/services/ingest.py` — `_extract_dsn_key` refactor, `ProjectSnapshot`, `resolve_dsn` (cached), `ingest_queue_full`, delete `validate_dsn`.
- Create: `backend/app/tasks/ingest_tasks.py` — `ingest_event` task + persistent loop/engine machinery.
- Modify: `backend/app/worker.py` — include module + `task_routes`.
- Modify: `backend/app/api/ingest.py` — thin endpoints.
- Modify: `docker-compose.yml`, `docker-compose.dev.yml` — `celery-ingest` service; prod backend `command:` with `--workers`.
- Create: `backend/tests/test_ingest_pipeline.py`.

**How tests run** (dev stack up): `docker compose -f docker-compose.dev.yml exec backend pytest` — currently 20 passed; after this plan 32 passed.

**Git identity:** no global identity — commit with `git -c user.name="Mohamed M. Hammad" -c user.email="mohamed.magdy@slnee.com" commit -m "..."`.

**Branch:** `feat/async-ingestion` from `main`, created in Task 1. No worktree (dev stack bind-mounts `./backend`).

---

### Task 1: Branch + settings

**Files:**
- Modify: `backend/app/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Create branch**

```bash
cd /opt/megoobug && git checkout -b feat/async-ingestion
```

- [ ] **Step 2: Add settings to `backend/app/config.py`**

After the `# ── Retention ──` block, insert:

```python
    # ── Ingestion ──
    # Reject decompressed event payloads larger than this (bytes).
    MAX_EVENT_BYTES: int = 1_048_576
    # Return 429 when the Redis ingest queue is deeper than this.
    INGEST_QUEUE_MAX: int = 50_000
```

- [ ] **Step 3: Add to `.env.example`** after the Retention block:

```
# ── Ingestion ──
# Reject decompressed event payloads larger than this (bytes).
MAX_EVENT_BYTES=1048576
# Return 429 when the Redis ingest queue is deeper than this.
INGEST_QUEUE_MAX=50000
# Uvicorn worker processes for the production backend container.
UVICORN_WORKERS=2
```

- [ ] **Step 4: Verify + commit**

```bash
docker compose -f docker-compose.dev.yml exec backend python -c "from app.config import settings; print(settings.MAX_EVENT_BYTES, settings.INGEST_QUEUE_MAX)"
```
Expected: `1048576 50000`.

```bash
git add backend/app/config.py .env.example
git -c user.name="Mohamed M. Hammad" -c user.email="mohamed.magdy@slnee.com" commit -m "feat(ingest): add MAX_EVENT_BYTES and INGEST_QUEUE_MAX settings"
```

---

### Task 2: DSN snapshot cache + queue-depth backpressure (TDD)

**Files:**
- Create: `backend/tests/test_ingest_pipeline.py`
- Modify: `backend/app/services/ingest.py`
- Modify: `backend/app/services/pubsub.py`

- [ ] **Step 1: Write the failing tests `backend/tests/test_ingest_pipeline.py`**

```python
"""Tests for the async ingestion pipeline: DSN cache, backpressure, endpoints, worker."""
import time
import uuid

import pytest


# ── DSN snapshot cache ──────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clear_dsn_cache():
    from app.services import ingest as ingest_service
    ingest_service.clear_dsn_cache()
    yield
    ingest_service.clear_dsn_cache()


def _snapshot(slug="cache-proj"):
    from app.services.ingest import ProjectSnapshot
    return ProjectSnapshot(id=str(uuid.uuid4()), name="Cache Proj", slug=slug)


async def test_resolve_dsn_caches_positive_lookups(monkeypatch):
    from app.services import ingest as ingest_service

    calls = []
    snap = _snapshot()

    async def _fake_fetch(dsn_key):
        calls.append(dsn_key)
        return snap

    monkeypatch.setattr(ingest_service, "_fetch_project_snapshot", _fake_fetch)

    auth = "Sentry sentry_key=aabbccdd, sentry_version=7"
    first = await ingest_service.resolve_dsn(auth, {})
    second = await ingest_service.resolve_dsn(auth, {})

    assert first == snap and second == snap
    assert calls == ["aabbccdd"]  # second hit served from cache


async def test_resolve_dsn_caches_negative_lookups(monkeypatch):
    from app.services import ingest as ingest_service

    calls = []

    async def _fake_fetch(dsn_key):
        calls.append(dsn_key)
        return None

    monkeypatch.setattr(ingest_service, "_fetch_project_snapshot", _fake_fetch)

    assert await ingest_service.resolve_dsn("", {"sentry_key": "badbadba"}) is None
    assert await ingest_service.resolve_dsn("", {"sentry_key": "badbadba"}) is None
    assert calls == ["badbadba"]  # invalid key cached too


# ── Queue-depth backpressure ────────────────────────────────────────

async def test_ingest_queue_full_fails_open(monkeypatch):
    """If the depth check itself errors, ingestion must NOT be blocked."""
    from app.services import ingest as ingest_service

    async def _boom(queue):
        raise ConnectionError("redis down")

    monkeypatch.setattr(ingest_service, "_queue_depth", _boom)
    ingest_service.clear_depth_cache()
    assert await ingest_service.ingest_queue_full() is False


async def test_ingest_queue_full_above_cap(monkeypatch):
    from app.config import settings
    from app.services import ingest as ingest_service

    async def _deep(queue):
        assert queue == "ingest"
        return settings.INGEST_QUEUE_MAX + 1

    monkeypatch.setattr(ingest_service, "_queue_depth", _deep)
    ingest_service.clear_depth_cache()
    assert await ingest_service.ingest_queue_full() is True
```

- [ ] **Step 2: Run to verify failure**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/test_ingest_pipeline.py -v
```
Expected: errors — `AttributeError: module 'app.services.ingest' has no attribute 'clear_dsn_cache'`.

- [ ] **Step 3: Add `queue_depth` to `backend/app/services/pubsub.py`** (after the publish helpers):

```python
# ── Queue inspection ─────────────────────────────────────────────────

async def queue_depth(queue: str) -> int:
    """Length of a Celery queue's Redis list (Celery queues are plain lists)."""
    r = _get_redis()
    return int(await r.llen(queue))
```

- [ ] **Step 4: Implement in `backend/app/services/ingest.py`**

a) Add imports near the top: `import time`, `from dataclasses import dataclass`, and `from app.database import async_session_factory`.

b) Refactor the key-extraction out of `validate_dsn` into a pure function (place it next to `validate_dsn`; the body is lifted verbatim from validate_dsn's first half):

```python
def _extract_dsn_key(
    auth_header: str | None,
    query_params: dict,
    envelope_header: dict | None = None,
) -> str | None:
    """Extract the DSN public key from header, query param, or envelope DSN."""
    if auth_header:
        match = _SENTRY_AUTH_RE.search(auth_header)
        if match:
            return match.group(1)

    key = query_params.get("sentry_key")
    if key:
        return key

    if envelope_header:
        dsn_str = envelope_header.get("dsn", "")
        if dsn_str:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(dsn_str)
                if parsed.username:
                    return parsed.username
            except Exception:
                pass

    return None
```

c) Add the snapshot cache (module level, after `_extract_dsn_key`):

```python
@dataclass(frozen=True)
class ProjectSnapshot:
    """Minimal project identity for the ingest hot path."""
    id: str
    name: str
    slug: str


_DSN_CACHE: dict[str, tuple[ProjectSnapshot | None, float]] = {}
_DSN_CACHE_TTL = 60.0       # seconds, valid keys
_DSN_NEGATIVE_TTL = 10.0    # seconds, unknown keys (don't hammer the DB on floods)


def clear_dsn_cache() -> None:
    """Test hook."""
    _DSN_CACHE.clear()


async def _fetch_project_snapshot(dsn_key: str) -> ProjectSnapshot | None:
    """DB lookup for a DSN key — only called on cache miss."""
    async with async_session_factory() as db:
        result = await db.execute(
            select(Project).where(Project.dsn_public_key == dsn_key)
        )
        project = result.scalar_one_or_none()
    if project is None:
        logger.warning("Invalid DSN key: %s", dsn_key[:8])
        return None
    return ProjectSnapshot(id=str(project.id), name=project.name, slug=project.slug)


async def resolve_dsn(
    auth_header: str | None,
    query_params: dict,
    envelope_header: dict | None = None,
) -> ProjectSnapshot | None:
    """Resolve DSN auth to a project snapshot, with in-process TTL caching."""
    dsn_key = _extract_dsn_key(auth_header, query_params, envelope_header)
    if dsn_key is None:
        logger.warning("No DSN key found in request")
        return None

    now = time.monotonic()
    cached = _DSN_CACHE.get(dsn_key)
    if cached is not None and now < cached[1]:
        return cached[0]

    snapshot = await _fetch_project_snapshot(dsn_key)
    ttl = _DSN_CACHE_TTL if snapshot is not None else _DSN_NEGATIVE_TTL
    _DSN_CACHE[dsn_key] = (snapshot, now + ttl)
    return snapshot
```

d) Add the backpressure check (module level, after the cache):

```python
_DEPTH_CACHE = {"full": False, "expires": 0.0}


def clear_depth_cache() -> None:
    """Test hook."""
    _DEPTH_CACHE.update(full=False, expires=0.0)


async def _queue_depth(queue: str) -> int:
    from app.services.pubsub import queue_depth
    return await queue_depth(queue)


async def ingest_queue_full() -> bool:
    """True when the ingest queue exceeds INGEST_QUEUE_MAX.

    Result cached ~1s; fails OPEN (a broken depth check must not block
    ingestion — the bounded publish timeout is the harder backstop).
    """
    now = time.monotonic()
    if now < _DEPTH_CACHE["expires"]:
        return _DEPTH_CACHE["full"]
    try:
        full = await _queue_depth("ingest") > settings.INGEST_QUEUE_MAX
    except Exception as e:
        logger.warning("Ingest queue depth check failed (failing open): %s", e)
        full = False
    _DEPTH_CACHE.update(full=full, expires=now + 1.0)
    return full
```

Note: `settings` is already imported in this module? If not, add `from app.config import settings`. Do NOT delete `validate_dsn` yet (the endpoints still use it until Task 4).

- [ ] **Step 5: Run tests**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/test_ingest_pipeline.py -v
```
Expected: 4 passed. Full suite: 24 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_ingest_pipeline.py backend/app/services/ingest.py backend/app/services/pubsub.py
git -c user.name="Mohamed M. Hammad" -c user.email="mohamed.magdy@slnee.com" commit -m "feat(ingest): DSN snapshot cache and queue-depth backpressure helpers"
```

---

### Task 3: `ingest_event` worker task with persistent loop/engine (TDD)

**Files:**
- Modify: `backend/tests/test_ingest_pipeline.py` (append)
- Create: `backend/app/tasks/ingest_tasks.py`
- Modify: `backend/app/worker.py`

- [ ] **Step 1: Append the failing end-to-end test**

This test runs the real task body against the TEST database. It commits real rows (the task uses its own engine, not the rollback fixture), so it creates everything with unique markers and deletes its project at the end (cascade wipes issue+event) — otherwise later tests' global-count assertions would see leftovers.

```python
# ── Worker task end-to-end ──────────────────────────────────────────

def test_ingest_event_end_to_end(monkeypatch):
    """The real task body against the test DB: creates issue + event rows."""
    import asyncio
    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.config import settings as app_settings
    from app.services import ingest as ingest_service
    from app.tasks import ingest_tasks
    from app.models.user import User
    from app.models.project import Project
    from app.models.issue import Issue
    from app.models.event import Event
    from tests.conftest import TEST_URL

    # Point the task machinery at the test DB and reset its cached loop/engine
    monkeypatch.setattr(app_settings, "DATABASE_URL", TEST_URL)
    ingest_tasks._reset_state()
    # Suppress meili/email side-dispatches from process_event
    monkeypatch.setattr(ingest_service, "_HAS_TASKS", False)

    marker = uuid.uuid4().hex[:12]
    event_id = uuid.uuid4().hex

    async def _setup():
        engine = create_async_engine(TEST_URL)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            user = User(email=f"ing-{marker}@example.com", name="Ing", password_hash="x")
            db.add(user)
            await db.flush()
            project = Project(
                name=f"Ingest {marker}", slug=f"ingest-{marker}",
                dsn_public_key=uuid.uuid4().hex, created_by=user.id,
            )
            db.add(project)
            await db.commit()
            pid = str(project.id)
        await engine.dispose()
        return pid

    async def _assert_and_cleanup(pid):
        engine = create_async_engine(TEST_URL)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            issue = (await db.execute(
                select(Issue).where(Issue.project_id == uuid.UUID(pid))
            )).scalars().first()
            assert issue is not None
            assert "IngestBoom" in issue.title
            stored = (await db.execute(
                select(Event).where(Event.event_id == event_id)
            )).scalar_one_or_none()
            assert stored is not None
            # Cleanup: cascade removes issue + event; user removed too
            await db.execute(delete(Project).where(Project.id == uuid.UUID(pid)))
            await db.execute(delete(User).where(User.email == f"ing-{marker}@example.com"))
            await db.commit()
        await engine.dispose()

    pid = asyncio.run(_setup())
    try:
        result = ingest_tasks.ingest_event.run(pid, {
            "event_id": event_id,
            "message": f"IngestBoom {marker}",
            "timestamp": time.time(),
        })
        assert result == event_id
        asyncio.run(_assert_and_cleanup(pid))
    finally:
        ingest_tasks._reset_state()


def test_ingest_event_drops_missing_project(monkeypatch):
    from app.config import settings as app_settings
    from app.tasks import ingest_tasks
    from tests.conftest import TEST_URL

    monkeypatch.setattr(app_settings, "DATABASE_URL", TEST_URL)
    ingest_tasks._reset_state()
    try:
        result = ingest_tasks.ingest_event.run(str(uuid.uuid4()), {"message": "orphan"})
        assert result is None
    finally:
        ingest_tasks._reset_state()
```

- [ ] **Step 2: Run to verify failure**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/test_ingest_pipeline.py -v
```
Expected: the two new tests error with `ModuleNotFoundError: No module named 'app.tasks.ingest_tasks'`; the 4 Task-2 tests pass.

- [ ] **Step 3: Create `backend/app/tasks/ingest_tasks.py`**

```python
"""Celery task for asynchronous event ingestion.

The ingest API endpoints accept-and-enqueue; this task does the actual
processing (dedup, issue upsert, event insert, notifications, indexing)
by calling the existing async process_event.

PERSISTENT LOOP + ENGINE PER WORKER CHILD (load-bearing, non-obvious):
process_event is async but Celery tasks are sync. Creating an asyncpg
engine per task cannot sustain hundreds of events/sec, and an asyncpg
pool is bound to the event loop it was created on. So each prefork
worker child lazily creates ONE event loop, ONE async engine, and the
pubsub Redis pool (for websocket pushes inside process_event), and
reuses them for every task via loop.run_until_complete.
"""
import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.worker import celery_app
from app.config import settings
from app.logging import get_logger

logger = get_logger("tasks.ingest")

_loop: asyncio.AbstractEventLoop | None = None
_session_factory = None


def _get_loop_and_factory():
    """Lazily create the per-process loop, engine, and pubsub pool."""
    global _loop, _session_factory
    if _loop is None:
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        engine = create_async_engine(
            settings.DATABASE_URL, pool_size=5, max_overflow=2, pool_pre_ping=True
        )
        _session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        # process_event publishes websocket updates via the pubsub pool;
        # initialise it on this loop so realtime updates keep working.
        from app.services.pubsub import init_redis
        try:
            _loop.run_until_complete(init_redis())
        except Exception as e:
            logger.warning("Pubsub init failed in ingest worker (realtime updates off): %s", e)
    return _loop, _session_factory


def _reset_state() -> None:
    """Test hook: drop the cached loop/engine so a new DATABASE_URL takes effect."""
    global _loop, _session_factory
    if _loop is not None:
        try:
            _loop.close()
        except Exception:
            pass
    _loop = None
    _session_factory = None


async def _process(project_id: str, event_data: dict, session_factory) -> str | None:
    from app.models.project import Project
    from app.services.ingest import process_event

    async with session_factory() as db:
        result = await db.execute(
            select(Project).where(Project.id == uuid.UUID(project_id))
        )
        project = result.scalar_one_or_none()
        if project is None:
            logger.warning("Ingest: project %s no longer exists — dropping event", project_id)
            return None
        issue, event = await process_event(project, event_data, db)
        await db.commit()
        return event.event_id


@celery_app.task(name="ingest_event")
def ingest_event(project_id: str, event_data: dict) -> str | None:
    """Process one queued event. Fire-once: failures are logged and dropped."""
    loop, factory = _get_loop_and_factory()
    try:
        return loop.run_until_complete(_process(project_id, event_data, factory))
    except Exception:
        logger.error(
            "Failed to process event %s (project=%s)",
            event_data.get("event_id"), project_id, exc_info=True,
        )
        return None
```

- [ ] **Step 4: Wire into `backend/app/worker.py`**

Include list gains the module, and routing sends it to the dedicated queue:

```python
celery_app.conf.include = [
    "app.tasks.event_tasks",
    "app.tasks.cleanup_tasks",
    "app.tasks.email_tasks",
    "app.tasks.ingest_tasks",
]

# Route event ingestion to its own queue so storms can't starve emails,
# indexing, or cleanup (and vice versa) — drained by the celery-ingest service.
celery_app.conf.task_routes = {
    "ingest_event": {"queue": "ingest"},
}
```

- [ ] **Step 5: Run tests**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/test_ingest_pipeline.py -v
```
Expected: 6 passed. Full suite: 26 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_ingest_pipeline.py backend/app/tasks/ingest_tasks.py backend/app/worker.py
git -c user.name="Mohamed M. Hammad" -c user.email="mohamed.magdy@slnee.com" commit -m "feat(ingest): ingest_event task with persistent per-child loop and engine"
```

---

### Task 4: Thin ingest endpoints (TDD)

**Files:**
- Modify: `backend/tests/test_ingest_pipeline.py` (append)
- Modify: `backend/app/api/ingest.py`
- Modify: `backend/app/services/ingest.py` (delete `validate_dsn`)

- [ ] **Step 1: Append the failing endpoint tests**

httpx `ASGITransport` runs no lifespan, so nothing external is touched — DSN resolution, depth check, and `delay` are all monkeypatched on the `app.api.ingest` namespace.

```python
# ── Thin endpoints ──────────────────────────────────────────────────

import json


@pytest.fixture
async def api_client():
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _patch_pipeline(monkeypatch, snapshot, queue_full=False):
    from app.api import ingest as ingest_api

    captured = []

    async def _resolve(auth_header, query_params, envelope_header=None):
        return snapshot

    async def _full():
        return queue_full

    monkeypatch.setattr(ingest_api, "resolve_dsn", _resolve)
    monkeypatch.setattr(ingest_api, "ingest_queue_full", _full)
    monkeypatch.setattr(
        ingest_api.ingest_event, "delay",
        lambda project_id, event_data: captured.append((project_id, event_data)),
    )
    return captured


async def test_store_endpoint_enqueues_and_returns_200(api_client, monkeypatch):
    snap = _snapshot()
    captured = _patch_pipeline(monkeypatch, snap)

    eid = uuid.uuid4().hex
    resp = await api_client.post(
        "/api/1/store/?sentry_key=aabbccdd",
        json={"event_id": eid, "message": "queued!"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"id": eid}
    assert len(captured) == 1
    project_id, event_data = captured[0]
    assert project_id == snap.id
    assert event_data["message"] == "queued!"


async def test_store_endpoint_401_unknown_dsn(api_client, monkeypatch):
    _patch_pipeline(monkeypatch, snapshot=None)
    resp = await api_client.post("/api/1/store/?sentry_key=bad", json={"message": "x"})
    assert resp.status_code == 401


async def test_store_endpoint_413_oversized(api_client, monkeypatch):
    from app.config import settings
    snap = _snapshot()
    _patch_pipeline(monkeypatch, snap)
    monkeypatch.setattr(settings, "MAX_EVENT_BYTES", 50)

    resp = await api_client.post(
        "/api/1/store/?sentry_key=aabbccdd",
        json={"message": "Y" * 200},
    )
    assert resp.status_code == 413


async def test_store_endpoint_429_when_queue_full(api_client, monkeypatch):
    snap = _snapshot()
    _patch_pipeline(monkeypatch, snap, queue_full=True)

    resp = await api_client.post(
        "/api/1/store/?sentry_key=aabbccdd", json={"message": "x"},
    )
    assert resp.status_code == 429
    assert resp.headers.get("retry-after") == "30"


async def test_store_endpoint_503_when_broker_down(api_client, monkeypatch):
    from app.api import ingest as ingest_api
    snap = _snapshot()
    _patch_pipeline(monkeypatch, snap)

    def _broker_down(project_id, event_data):
        raise ConnectionError("redis unreachable")

    monkeypatch.setattr(ingest_api.ingest_event, "delay", _broker_down)
    resp = await api_client.post(
        "/api/1/store/?sentry_key=aabbccdd", json={"message": "x"},
    )
    assert resp.status_code == 503


async def test_envelope_endpoint_enqueues_each_event(api_client, monkeypatch):
    snap = _snapshot()
    captured = _patch_pipeline(monkeypatch, snap)

    eid = uuid.uuid4().hex
    envelope = (
        json.dumps({"dsn": "http://aabbccdd@localhost/1"}) + "\n"
        + json.dumps({"type": "event"}) + "\n"
        + json.dumps({"event_id": eid, "message": "from envelope"}) + "\n"
    )
    resp = await api_client.post(
        "/api/1/envelope/",
        content=envelope.encode(),
        headers={"Content-Type": "application/x-sentry-envelope"},
    )

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0][1]["event_id"] == eid
```

- [ ] **Step 2: Run to verify failure**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/test_ingest_pipeline.py -v
```
Expected: new tests FAIL (`AttributeError: module 'app.api.ingest' has no attribute 'resolve_dsn'` / `ingest_event`); prior 6 pass.

- [ ] **Step 3: Rewrite `backend/app/api/ingest.py`**

Replace the imports and both handlers (keep `_decompress_body` unchanged):

```python
"""Sentry-compatible ingest endpoints.

Accept-and-enqueue: these endpoints validate the DSN (cached), enforce
size and queue-depth limits, queue the event for the celery-ingest
worker, and return immediately. They never touch Postgres on the hot
path and never hold a DB connection while processing — inline processing
caused the 2026-06 pool-exhaustion incident class.
"""
import gzip
import uuid

from fastapi import APIRouter, HTTPException, Request, status

from app.config import settings
from app.services.ingest import (
    ingest_queue_full,
    parse_store_payload,
    parse_envelope_header,
    parse_envelope_payload,
    resolve_dsn,
)
from app.tasks.ingest_tasks import ingest_event
from app.logging import get_logger

logger = get_logger("api.ingest")

router = APIRouter()

_RETRY_AFTER = {"Retry-After": "30"}
```

(keep `_decompress_body` here, unchanged)

```python
def _check_limits_and_body(body: bytes) -> None:
    """Shared 413 guard."""
    if len(body) > settings.MAX_EVENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Event payload too large",
        )


async def _backpressure_guard() -> None:
    if await ingest_queue_full():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Ingestion queue full, retry later",
            headers=_RETRY_AFTER,
        )


def _enqueue(project_id: str, event_data: dict) -> str:
    """Queue one event; returns its event_id. 503 if the broker is unreachable."""
    event_id = event_data.get("event_id") or uuid.uuid4().hex
    event_data["event_id"] = event_id
    try:
        ingest_event.delay(project_id, event_data)
    except Exception as e:
        logger.error("Failed to enqueue event (broker down?): %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingestion temporarily unavailable",
        )
    return event_id


@router.post("/{project_id}/store/")
async def store_event(project_id: str, request: Request):
    """Legacy Sentry store endpoint: accept-and-enqueue."""
    auth_header = request.headers.get("x-sentry-auth", "")
    query_params = dict(request.query_params)
    project = await resolve_dsn(auth_header, query_params)
    if project is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid DSN")

    raw_body = await request.body()
    body = _decompress_body(raw_body, request.headers.get("content-encoding"))
    _check_limits_and_body(body)

    event_data = parse_store_payload(body)
    if not event_data:
        logger.warning(
            "Empty store payload (project=%s, raw=%d bytes, decoded=%d bytes)",
            project.slug, len(raw_body), len(body),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")

    await _backpressure_guard()
    event_id = _enqueue(project.id, event_data)
    return {"id": event_id}


@router.post("/{project_id}/envelope/")
async def store_envelope(project_id: str, request: Request):
    """Sentry envelope endpoint: accept-and-enqueue each event."""
    raw_body = await request.body()
    body = _decompress_body(raw_body, request.headers.get("content-encoding"))
    _check_limits_and_body(body)

    envelope_header, _ = parse_envelope_header(body)

    auth_header = request.headers.get("x-sentry-auth", "")
    query_params = dict(request.query_params)
    project = await resolve_dsn(auth_header, query_params, envelope_header=envelope_header)
    if project is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid DSN")

    events = parse_envelope_payload(body)
    if not events:
        # Envelope may contain non-event items (sessions, etc.) — accept silently
        return {"id": str(uuid.uuid4().hex)}

    await _backpressure_guard()
    last_event_id = None
    for event_data in events:
        last_event_id = _enqueue(project.id, event_data)

    logger.debug("Envelope queued: %d events (project=%s)", len(events), project.slug)
    return {"id": last_event_id or str(uuid.uuid4().hex)}
```

- [ ] **Step 4: Delete `validate_dsn` from `backend/app/services/ingest.py`**

The endpoints were its only callers (verify: `grep -rn "validate_dsn" backend/app --include="*.py"` → nothing left after the rewrite). Remove the function; keep `_extract_dsn_key` and everything else. Remove `Depends`/`get_db`/`AsyncSession` imports from `api/ingest.py` (done in the rewrite above) and check `services/ingest.py` doesn't lose imports still used by `process_event`.

- [ ] **Step 5: Run the full suite + import check**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest -v
docker compose -f docker-compose.dev.yml exec backend python -c "import app.main; print('ok')"
```
Expected: **32 passed** (20 base + 4 from Task 2 + 2 from Task 3 + 6 from this task); `ok`.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_ingest_pipeline.py backend/app/api/ingest.py backend/app/services/ingest.py
git -c user.name="Mohamed M. Hammad" -c user.email="mohamed.magdy@slnee.com" commit -m "feat(ingest): thin accept-and-enqueue endpoints with size cap and backpressure"
```

---

### Task 5: Compose wiring — celery-ingest service + uvicorn workers

**Files:**
- Modify: `docker-compose.dev.yml`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add `celery-ingest` to `docker-compose.dev.yml`** (after the `celery-worker` service; mirror its block):

```yaml
  celery-ingest:
    build:
      context: ./backend
      dockerfile: Dockerfile.dev
    command: celery -A app.worker worker -Q ingest --concurrency=4 --loglevel=info
    env_file: .env
    volumes:
      - ./backend:/app
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - megoobug
```

- [ ] **Step 2: Add `celery-ingest` to `docker-compose.yml`** (after `celery-worker`; mirror its prod block):

```yaml
  celery-ingest:
    build:
      context: ./backend
      dockerfile: Dockerfile
    restart: unless-stopped
    command: celery -A app.worker worker -Q ingest --concurrency=4 --loglevel=info
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - megoobug
```

- [ ] **Step 3: Prod backend gets uvicorn workers** — in `docker-compose.yml`, the `backend` service has no `command:` (uses Dockerfile CMD). Add one:

```yaml
    # Multi-process serving; Dockerfile CMD remains the single-process fallback
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-2}
```

(dev compose unchanged — keeps single-process autoreload.)

- [ ] **Step 4: Validate + commit**

```bash
docker compose -f docker-compose.dev.yml config --quiet && docker compose -f docker-compose.yml config --quiet && echo valid
```
Expected: `valid` (env-var warnings OK).

```bash
git add docker-compose.dev.yml docker-compose.yml
git -c user.name="Mohamed M. Hammad" -c user.email="mohamed.magdy@slnee.com" commit -m "feat(ingest): dedicated celery-ingest service and prod uvicorn workers"
```

---

### Task 6: Manual end-to-end verification

**Files:** none

- [ ] **Step 1: Start the ingest worker + restart backend**

```bash
cd /opt/megoobug
docker compose -f docker-compose.dev.yml up -d celery-ingest
docker compose -f docker-compose.dev.yml restart backend celery-worker
sleep 12
docker compose -f docker-compose.dev.yml logs celery-ingest --tail 20
```
Expected: celery-ingest boots, `[queues]` shows `ingest`, task `ingest_event` registered.

- [ ] **Step 2: Single event end-to-end**

```bash
DSN_KEY=$(docker compose -f docker-compose.dev.yml exec -T postgres psql -U megoo -d megoobug -tAc "SELECT dsn_public_key FROM projects LIMIT 1")
EID=$(docker compose -f docker-compose.dev.yml exec -T backend python -c "import uuid;print(uuid.uuid4().hex)")
curl -s -X POST "http://localhost:8001/api/1/store/?sentry_key=$DSN_KEY" -H "Content-Type: application/json" -d "{\"event_id\":\"$EID\",\"message\":\"async pipeline check\",\"timestamp\":$(date +%s)}"
sleep 4
docker compose -f docker-compose.dev.yml exec -T postgres psql -U megoo -d megoobug -tAc "SELECT count(*) FROM events WHERE event_id = '$EID'"
```
Expected: curl returns `{"id":"<EID>"}` instantly; count = 1 after the worker processes it.

- [ ] **Step 3: Burst test — 200 events, all accepted fast**

```bash
time for i in $(seq 1 200); do
  curl -s -o /dev/null -X POST "http://localhost:8001/api/1/store/?sentry_key=$DSN_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"message\":\"burst $i $(date +%s%N)\",\"timestamp\":$(date +%s)}" &
done; wait
sleep 10
docker compose -f docker-compose.dev.yml exec -T postgres psql -U megoo -d megoobug -tAc "SELECT count(*) FROM events WHERE data->>'message' LIKE 'burst %'"
```
Expected: the 200 accepts complete in a few seconds total; after the sleep, count = 200 (queue drained).

- [ ] **Step 4: Worker-down resilience**

```bash
docker compose -f docker-compose.dev.yml stop celery-ingest
EID2=$(docker compose -f docker-compose.dev.yml exec -T backend python -c "import uuid;print(uuid.uuid4().hex)")
time curl -s -o /dev/null -w "%{http_code}\n" -X POST "http://localhost:8001/api/1/store/?sentry_key=$DSN_KEY" -H "Content-Type: application/json" -d "{\"event_id\":\"$EID2\",\"message\":\"worker down\",\"timestamp\":$(date +%s)}"
docker compose -f docker-compose.dev.yml start celery-ingest
sleep 10
docker compose -f docker-compose.dev.yml exec -T postgres psql -U megoo -d megoobug -tAc "SELECT count(*) FROM events WHERE event_id = '$EID2'"
```
Expected: 200 in milliseconds while the worker is down; count = 1 after restart (queued event processed).

- [ ] **Step 5: Final state**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest
git status && git log --oneline -6
```
Expected: 32 passed; clean tree; 5 commits on `feat/async-ingestion`.
