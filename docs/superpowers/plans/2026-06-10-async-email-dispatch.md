# Async Email Dispatch Implementation Plan (pool exhaustion fix)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move all SMTP email sending off the API request path into Celery tasks so slow mail servers can never exhaust the DB connection pool again.

**Architecture:** New `app/tasks/email_tasks.py` with two fire-once Celery tasks (`send_issue_emails`, `send_invite_email`) that load SMTP config themselves (sync engine read of the settings table, env fallback — credentials never travel through the broker) and reuse the existing HTML builders + sync `_send()`. Call sites (`_create_notifications` in ingest, invite creation) build JSON payloads and `.delay()` them inside try/except so a dead broker can't fail a request. The old inline async senders are deleted. `pool_pre_ping=True` rides along on the engine.

**Tech Stack:** Celery 5.5, smtplib (existing `_send`), SQLAlchemy sync engine via psycopg2-binary (already installed, same pattern as `reindex_all`), pytest scaffold in `backend/tests/`.

**Spec:** `docs/superpowers/specs/2026-06-10-async-email-dispatch-design.md`

## File Structure

- Modify: `backend/app/database.py` — `pool_pre_ping=True`.
- Create: `backend/app/tasks/email_tasks.py` — the two tasks + sync SMTP config loader.
- Modify: `backend/app/worker.py` — add module to `include`.
- Modify: `backend/app/services/email.py` — add `_env_smtp_config()`; delete async senders + `_get_smtp_config`; keep builders/`_send`.
- Modify: `backend/app/services/ingest.py` — import task in the `_HAS_TASKS` block; replace inline email loop with guarded `.delay()`.
- Modify: `backend/app/api/v1/invites.py` — guarded `.delay()` instead of `await send_invite_email`; add a logger.
- Modify: `backend/app/api/v1/projects.py` — remove the DEAD `from app.services.email import send_invite_email` block (~line 319–326: it imports then `pass`es; nothing is sent there today).
- Create: `backend/tests/test_email_tasks.py`.

**How tests run** (dev stack must be up):

```bash
docker compose -f docker-compose.dev.yml exec backend pytest
```

Current suite: 14 passed. After this plan: 19 passed.

**Git identity note:** no global git identity on this machine — commit with:

```bash
git -c user.name="Mohamed M. Hammad" -c user.email="mohamed.magdy@slnee.com" commit -m "..."
```

**Branch:** `fix/async-email-dispatch` from `main`, created in Task 1. Do NOT use a worktree (the dev Docker stack bind-mounts `./backend` from this checkout).

---

### Task 1: Branch + `pool_pre_ping`

**Files:**
- Modify: `backend/app/database.py:6-11`

- [ ] **Step 1: Create the branch**

```bash
cd /opt/megoobug && git checkout -b fix/async-email-dispatch
```

- [ ] **Step 2: Add `pool_pre_ping` to the engine**

In `backend/app/database.py`, change:

```python
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ENVIRONMENT == "development",
    pool_size=20,
    max_overflow=10,
)
```

to:

```python
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ENVIRONMENT == "development",
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)
```

- [ ] **Step 3: Run the suite (regression)**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest
```

Expected: 14 passed.

- [ ] **Step 4: Commit**

```bash
git add backend/app/database.py
git -c user.name="Mohamed M. Hammad" -c user.email="mohamed.magdy@slnee.com" commit -m "fix(db): enable pool_pre_ping to drop stale pooled connections"
```

---

### Task 2: `email_tasks.py` — the two Celery tasks (TDD)

**Files:**
- Create: `backend/tests/test_email_tasks.py`
- Create: `backend/app/tasks/email_tasks.py`
- Modify: `backend/app/services/email.py` (add `_env_smtp_config` only — deletions happen in Task 3)
- Modify: `backend/app/worker.py` (include list)

- [ ] **Step 1: Write the failing tests `backend/tests/test_email_tasks.py`**

```python
"""Tests for the Celery email tasks (no real SMTP, no broker)."""
import pytest


ISSUE_PAYLOAD = {
    "emails": ["a@example.com", "b@example.com"],
    "project_name": "Webmail Backend",
    "project_slug": "webmail-backend",
    "issue_id": "0dcae490-c3e2-4b5e-86b8-98e5f7e3ad10",
    "issue_title": "ZeroDivisionError: division by zero",
    "issue_level": "error",
    "is_regression": False,
    "event_count": 3,
    "environment": "production",
}


