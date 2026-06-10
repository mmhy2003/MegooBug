# Sentry MCP Event Lookup 404 Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the Sentry-compat API so event lookups by Sentry hex `eventID` (32-char dashless hex) resolve correctly instead of returning 404, unblocking the Sentry MCP's `get_sentry_resource` / `getEventForIssue` tools.

**Architecture:** Python's `uuid.UUID()` accepts dashless hex, so Sentry event IDs incorrectly take the "internal PK" lookup branch and never match. We add one shared async helper `find_event()` in a new module that matches `Event.event_id == raw_id OR Event.id == UUID(raw_id)` in a single query, and wire it into both affected endpoints. Tests run against the dev-stack Postgres (models use Postgres-only `UUID`/`JSONB` types) in a dedicated `megoobug_test` database created/dropped by a conftest fixture.

**Tech Stack:** FastAPI, SQLAlchemy 2.x async (asyncpg), pytest + pytest-asyncio 0.26, Postgres 16 via `docker-compose.dev.yml`.

**Spec:** `docs/superpowers/specs/2026-06-10-sentry-mcp-event-lookup-design.md`

## File Structure

- Create: `backend/pytest.ini` — pytest + pytest-asyncio configuration.
- Create: `backend/tests/__init__.py` — empty package marker.
- Create: `backend/tests/conftest.py` — test-DB lifecycle (create/drop `megoobug_test`) and per-test rollback session.
- Create: `backend/tests/test_infra.py` — sanity test that the test DB works.
- Create: `backend/tests/test_event_lookup.py` — focused tests for `find_event`.
- Create: `backend/app/api/sentry_compat/event_lookup.py` — the shared `find_event()` helper (its own module because both route files need it and neither should import from the other).
- Modify: `backend/app/api/sentry_compat/organizations.py:586-620` — `get_org_issue_event` uses the helper.
- Modify: `backend/app/api/sentry_compat/issues.py:150-165` — `get_event` accepts `str` and uses the helper.

**How tests run:** inside the backend container, where Postgres is reachable at host `postgres` (this is what `make test-be` does):

```bash
docker compose -f docker-compose.dev.yml exec backend pytest
```

The dev stack must be up first: `make dev` (from repo root `/opt/megoobug`).

**Git identity note:** this machine has no global git identity configured. Commit with the repo's existing author identity:

```bash
git -c user.name="Mohamed M. Hammad" -c user.email="mohamed.magdy@slnee.com" commit -m "..."
```

---

### Task 1: Test infrastructure (pytest config + Postgres test database)

The repo has pytest in `requirements.txt` but no tests directory, no pytest config, and no fixtures. This task creates the minimal scaffold and proves it works with a sanity test.

**Files:**
- Create: `backend/pytest.ini`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_infra.py`

- [ ] **Step 1: Create `backend/pytest.ini`**

`asyncio_mode = auto` lets us write plain `async def test_*` functions without decorators. Both loop scopes are set to `session` so the session-scoped engine fixture and function-scoped tests share one event loop (asyncpg connections are bound to the loop they were created on).

```ini
[pytest]
testpaths = tests
asyncio_mode = auto
asyncio_default_fixture_loop_scope = session
asyncio_default_test_loop_scope = session
```

- [ ] **Step 2: Create `backend/tests/__init__.py`**

Empty file:

```python
```

- [ ] **Step 3: Create `backend/tests/conftest.py`**

`CREATE DATABASE` / `DROP DATABASE` cannot run inside a transaction, hence the `AUTOCOMMIT` admin engine. The `db` fixture wraps each test in a transaction on a single connection and rolls it back, so tests never pollute each other. `import app.models` registers every model on `Base.metadata` so `create_all` builds the full schema (FKs included).

```python
"""Shared test fixtures: dedicated Postgres test database + rollback sessions.

Tests run inside the backend container (see `make test-be`), where the
dev-stack Postgres is reachable at host `postgres`. The test database
`megoobug_test` is created from scratch at session start and dropped at
session end — it never touches the dev `megoobug` database.
"""
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import settings
from app.database import Base
import app.models  # noqa: F401 — register all models on Base.metadata

TEST_DB_NAME = "megoobug_test"
# Reuse the app's DSN (user/password/host), swap only the database name.
ADMIN_URL = settings.DATABASE_URL
TEST_URL = ADMIN_URL.rsplit("/", 1)[0] + f"/{TEST_DB_NAME}"


async def _run_admin_sql(*statements: str) -> None:
    """Run statements outside a transaction (needed for CREATE/DROP DATABASE)."""
    admin = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            for stmt in statements:
                await conn.execute(text(stmt))
    finally:
        await admin.dispose()


