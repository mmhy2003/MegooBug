# Scheduled Retention Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nightly Celery-beat task that deletes ingested data older than `RETENTION_DAYS` (default 14) from Postgres and mirrors the deletions to Meilisearch.

**Architecture:** A pure async core `_cleanup(db, cutoff, batch_size)` does the Postgres work (delete stale issues — cascade removes their events; then batch-delete remaining old events with RETURNING ids) and is unit-tested against the real test database. A sync Celery task `cleanup_old_data` wraps it (fresh engine per run via `asyncio.run`), then best-effort deletes the same documents from Meilisearch. Celery beat runs embedded in the existing worker (`-B`).

**Tech Stack:** Celery 5.5 (beat crontab), SQLAlchemy 2.x async (asyncpg), meilisearch-python 0.33 (`delete_documents(filter=...)` supported), pytest scaffold from `backend/tests/`.

**Spec:** `docs/superpowers/specs/2026-06-10-retention-cleanup-design.md`

## File Structure

- Modify: `backend/app/config.py` — add `RETENTION_DAYS`.
- Modify: `.env.example` — document `RETENTION_DAYS`.
- Create: `backend/app/tasks/cleanup_tasks.py` — async core + Celery task + Meili mirror.
- Create: `backend/tests/test_cleanup.py` — tests for the core and the disabled no-op.
- Modify: `backend/app/worker.py` — include cleanup module, add `beat_schedule`.
- Modify: `docker-compose.dev.yml`, `docker-compose.yml` — worker command gets `-B`.

**How tests run** (dev stack must be up: `make dev` or `docker compose -f docker-compose.dev.yml up -d backend`):

```bash
docker compose -f docker-compose.dev.yml exec backend pytest
```

**Git identity note:** no global git identity on this machine — commit with:

```bash
git -c user.name="Mohamed M. Hammad" -c user.email="mohamed.magdy@slnee.com" commit -m "..."
```

**Branch:** work on `feat/retention-cleanup` branched from `main` (create it in Task 1; the dev Docker stack mounts `./backend` from this checkout, so do NOT use a separate worktree).

---

### Task 1: RETENTION_DAYS config

Pure configuration — no test of its own; Task 3's disabled-mode test exercises it via monkeypatch.

**Files:**
- Modify: `backend/app/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Create the branch**

```bash
cd /opt/megoobug && git checkout -b feat/retention-cleanup
```

- [ ] **Step 2: Add the setting to `backend/app/config.py`**

After the `# ── Meilisearch ──` block (lines 35–37) and before `# ── Seed Admin ──`, insert:

```python
    # ── Retention ──
    # Days to keep ingested events/issues. 0 or negative disables cleanup.
    RETENTION_DAYS: int = 14
```

- [ ] **Step 3: Add to `.env.example`**

After the `# ── Meilisearch ──` block, insert:

```
# ── Retention ──
# Days to keep ingested events/issues. 0 disables the nightly cleanup.
RETENTION_DAYS=14
```

- [ ] **Step 4: Sanity-check the setting loads**

```bash
docker compose -f docker-compose.dev.yml exec backend python -c "from app.config import settings; print(settings.RETENTION_DAYS)"
```