def test_send_issue_emails_noops_without_smtp(monkeypatch):
    from app.tasks import email_tasks

    monkeypatch.setattr(email_tasks, "_load_smtp_config", lambda: None)

    def _must_not_send(*args, **kwargs):
        raise AssertionError("_send must not be called without SMTP config")

    monkeypatch.setattr(email_tasks, "_send", _must_not_send)
    result = email_tasks.send_issue_emails.run(ISSUE_PAYLOAD)
    assert result == {"sent": 0, "failed": 0, "skipped": True}


def test_send_issue_emails_continues_after_failure(monkeypatch):
    from app.tasks import email_tasks

    monkeypatch.setattr(
        email_tasks, "_load_smtp_config",
        lambda: {"host": "smtp.example.com", "port": 587, "from_email": "x@example.com"},
    )

    attempted = []

    def _send_first_fails(cfg, to, subject, html_body, text_body):
        attempted.append(to)
        if to == "a@example.com":
            raise RuntimeError("smtp boom")

    monkeypatch.setattr(email_tasks, "_send", _send_first_fails)
    result = email_tasks.send_issue_emails.run(ISSUE_PAYLOAD)
    assert attempted == ["a@example.com", "b@example.com"]
    assert result == {"sent": 1, "failed": 1}


def test_send_invite_email_noops_without_smtp(monkeypatch):
    from app.tasks import email_tasks

    monkeypatch.setattr(email_tasks, "_load_smtp_config", lambda: None)

    def _must_not_send(*args, **kwargs):
        raise AssertionError("_send must not be called without SMTP config")

    monkeypatch.setattr(email_tasks, "_send", _must_not_send)
    result = email_tasks.send_invite_email.run({
        "to_email": "new@example.com",
        "invite_token": "tok123",
        "role": "developer",
        "invited_by_name": "Admin",
    })
    assert result == {"sent": 0, "skipped": True}
```

- [ ] **Step 2: Run to verify failure**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/test_email_tasks.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'app.tasks.email_tasks'`.

- [ ] **Step 3: Add `_env_smtp_config()` to `backend/app/services/email.py`**

Insert directly ABOVE the existing `async def _get_smtp_config(...)` (do not delete anything yet):

```python
def _env_smtp_config() -> dict | None:
    """SMTP config from environment variables, or None if not configured."""
    if not app_settings.SMTP_HOST:
        return None
    return {
        "host": app_settings.SMTP_HOST,
        "port": app_settings.SMTP_PORT,
        "username": app_settings.SMTP_USERNAME,
        "password": app_settings.SMTP_PASSWORD,
        "from_email": app_settings.SMTP_FROM_EMAIL or "noreply@megoobug.local",
        "use_tls": app_settings.SMTP_USE_TLS,
    }
```

- [ ] **Step 4: Create `backend/app/tasks/email_tasks.py`**