@pytest.fixture(scope="session")
async def db_engine():
    await _run_admin_sql(
        f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)",
        f"CREATE DATABASE {TEST_DB_NAME}",
    )
    engine = create_async_engine(TEST_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()
    await _run_admin_sql(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)")


@pytest.fixture
async def db(db_engine):
    """A session inside a transaction that is rolled back after each test."""
    async with db_engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()
```

- [ ] **Step 4: Create the sanity test `backend/tests/test_infra.py`**

```python
"""Sanity check that the test database scaffold works."""
from sqlalchemy import text


async def test_db_connects(db):
    result = await db.execute(text("SELECT 1"))
    assert result.scalar() == 1


async def test_schema_created(db):
    result = await db.execute(text("SELECT count(*) FROM events"))
    assert result.scalar() == 0
```

- [ ] **Step 5: Start the dev stack (if not already running) and run the tests**

```bash
cd /opt/megoobug && make dev
docker compose -f docker-compose.dev.yml exec backend pytest tests/test_infra.py -v
```

Expected: both tests PASS. If `DROP DATABASE ... WITH (FORCE)` errors (needs Postgres 13+; dev stack is 16, so it shouldn't), check the Postgres container version.

- [ ] **Step 6: Commit**

```bash
cd /opt/megoobug
git add backend/pytest.ini backend/tests/
git commit -m "test: add pytest scaffold with Postgres test database fixtures"
```

---

### Task 2: `find_event` helper (TDD)

The core fix: a single-query lookup that matches the Sentry hex `eventID` column OR the internal UUID PK, with an optional issue filter.

**Files:**
- Create: `backend/tests/test_event_lookup.py`
- Create: `backend/app/api/sentry_compat/event_lookup.py`

- [ ] **Step 1: Write the failing tests `backend/tests/test_event_lookup.py`**

The seed fixture builds the full FK chain (user → project → issues → events) because the schema enforces non-null FKs. `31472ffb67c14b8d85ceb68f067146ae` is the exact ID format from the bug report: 32-char dashless hex, which `uuid.UUID()` happily parses — that's the regression being pinned down.

```python
"""Tests for the shared sentry_compat event lookup helper."""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.sentry_compat.event_lookup import find_event
from app.models.event import Event
from app.models.issue import Issue
from app.models.project import Project
from app.models.user import User

SENTRY_HEX_ID = "31472ffb67c14b8d85ceb68f067146ae"
OTHER_HEX_ID = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


@pytest.fixture
async def seeded(db):
    now = datetime.now(timezone.utc)
    user = User(email="tester@example.com", name="Tester", password_hash="x")
    db.add(user)
    await db.flush()

    project = Project(
        name="Webmail Backend",
        slug="webmail-backend",
        dsn_public_key=uuid.uuid4().hex,
        created_by=user.id,
    )
    db.add(project)
    await db.flush()

    issue = Issue(project_id=project.id, title="Boom", fingerprint="fp-1")
    other_issue = Issue(project_id=project.id, title="Other", fingerprint="fp-2")
    db.add_all([issue, other_issue])
    await db.flush()

    event = Event(
        issue_id=issue.id,
        project_id=project.id,
        event_id=SENTRY_HEX_ID,
        data={},
        timestamp=now,
    )
    other_event = Event(
        issue_id=other_issue.id,
        project_id=project.id,
        event_id=OTHER_HEX_ID,
        data={},
        timestamp=now,
    )
    db.add_all([event, other_event])
    await db.flush()
    return SimpleNamespace(issue=issue, other_issue=other_issue, event=event)


async def test_finds_by_sentry_hex_id(db, seeded):
    """The bug from the report: a dashless-hex Sentry eventID parses as a
    UUID, so the old code compared it against the internal PK and 404'd."""
    found = await find_event(db, SENTRY_HEX_ID)
    assert found is not None
    assert found.id == seeded.event.id


async def test_finds_by_internal_uuid(db, seeded):
    found = await find_event(db, str(seeded.event.id))
    assert found is not None
    assert found.event_id == SENTRY_HEX_ID


async def test_unknown_id_returns_none(db, seeded):
    assert await find_event(db, "deadbeefdeadbeefdeadbeefdeadbeef") is None


async def test_non_uuid_garbage_returns_none(db, seeded):
    assert await find_event(db, "not-an-id") is None


async def test_issue_filter_scopes_lookup(db, seeded):
    found = await find_event(db, SENTRY_HEX_ID, issue_id=seeded.issue.id)
    assert found is not None

    # Same event, wrong issue → not found
    assert await find_event(db, SENTRY_HEX_ID, issue_id=seeded.other_issue.id) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/test_event_lookup.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'app.api.sentry_compat.event_lookup'`.

- [ ] **Step 3: Create `backend/app/api/sentry_compat/event_lookup.py`**

`scalars().first()` (not `scalar_one_or_none()`) so a freak collision between one row's hex `event_id` and another row's PK can't raise `MultipleResultsFound`.

```python
"""Shared event lookup for the Sentry-compat routes.

Sentry event IDs are 32-char dashless hex strings, which `uuid.UUID()`
happily parses — so routes must NOT branch on UUID-parseability to decide
which column to query. This helper matches both columns in one query.
"""
import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event


async def find_event(
    db: AsyncSession,
    raw_id: str,
    issue_id: uuid.UUID | None = None,
) -> Event | None:
    """Find an event by Sentry hex eventID or internal UUID primary key.

    Optionally scope the lookup to a single issue.
    """
    conds = [Event.event_id == raw_id]
    try:
        conds.append(Event.id == uuid.UUID(raw_id))
    except ValueError:
        pass

    q = select(Event).where(or_(*conds))
    if issue_id is not None:
        q = q.where(Event.issue_id == issue_id)

    result = await db.execute(q)
    return result.scalars().first()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/test_event_lookup.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /opt/megoobug
git add backend/tests/test_event_lookup.py backend/app/api/sentry_compat/event_lookup.py
git commit -m "feat(sentry-compat): add find_event helper matching hex eventID or internal UUID"
```

---

### Task 3: Wire `find_event` into `get_org_issue_event` (the endpoint the MCP hit)

**Files:**
- Modify: `backend/app/api/sentry_compat/organizations.py:586-620`

- [ ] **Step 1: Add the import**

In `backend/app/api/sentry_compat/organizations.py`, with the other `app.` imports near the top of the file, add:

```python
from app.api.sentry_compat.event_lookup import find_event
```

- [ ] **Step 2: Replace the lookup in `get_org_issue_event`**

Replace the body after `issue = await _resolve_issue(...)` (currently lines 597–620, the `if event_id == "latest": ... else: try/except UUID ...` block through `return _event_to_sentry(event)`) with:

```python
    if event_id == "latest":
        result = await db.execute(
            select(Event)
            .where(Event.issue_id == issue.id)
            .order_by(Event.timestamp.desc())
            .limit(1)
        )
        event = result.scalar_one_or_none()
    else:
        event = await find_event(db, event_id, issue_id=issue.id)

    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return _event_to_sentry(event)
```

The `"latest"` special case is unchanged. Do not remove `from uuid import UUID` from the file's imports — `_resolve_issue` still uses it.

- [ ] **Step 3: Run the full test suite (regression check)**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
cd /opt/megoobug
git add backend/app/api/sentry_compat/organizations.py
git commit -m "fix(sentry-compat): resolve events by hex eventID in org issue event endpoint"
```

---

### Task 4: Fix `get_event` in `issues.py` (same bug class)

**Files:**
- Modify: `backend/app/api/sentry_compat/issues.py:150-165`

- [ ] **Step 1: Add the import**

In `backend/app/api/sentry_compat/issues.py`, with the other `app.` imports, add:

```python
from app.api.sentry_compat.event_lookup import find_event
```

- [ ] **Step 2: Replace the `get_event` handler**

Replace the whole handler (lines 150–165) — the path param becomes `str` (it was `UUID`, which both 422'd on some inputs and only ever queried the PK):

```python
@router.get("/events/{event_id}/")
async def get_event(
    event_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get a single event by its Sentry eventID or internal ID."""
    event = await find_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if not await check_project_access(current_user, event.project_id, db):
        raise HTTPException(status_code=404, detail="Event not found")
    return _event_to_sentry(event)
```

Keep `from uuid import UUID` in the file's imports — the other issue routes still use UUID-typed params.

- [ ] **Step 3: Run the full test suite**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
cd /opt/megoobug
git add backend/app/api/sentry_compat/issues.py
git commit -m "fix(sentry-compat): accept hex eventID in GET /api/0/events/{event_id}/"
```

---

### Task 5: Manual end-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Make sure the dev stack picked up the changes**

The backend dev container mounts `./backend` and runs with autoreload, so the code is already live. Confirm it's healthy:

```bash
docker compose -f docker-compose.dev.yml ps
docker compose -f docker-compose.dev.yml logs backend --tail 20
```

Expected: backend running, no tracebacks in recent logs.

- [ ] **Step 2: Grab a real issue shortId and event hex ID from the dev DB**

```bash
docker compose -f docker-compose.dev.yml exec postgres psql -U megoo -d megoobug -c \
  "SELECT p.slug, i.issue_number, e.event_id FROM events e \
   JOIN issues i ON i.id = e.issue_id JOIN projects p ON p.id = e.project_id LIMIT 3;"
```

Expected: rows like `webmail-backend | 2954 | 31472ffb67c14b8d85ceb68f067146ae`.

- [ ] **Step 3: Hit the previously-failing endpoint with curl**

Use an API token (the same one the Sentry MCP is configured with, or create one in the MegooBug UI under API tokens). With values from Step 2:

```bash
TOKEN="<api token>"
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/0/organizations/megoobug/issues/<SLUG-UPPER>-<issue_number>/events/<event_id>/"
```

(Adjust the port if the backend publishes a different one — check `docker compose -f docker-compose.dev.yml ps backend`.)

Expected: `200`. Before the fix this returned `404`.

- [ ] **Step 4: Re-run the original Sentry MCP call**

Ask the user to re-run the MCP tool that originally failed (`get_sentry_resource` for an event on `webmail-backend`). Expected: event details returned, no "Event not found".

- [ ] **Step 5: Final commit check**

```bash
cd /opt/megoobug && git status && git log --oneline -5
```

Expected: clean working tree; the three fix/test commits from Tasks 1–4 on top.