Expected: `14`

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py .env.example
git -c user.name="Mohamed M. Hammad" -c user.email="mohamed.magdy@slnee.com" commit -m "feat(retention): add RETENTION_DAYS setting (default 14, 0 disables)"
```

---

### Task 2: `_cleanup` async core (TDD)

The Postgres deletion logic, importable and testable without Celery or Meilisearch.

**Files:**
- Create: `backend/tests/test_cleanup.py`
- Create: `backend/app/tasks/cleanup_tasks.py` (core function only in this task)

- [ ] **Step 1: Write the failing tests `backend/tests/test_cleanup.py`**

Note: `Issue.last_seen` and `Event.timestamp` default to now, so tests set them explicitly. The conftest `db` fixture wraps each test in a rolled-back outer transaction; `_cleanup`'s internal `commit()` calls release savepoints inside it, so isolation holds.

```python
"""Tests for the retention cleanup core (Postgres only — no Celery, no Meilisearch)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.tasks.cleanup_tasks import _cleanup
from app.models.event import Event
from app.models.issue import Issue
from app.models.project import Project
from app.models.user import User

NOW = None  # set per-test from datetime.now


@pytest.fixture
async def project(db):
    user = User(email="retention@example.com", name="Retention", password_hash="x")
    db.add(user)
    await db.flush()
    proj = Project(
        name="Retention Proj",
        slug="retention-proj",
        dsn_public_key=uuid.uuid4().hex,
        created_by=user.id,
    )
    db.add(proj)
    await db.flush()
    return proj


async def _make_issue(db, project, fingerprint, last_seen):
    issue = Issue(
        project_id=project.id,
        title=f"Issue {fingerprint}",
        fingerprint=fingerprint,
        last_seen=last_seen,
    )
    db.add(issue)
    await db.flush()
    return issue


async def _make_event(db, issue, timestamp):
    event = Event(
        issue_id=issue.id,
        project_id=issue.project_id,
        event_id=uuid.uuid4().hex,
        data={},
        timestamp=timestamp,
    )
    db.add(event)
    await db.flush()
    return event


async def _count(db, model):
    return (await db.execute(select(func.count()).select_from(model))).scalar()


async def test_stale_issue_cascades(db, project):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=14)
    stale = await _make_issue(db, project, "stale-fp", last_seen=now - timedelta(days=30))
    await _make_event(db, stale, timestamp=now - timedelta(days=30))
    fresh = await _make_issue(db, project, "fresh-fp", last_seen=now)
    await _make_event(db, fresh, timestamp=now)

    summary = await _cleanup(db, cutoff)

    assert summary["issues_deleted"] == 1
    assert stale.id in summary["stale_issue_ids"]
    remaining_issues = (await db.execute(select(Issue.id))).scalars().all()
    assert remaining_issues == [fresh.id]
    # stale issue's event went away via cascade; fresh event survives
    remaining_events = (await db.execute(select(Event.issue_id))).scalars().all()
    assert remaining_events == [fresh.id]


async def test_active_issue_keeps_recent_events(db, project):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=14)
    issue = await _make_issue(db, project, "active-fp", last_seen=now)
    old_event = await _make_event(db, issue, timestamp=now - timedelta(days=30))
    new_event = await _make_event(db, issue, timestamp=now)

    summary = await _cleanup(db, cutoff)

    assert summary["issues_deleted"] == 0
    assert summary["events_deleted"] == 1
    assert old_event.id in summary["deleted_event_ids"]
    remaining = (await db.execute(select(Event.id))).scalars().all()
    assert remaining == [new_event.id]


async def test_cutoff_boundary_keeps_newer_events(db, project):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=14)
    issue = await _make_issue(db, project, "boundary-fp", last_seen=now)
    await _make_event(db, issue, timestamp=cutoff + timedelta(seconds=1))

    summary = await _cleanup(db, cutoff)

    assert summary["events_deleted"] == 0
    assert await _count(db, Event) == 1


async def test_batching_terminates_and_deletes_all(db, project):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=14)
    issue = await _make_issue(db, project, "batch-fp", last_seen=now)
    for _ in range(3):
        await _make_event(db, issue, timestamp=now - timedelta(days=30))

    summary = await _cleanup(db, cutoff, batch_size=1)

    assert summary["events_deleted"] == 3
    assert await _count(db, Event) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/test_cleanup.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'app.tasks.cleanup_tasks'`.

- [ ] **Step 3: Create `backend/app/tasks/cleanup_tasks.py` with the core only**

```python
"""Retention cleanup: delete ingested data older than RETENTION_DAYS.