```python
"""Celery tasks for sending emails off the request path.

Emails were previously sent inline during ingest/invite requests, holding
the request's pooled DB connection through slow SMTP I/O — under an error
storm this exhausted the API's connection pool (the 2026-06 production
incident). These tasks run on the worker: fire once, log failures, no
retries. SMTP credentials are loaded here (DB settings → env fallback),
never passed through the broker.
"""
from app.worker import celery_app
from app.config import settings
from app.logging import get_logger
from app.services.email import (
    _build_invite_html,
    _build_issue_notification_html,
    _env_smtp_config,
    _send,
)

logger = get_logger("tasks.email")


def _load_smtp_config() -> dict | None:
    """SMTP config from the settings table (sync engine), env fallback.

    Sync counterpart of the API's old _get_smtp_config — Celery tasks run
    outside the async event loop (same pattern as reindex_all).
    """
    try:
        from sqlalchemy import create_engine, text

        sync_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        engine = create_engine(sync_url)
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT value FROM settings WHERE key = 'smtp'")
                ).fetchone()
        finally:
            engine.dispose()
        if row and row[0] and row[0].get("host"):
            return row[0]
    except Exception:
        logger.warning("Could not read SMTP settings from DB, falling back to env", exc_info=True)

    return _env_smtp_config()


@celery_app.task(name="send_issue_emails")
def send_issue_emails(payload: dict) -> dict:
    """Send new-issue/regression notification emails to project members."""
    emails = payload.get("emails", [])
    cfg = _load_smtp_config()
    if cfg is None:
        logger.debug("SMTP not configured — skipping %d issue emails", len(emails))
        return {"sent": 0, "failed": 0, "skipped": True}

    app_url = settings.APP_URL.rstrip("/")
    app_name = settings.APP_NAME
    issue_link = f"{app_url}/projects/{payload['project_slug']}/issues/{payload['issue_id']}"
    is_regression = bool(payload.get("is_regression"))
    type_label = "Regression" if is_regression else "New Issue"
    subject = f"[{payload['project_name']}] {type_label}: {payload['issue_title'][:100]}"
    environment = payload.get("environment", "")

    text_body = (
        f"{type_label} in {payload['project_name']}\n\n"
        f"Level: {payload['issue_level'].upper()}\n"
        f"Title: {payload['issue_title']}\n"
        f"Events: {payload.get('event_count', 1)}\n"
        + (f"Environment: {environment}\n" if environment else "")
        + f"\nView issue: {issue_link}\n\n"
        f"— {app_name}"
    )
    html_body = _build_issue_notification_html(
        app_name=app_name,
        project_name=payload["project_name"],
        issue_title=payload["issue_title"],
        issue_level=payload["issue_level"],
        issue_link=issue_link,
        is_regression=is_regression,
        event_count=payload.get("event_count", 1),
        environment=environment,
    )

    sent = failed = 0
    for to_email in emails:
        try:
            _send(cfg, to_email, subject, html_body, text_body)
            sent += 1
        except Exception as e:
            failed += 1
            logger.error("Failed to send issue email to %s: %s", to_email, e)

    logger.info(
        "Issue emails: %d sent, %d failed (issue=%s)",
        sent, failed, payload["issue_id"][:8],
    )
    return {"sent": sent, "failed": failed}


@celery_app.task(name="send_invite_email")
def send_invite_email(payload: dict) -> dict:
    """Send a team invite email."""
    to_email = payload["to_email"]
    cfg = _load_smtp_config()
    if cfg is None:
        logger.warning("Cannot send invite email to %s — SMTP not configured", to_email)
        return {"sent": 0, "skipped": True}

    app_url = settings.APP_URL.rstrip("/")
    app_name = settings.APP_NAME
    invite_link = f"{app_url}/register?token={payload['invite_token']}"
    expire_hours = settings.INVITE_TOKEN_EXPIRE_HOURS
    role = payload.get("role", "viewer")
    invited_by_name = payload.get("invited_by_name", "An admin")

    subject = f"You've been invited to {app_name}"
    text_body = (
        f"Hi,\n\n"
        f"{invited_by_name} has invited you to join {app_name} as a {role}.\n\n"
        f"Click the link below to create your account:\n"
        f"{invite_link}\n\n"
        f"This link expires in {expire_hours} hours.\n\n"
        f"If you didn't expect this invite, you can safely ignore this email.\n\n"
        f"— {app_name}"
    )
    html_body = _build_invite_html(
        app_name=app_name,
        invite_link=invite_link,
        invited_by_name=invited_by_name,
        role=role,
        expire_hours=expire_hours,
    )

    try:
        _send(cfg, to_email, subject, html_body, text_body)
        logger.info("Invite email sent to %s", to_email)
        return {"sent": 1}
    except Exception as e:
        logger.error("Failed to send invite email to %s: %s", to_email, e)
        return {"sent": 0, "failed": 1}
```

- [ ] **Step 5: Register the module in `backend/app/worker.py`**

```python
celery_app.conf.include = [
    "app.tasks.event_tasks",
    "app.tasks.cleanup_tasks",
    "app.tasks.email_tasks",
]
```

- [ ] **Step 6: Run tests**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/test_email_tasks.py -v
```

Expected: 3 passed. Full suite: 17 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/tests/test_email_tasks.py backend/app/tasks/email_tasks.py backend/app/services/email.py backend/app/worker.py
git -c user.name="Mohamed M. Hammad" -c user.email="mohamed.magdy@slnee.com" commit -m "feat(email): add Celery tasks for issue and invite emails"
```

---

### Task 3: Rewire call sites + delete the inline async senders (TDD)

Order matters within this task: the call sites must stop using the old
functions in the same commit that deletes them (`invites.py` imports
`send_invite_email` at module top — deleting first would crash API import).

**Files:**
- Modify: `backend/tests/test_email_tasks.py` (append two tests)
- Modify: `backend/app/services/ingest.py`
- Modify: `backend/app/api/v1/invites.py`
- Modify: `backend/app/api/v1/projects.py`
- Modify: `backend/app/services/email.py` (deletions)

- [ ] **Step 1: Append the failing dispatch tests to `backend/tests/test_email_tasks.py`**

