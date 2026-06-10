# Move email sending off the request path (fix pool exhaustion)

**Date:** 2026-06-10
**Status:** Approved

## Problem (production incident)

Production backend hits
`sqlalchemy.exc.TimeoutError: QueuePool limit of size 20 overflow 10 reached`.

Root cause (diagnosed from code; the failing auth request in the traceback is
the victim, not the culprit): notification emails are sent **synchronously
inside the ingest request** while the request's pooled DB connection is held.

The chain:

1. SDK posts an error → `POST /api/{id}/envelope/` → `get_db` checks out a
   pool connection for the whole request (`app/api/ingest.py`).
2. New issue or regression → `_create_notifications`
   (`app/services/ingest.py:383-387`).
3. `_create_notifications` loops recipients and awaits
   `send_issue_notification_email` **serially, inline**
   (`app/services/ingest.py:637-642`).
4. Each send runs sync `smtplib.SMTP(host, port, timeout=15)` + STARTTLS +
   login + send in the default executor (`app/services/email.py:103-108`).
   smtplib's timeout is per socket operation → a slow/unreachable SMTP server
   costs ~15s+ per stage per recipient, with the DB connection held throughout.

Amplifiers: error storms create new issues (→ emails) exactly when ingest
concurrency spikes; the default executor (~cpus+4 threads) saturates with
stuck SMTP sends, so later requests queue for a thread while still holding
their connections. ~30 stuck ingest requests exhaust the pool (20+10) and
starve every other request for 30s → the observed TimeoutError.

Invite emails (`api/v1/invites.py` → `send_invite_email`) follow the same
inline pattern at low volume (slow admin request, not a meltdown).

## Decisions (user-approved)

- **Scope:** move BOTH issue-notification emails and invite emails to Celery.
- **Failure policy:** fire once, log failures (no retries) — matches current
  swallow-and-log semantics.
- **Mechanism:** Celery tasks (existing worker + Redis), not
  BackgroundTasks / fire-and-forget asyncio.
- **Ride-along:** `pool_pre_ping=True` on the engine. No pool resizing.

## Design

### New module: `backend/app/tasks/email_tasks.py`

Registered in `celery_app.conf.include` (`app/worker.py`). Two fire-once
tasks, both pure-JSON payloads:

- `send_issue_emails(payload)` with payload keys: `emails` (list of recipient
  addresses), `project_name`, `project_slug`, `issue_id`, `issue_title`,
  `issue_level`, `is_regression`, `event_count`, `environment`.
  Behavior: load SMTP config (see below); if unconfigured, log and return.
  Build subject/text/HTML once via the existing builders in
  `app/services/email.py`, then `_send()` per recipient; log and continue on
  per-recipient failure. Returns a count summary for the result backend.
- `send_invite_email(payload)` with payload keys: `to_email`, `invite_token`,
  `role`, `invited_by_name`. Same load-config/no-op/log semantics.

SMTP config loading in the worker: a small sync read of the `settings` table
row `key="smtp"` using a sync engine (`postgresql://` URL transform +
psycopg2, the same pattern as `reindex_all`), falling back to env vars. The
env-fallback dict construction is extracted from `_get_smtp_config` into a
pure helper `_env_smtp_config()` in `app/services/email.py`. The async
`_get_smtp_config(db)` has no remaining callers after this change (verified
by grep) and is deleted along with the async senders; the sync loader in
`email_tasks.py` is its replacement. SMTP credentials are deliberately NOT
passed through the broker.

### Call-site changes

- `app/services/ingest.py: _create_notifications` — replace the inline send
  loop with: build the recipient address list (the function already resolves
  users/preferences), then one `send_issue_emails.delay(payload)` wrapped in
  try/except logging a warning — a dead broker must not fail ingest (same
  guard style as the adjacent Meilisearch dispatch).
- Invite call sites — there are TWO: `app/api/v1/invites.py:62` and
  `app/api/v1/projects.py:321` (invite-by-email during project member add).
  Replace each `await send_invite_email(db, ...)` with a guarded
  `send_invite_email.delay(payload)`. Any "email_sent" response field now
  means "queued" (response semantics documented at the call site).

### `app/services/email.py` cleanup

Keep: HTML builders, `_send()`, config helpers (with the extracted pure
env-fallback). Delete the now-unused async `send_invite_email` /
`send_issue_notification_email` coroutines so the blocking inline pattern
cannot be reintroduced. Before deleting, verify with grep that the only
callers are the two call sites above.

### Engine hardening

`app/database.py`: add `pool_pre_ping=True` to `create_async_engine` —
protects against stale pooled connections after a Postgres restart.

## Why this fixes the incident

Ingest requests do zero SMTP I/O; their DB connections are held only for
milliseconds of actual DB work. Mail-server latency lands on the Celery
worker process, which does not share the API's connection pool. The thread
pool of the API process is no longer consumed by SMTP.

## Out of scope

- Email retries / dead-letter queues.
- Pool size tuning.
- Digest/batching of notification emails.
- Any UI changes.

## Testing

Unit tests on the existing scaffold (`backend/tests/`, real test Postgres):

1. `_create_notifications` with a member (`notify_email=True`) dispatches
   exactly one `send_issue_emails` task whose payload contains the right
   recipient and issue fields (task `delay` monkeypatched to capture).
2. `_create_notifications` proceeds (no exception) when `delay` raises —
   the broker-down guard.
3. `send_issue_emails.run()` no-ops cleanly when SMTP is unconfigured
   (config loader monkeypatched to None).
4. `send_issue_emails.run()` continues past a recipient whose `_send` raises
   (monkeypatched), still attempting the rest.

Manual verification on the dev stack: invoke the task in the worker with a
fake payload (SMTP unconfigured → clean no-op log); ingest an event with the
broker stopped and confirm HTTP 200 + warning log.