The async core (`_cleanup`) touches Postgres only and is unit-tested.
The Celery task wrapper and the Meilisearch mirror live in this module too
(added alongside) but stay out of the core so tests need neither Celery nor
Meilisearch.
"""
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.issue import Issue
from app.logging import get_logger

logger = get_logger("tasks.cleanup")


async def _cleanup(db: AsyncSession, cutoff: datetime, batch_size: int = 5000) -> dict:
    """Delete stale issues (cascades to their events) and old events.

    Postgres is the source of truth and is cleaned first; each batch commits
    independently so an interrupted run loses nothing.
    Returns ids so the caller can mirror deletions to Meilisearch.
    """
    stale_result = await db.execute(select(Issue.id).where(Issue.last_seen < cutoff))
    stale_issue_ids = list(stale_result.scalars().all())
    if stale_issue_ids:
        await db.execute(delete(Issue).where(Issue.id.in_(stale_issue_ids)))
        await db.commit()
        logger.info("Retention: deleted %d stale issues", len(stale_issue_ids))

    deleted_event_ids = []
    while True:
        result = await db.execute(
            delete(Event)
            .where(
                Event.id.in_(
                    select(Event.id).where(Event.timestamp < cutoff).limit(batch_size)
                )
            )
            .returning(Event.id)
        )
        batch = list(result.scalars().all())
        await db.commit()
        if not batch:
            break
        deleted_event_ids.extend(batch)
        if len(batch) < batch_size:
            break

    if deleted_event_ids:
        logger.info("Retention: deleted %d old events", len(deleted_event_ids))

    return {
        "stale_issue_ids": stale_issue_ids,
        "deleted_event_ids": deleted_event_ids,
        "issues_deleted": len(stale_issue_ids),
        "events_deleted": len(deleted_event_ids),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/test_cleanup.py -v
```

Expected: 4 passed (and the full suite `pytest` shows 11 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_cleanup.py backend/app/tasks/cleanup_tasks.py
git -c user.name="Mohamed M. Hammad" -c user.email="mohamed.magdy@slnee.com" commit -m "feat(retention): add _cleanup core deleting stale issues and old events"
```

---

### Task 3: `cleanup_old_data` Celery task + Meilisearch mirror (TDD for the disabled no-op)

**Files:**
- Modify: `backend/tests/test_cleanup.py` (append one test)
- Modify: `backend/app/tasks/cleanup_tasks.py` (append wrapper + mirror)

- [ ] **Step 1: Append the failing test to `backend/tests/test_cleanup.py`**

```python
def test_cleanup_old_data_disabled_noops(monkeypatch):
    """RETENTION_DAYS<=0 must short-circuit before touching DB or Meilisearch."""
    from app.config import settings
    from app.tasks.cleanup_tasks import cleanup_old_data

    monkeypatch.setattr(settings, "RETENTION_DAYS", 0)
    result = cleanup_old_data.run()
    assert result == {"issues_deleted": 0, "events_deleted": 0, "skipped": True}
```

- [ ] **Step 2: Run it to verify it fails**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/test_cleanup.py::test_cleanup_old_data_disabled_noops -v
```

Expected: FAIL — `ImportError: cannot import name 'cleanup_old_data'`.

- [ ] **Step 3: Append wrapper + mirror to `backend/app/tasks/cleanup_tasks.py`**

Add these imports at the top of the file (merge with existing ones):

```python
import asyncio
from datetime import timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.worker import celery_app
```

Append at the end of the file:

```python
async def _run_cleanup(cutoff: datetime) -> dict:
    """Run _cleanup with a fresh engine — the app's global engine must not
    cross the Celery worker process boundary."""
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            return await _cleanup(db, cutoff)
    finally:
        await engine.dispose()


def _mirror_to_meilisearch(summary: dict) -> None:
    """Best-effort removal of deleted rows from the search indexes.

    Failures are logged and swallowed (same pattern as the indexing tasks);
    a later reindex_all self-heals search.
    """
    try:
        import meilisearch

        client = meilisearch.Client(
            settings.MEILISEARCH_URL,
            settings.MEILISEARCH_MASTER_KEY,
        )

        stale_ids = [str(i) for i in summary["stale_issue_ids"]]
        if stale_ids:
            client.index("issues").delete_documents(stale_ids)
            # Events of stale issues were cascade-deleted in Postgres without
            # RETURNING; remove them from search by filter (issue_id is filterable).
            quoted = ", ".join(f'"{i}"' for i in stale_ids)
            client.index("events").delete_documents(filter=f"issue_id IN [{quoted}]")

        event_ids = [str(e) for e in summary["deleted_event_ids"]]
        if event_ids:
            client.index("events").delete_documents(event_ids)
    except Exception as e:
        logger.error("Retention: Meilisearch mirror failed (search will self-heal on reindex): %s", e)


@celery_app.task(name="cleanup_old_data")
def cleanup_old_data() -> dict:
    """Nightly retention: drop ingested data older than RETENTION_DAYS."""
    if settings.RETENTION_DAYS <= 0:
        logger.info("Retention disabled (RETENTION_DAYS=%s), skipping", settings.RETENTION_DAYS)
        return {"issues_deleted": 0, "events_deleted": 0, "skipped": True}

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.RETENTION_DAYS)
    summary = asyncio.run(_run_cleanup(cutoff))
    _mirror_to_meilisearch(summary)

    logger.info(
        "Retention run complete: %d issues, %d events deleted (cutoff %s)",
        summary["issues_deleted"], summary["events_deleted"], cutoff.isoformat(),
    )
    return {
        "issues_deleted": summary["issues_deleted"],
        "events_deleted": summary["events_deleted"],
    }
```

- [ ] **Step 4: Run the full suite**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest -v
```

Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_cleanup.py backend/app/tasks/cleanup_tasks.py
git -c user.name="Mohamed M. Hammad" -c user.email="mohamed.magdy@slnee.com" commit -m "feat(retention): add cleanup_old_data Celery task with Meilisearch mirror"
```

---

### Task 4: Beat schedule + worker wiring + compose `-B`

**Files:**
- Modify: `backend/app/worker.py`
- Modify: `docker-compose.dev.yml` (celery-worker `command:`)
- Modify: `docker-compose.yml` (celery-worker `command:`, line 71)

- [ ] **Step 1: Wire the module and schedule in `backend/app/worker.py`**

Add the import at the top:

```python
from celery.schedules import crontab
```

Replace the include block at the bottom:

```python
# Register task modules explicitly
celery_app.conf.include = [
    "app.tasks.event_tasks",
    "app.tasks.cleanup_tasks",
]

# Periodic tasks (beat runs embedded in the worker via `-B`)
celery_app.conf.beat_schedule = {
    "cleanup-old-data-daily": {
        "task": "cleanup_old_data",
        "schedule": crontab(hour=3, minute=0),  # daily, 03:00 UTC
    },
}
```

- [ ] **Step 2: Update both compose files**

In `docker-compose.dev.yml`, the `celery-worker` service:

```yaml
    # -B embeds the beat scheduler — move beat to its own service if workers scale beyond one
    command: celery -A app.worker worker -B --loglevel=info
```

In `docker-compose.yml` (line 71), same replacement:

```yaml
    # -B embeds the beat scheduler — move beat to its own service if workers scale beyond one
    command: celery -A app.worker worker -B --loglevel=info
```

- [ ] **Step 3: Verify the schedule registers**

```bash
docker compose -f docker-compose.dev.yml exec backend python -c "
from app.worker import celery_app
assert 'app.tasks.cleanup_tasks' in celery_app.conf.include
print(celery_app.conf.beat_schedule)"
```

Expected: dict containing `cleanup-old-data-daily` with task `cleanup_old_data`.

- [ ] **Step 4: Run the full suite (regression)**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest
```

Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/worker.py docker-compose.dev.yml docker-compose.yml
git -c user.name="Mohamed M. Hammad" -c user.email="mohamed.magdy@slnee.com" commit -m "feat(retention): schedule cleanup_old_data daily via celery beat (-B on worker)"
```

---

### Task 5: Manual end-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Start the worker (it isn't running in the current dev stack)**

```bash
cd /opt/megoobug
docker compose -f docker-compose.dev.yml up -d celery-worker
docker compose -f docker-compose.dev.yml logs celery-worker --tail 20
```

Expected: worker boots, log shows `beat: Starting...` and the registered task `cleanup_old_data`. (If the container fails on Redis/Meili, check those services are healthy.)

- [ ] **Step 2: Seed old + new data in the dev DB**

```bash
docker compose -f docker-compose.dev.yml exec -T backend python - <<'EOF'
import asyncio, uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.database import async_session_factory
from app.models.user import User
from app.models.project import Project
from app.models.issue import Issue
from app.models.event import Event

async def main():
    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        user = (await db.execute(select(User))).scalars().first()
        proj = (await db.execute(select(Project).where(Project.slug == "webmail-backend"))).scalar_one()
        old_issue = Issue(project_id=proj.id, title="Old stale issue", fingerprint="retention-old",
                          last_seen=now - timedelta(days=30))
        db.add(old_issue); await db.flush()
        db.add(Event(issue_id=old_issue.id, project_id=proj.id, event_id=uuid.uuid4().hex,
                     data={}, timestamp=now - timedelta(days=30)))
        await db.commit()
        print("seeded old issue", old_issue.id)

asyncio.run(main())
EOF
```

- [ ] **Step 3: Invoke the task once and check the result**

```bash
docker compose -f docker-compose.dev.yml exec celery-worker celery -A app.worker call cleanup_old_data
sleep 5
docker compose -f docker-compose.dev.yml logs celery-worker --tail 10
```

Expected: log line `Retention run complete: 1 issues, ... events deleted`.

- [ ] **Step 4: Confirm in Postgres**

```bash
docker compose -f docker-compose.dev.yml exec postgres psql -U megoo -d megoobug -c \
  "SELECT count(*) FROM issues WHERE fingerprint = 'retention-old';"
```

Expected: `0`. Also confirm the recent verification issue (`verify-fp`) still exists:

```bash
docker compose -f docker-compose.dev.yml exec postgres psql -U megoo -d megoobug -c \
  "SELECT count(*) FROM issues WHERE fingerprint = 'verify-fp';"
```

Expected: `1`.

- [ ] **Step 5: Confirm clean git state**

```bash
git status && git log --oneline -5
```

Expected: clean tree, the four task commits on `feat/retention-cleanup`.