```python
import uuid as _uuid
from datetime import datetime, timezone


@pytest.fixture
async def notif_setup(db):
    """User who is a project member with email notifications on, + an issue."""
    from app.models.user import User
    from app.models.project import Project, ProjectMember
    from app.models.issue import Issue

    user = User(email="member@example.com", name="Member", password_hash="x")
    db.add(user)
    await db.flush()
    project = Project(
        name="Notif Proj", slug="notif-proj",
        dsn_public_key=_uuid.uuid4().hex, created_by=user.id,
    )
    db.add(project)
    await db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id,
                         notify_email=True, notify_inapp=True))
    issue = Issue(project_id=project.id, title="Kaboom", fingerprint="notif-fp")
    db.add(issue)
    await db.flush()
    return project, issue, user


async def test_create_notifications_dispatches_email_task(db, notif_setup, monkeypatch):
    from app.models.notification import NotificationType
    from app.services import ingest as ingest_service

    project, issue, user = notif_setup
    captured = []
    monkeypatch.setattr(
        ingest_service.send_issue_emails, "delay",
        lambda payload: captured.append(payload),
    )

    await ingest_service._create_notifications(
        db, project, issue, NotificationType.NEW_ISSUE
    )

    assert len(captured) == 1
    payload = captured[0]
    assert payload["emails"] == ["member@example.com"]
    assert payload["project_slug"] == "notif-proj"
    assert payload["issue_id"] == str(issue.id)
    assert payload["issue_title"] == "Kaboom"
    assert payload["is_regression"] is False


async def test_create_notifications_survives_broker_failure(db, notif_setup, monkeypatch):
    from app.models.notification import NotificationType
    from app.services import ingest as ingest_service

    project, issue, user = notif_setup

    def _broker_down(payload):
        raise ConnectionError("redis unreachable")

    monkeypatch.setattr(ingest_service.send_issue_emails, "delay", _broker_down)

    # Must not raise — a dead broker cannot fail ingest
    await ingest_service._create_notifications(
        db, project, issue, NotificationType.NEW_ISSUE
    )
```

- [ ] **Step 2: Run to verify failure**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/test_email_tasks.py -v
```

Expected: the two new tests FAIL with `AttributeError: module 'app.services.ingest' has no attribute 'send_issue_emails'` (the 3 Task-2 tests still pass).

- [ ] **Step 3: Rewire `backend/app/services/ingest.py`**

a) Extend the existing tasks-import guard near the top:

```python
try:
    from app.tasks.event_tasks import index_issue_to_meilisearch, index_event_to_meilisearch
    from app.tasks.email_tasks import send_issue_emails
    _HAS_TASKS = True
except Exception:
    _HAS_TASKS = False
```

b) In `_create_notifications`, replace the whole `# ── Email notifications (fire-and-forget) ──` block (the `if email_user_ids:` block containing the inline `await send_issue_notification_email(...)` loop, currently ~lines 626-659) with:

```python
        # ── Email notifications (queued on the Celery worker) ──
        # Never send SMTP inline here: this runs inside the ingest request
        # while its pooled DB connection is held — inline sends caused the
        # 2026-06 pool-exhaustion incident.
        if email_user_ids and _HAS_TASKS:
            try:
                environment = ""
                if issue.metadata_ and isinstance(issue.metadata_, dict):
                    environment = issue.metadata_.get("environment", "")

                emails = [
                    user_rows[uid]["email"]
                    for uid in email_user_ids
                    if user_rows.get(uid, {}).get("email")
                ]
                if emails:
                    send_issue_emails.delay({
                        "emails": emails,
                        "project_name": project.name,
                        "project_slug": project.slug,
                        "issue_id": str(issue.id),
                        "issue_title": issue.title,
                        "issue_level": issue.level.value,
                        "is_regression": notification_type == NotificationType.REGRESSION,
                        "event_count": issue.event_count,
                        "environment": environment,
                    })
            except Exception as e:
                logger.warning("Failed to queue issue emails: %s", e)
```

- [ ] **Step 4: Rewire `backend/app/api/v1/invites.py`**

a) Replace the import at line 15 and add a logger:

```python
from app.tasks.email_tasks import send_invite_email
from app.logging import get_logger

logger = get_logger("api.invites")
```

(Remove `from app.services.email import send_invite_email`.)

b) Replace the send block (currently `await send_invite_email(db=..., ...)` after `await db.refresh(invite)`):

```python
    # Queue invite email on the worker (fire-and-forget — a dead broker
    # must not fail the invite; "sent" now means "queued")
    try:
        send_invite_email.delay({
            "to_email": data.email,
            "invite_token": invite.token,
            "role": data.role.value if hasattr(data.role, 'value') else str(data.role),
            "invited_by_name": current_user.name,
        })
    except Exception as e:
        logger.warning("Failed to queue invite email to %s: %s", data.email, e)
```

- [ ] **Step 5: Remove the dead block in `backend/app/api/v1/projects.py`**

Around lines 319-326 there is a dead block that imports `send_invite_email` and does nothing:

```python
        if assigned_pref.get("email", True):
            try:
                from app.services.email import send_invite_email
                # No dedicated "assigned to project" email template, so we skip email for now
                # Email notification for project assignment can be added later
                pass
            except Exception:
                pass
```

Replace it with a comment only:

```python
        # No dedicated "assigned to project" email template — email skipped.
```

- [ ] **Step 6: Delete the inline senders from `backend/app/services/email.py`**

Delete entirely (verify with grep first that no callers remain outside this file: `grep -rn "send_invite_email\|send_issue_notification_email\|_get_smtp_config" backend/app --include="*.py" | grep -v email_tasks | grep -v "app/services/email.py"` must return nothing):

- `async def _get_smtp_config(...)` (replaced by `email_tasks._load_smtp_config`)
- `async def send_invite_email(...)`
- `async def send_issue_notification_email(...)`

Then remove the now-unused imports at the top of the file: `from sqlalchemy import select`, `from sqlalchemy.ext.asyncio import AsyncSession`, `from app.models.setting import Setting`. Keep `smtplib`, MIME imports, `app_settings`, the builders, `_env_smtp_config`, and `_send`.

- [ ] **Step 7: Run the full suite**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest -v
```

Expected: 19 passed. Also confirm clean imports:

```bash
docker compose -f docker-compose.dev.yml exec backend python -c "import app.main; import app.api.v1.invites; import app.api.v1.projects; print('ok')"
```

- [ ] **Step 8: Commit**

```bash
git add backend/tests/test_email_tasks.py backend/app/services/ingest.py backend/app/api/v1/invites.py backend/app/api/v1/projects.py backend/app/services/email.py
git -c user.name="Mohamed M. Hammad" -c user.email="mohamed.magdy@slnee.com" commit -m "fix(email): dispatch issue/invite emails via Celery, never inline in requests"
```

---

### Task 4: Manual end-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Restart the worker so it loads the new task module**

```bash
cd /opt/megoobug
docker compose -f docker-compose.dev.yml restart celery-worker backend
sleep 10
docker compose -f docker-compose.dev.yml logs celery-worker --tail 25
```

Expected: `[tasks]` list includes `send_issue_emails` and `send_invite_email`; backend reloads cleanly.

- [ ] **Step 2: Invoke the issue-email task with a fake payload (SMTP unconfigured on dev → clean skip)**

```bash
docker compose -f docker-compose.dev.yml exec celery-worker celery -A app.worker call send_issue_emails --args '[{"emails":["x@example.com"],"project_name":"P","project_slug":"p","issue_id":"deadbeef-0000-0000-0000-000000000000","issue_title":"T","issue_level":"error","is_regression":false,"event_count":1,"environment":""}]'
sleep 5
docker compose -f docker-compose.dev.yml logs celery-worker --tail 6
```

Expected: task succeeds returning `{'sent': 0, 'failed': 0, 'skipped': True}` (SMTP not configured in dev).

- [ ] **Step 3: Ingest an event end-to-end and confirm 200 + task dispatch**

```bash
DSN_KEY=$(docker compose -f docker-compose.dev.yml exec -T postgres psql -U megoo -d megoobug -tAc "SELECT dsn_public_key FROM projects LIMIT 1")
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  "http://localhost:8001/api/1/store/?sentry_key=$DSN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"event_id":"'"$(python3 -c 'import uuid;print(uuid.uuid4().hex)')"'","message":"email dispatch verification","timestamp":"'"$(date -u +%Y-%m-%dT%H:%M:%S)"'"}'
```

Expected: `200`. (Whether an email task fires depends on member notify flags — the point is ingest returns instantly and never blocks on SMTP.)

- [ ] **Step 4: Broker-down resilience check (the incident scenario)**

```bash
docker compose -f docker-compose.dev.yml stop redis
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  "http://localhost:8001/api/1/store/?sentry_key=$DSN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"event_id":"'"$(python3 -c 'import uuid;print(uuid.uuid4().hex)')"'","message":"broker down verification","timestamp":"'"$(date -u +%Y-%m-%dT%H:%M:%S)"'"}'
docker compose -f docker-compose.dev.yml start redis
```

Expected: still `200` (warning logged about queueing, request unaffected). Note: pubsub/websocket warnings during the redis stop are expected and harmless.

- [ ] **Step 5: Final state check**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest
git status && git log --oneline -4
```

Expected: 19 passed; clean tree; 3 commits on `fix/async-email-dispatch`.
