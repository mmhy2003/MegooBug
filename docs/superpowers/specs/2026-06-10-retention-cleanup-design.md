# Scheduled retention cleanup for ingested data

**Date:** 2026-06-10
**Status:** Approved

## Problem

MegooBug never garbage-collects ingested data. Events and issues accumulate
forever in two stores:

- **Postgres** — `events` and `issues` rows are only ever inserted
  (`app/services/ingest.py`); nothing deletes them.
- **Meilisearch** — every event and issue is mirrored into the `events` /
  `issues` search indexes (`app/tasks/event_tasks.py`) and never removed.

There is also no scheduler: a Celery worker + Redis exist, but no beat
scheduler is configured anywhere.

## Decisions (user-approved)

- **Scope:** delete events older than the retention window AND issues whose
  `last_seen` is older than the window (stale issues). Active issues keep
  their recent events and stats.
- **Scheduler:** Celery beat embedded in the existing worker (`-B` flag),
  daily run.
- **Config:** env var only — `RETENTION_DAYS`, default `14`; `0` (or
  negative) disables retention.
- **Mechanism:** targeted deletes mirrored surgically to Meilisearch
  (no nightly full reindex, no table partitioning).

## Design

### Config

`app/config.py`: add `RETENTION_DAYS: int = 14` under a new
`# ── Retention ──` section. Add `RETENTION_DAYS=14` to `.env.example` with
a comment explaining `0` disables cleanup.

### Scheduling

`app/worker.py`:

- Add `app.tasks.cleanup_tasks` to `celery_app.conf.include`.
- Add a `beat_schedule` running task `cleanup_old_data` daily at 03:00 UTC
  (crontab schedule).

Compose files (`docker-compose.yml` and `docker-compose.dev.yml`): change the
`celery-worker` command to
`celery -A app.worker worker -B --loglevel=info`, with a YAML comment that
`-B` must move to a dedicated beat service if workers are ever scaled beyond
one (multiple embedded beats would duplicate runs).

### Cleanup task

New module `app/tasks/cleanup_tasks.py`:

- `cleanup_old_data` — sync Celery task (`@celery_app.task(name="cleanup_old_data")`).
  - If `settings.RETENTION_DAYS <= 0`: log "retention disabled" and return.
  - Compute `cutoff = datetime.now(timezone.utc) - timedelta(days=settings.RETENTION_DAYS)`.
  - Run the async core via `asyncio.run(...)`, creating a fresh
    `create_async_engine(settings.DATABASE_URL)` inside the task and
    disposing it in a `finally` (the app's global engine must not cross the
    Celery process boundary).
  - Returns/logs a summary dict: `{"issues_deleted": N, "events_deleted": M}`.

- Async core `_cleanup(db: AsyncSession, cutoff, batch_size=5000) -> dict`
  (importable and testable without Celery or Meilisearch; the Celery task
  opens its own session around it):

  1. **Stale issues:** `SELECT id FROM issues WHERE last_seen < cutoff`;
     `DELETE FROM issues WHERE id IN (...)`. DB `ON DELETE CASCADE` removes
     their events; `notifications.issue_id` is `ON DELETE SET NULL`, so
     notifications survive harmlessly. Commit.
  2. **Old events under active issues:** loop:
     `DELETE FROM events WHERE id IN (SELECT id FROM events WHERE timestamp < cutoff LIMIT 5000) RETURNING id`;
     commit each batch; collect returned ids; stop when a batch is empty.
  3. Return stale issue ids, deleted event ids, and counts.

- Meilisearch mirror (in the sync task, after the DB work, best-effort):
  - `issues` index: `delete_documents(stale_issue_ids)`.
  - `events` index: delete by filter `issue_id IN [stale ids]` (issue_id is
    already filterable), plus `delete_documents(event_ids)` for the batch-
    deleted events.
  - Any Meilisearch exception is logged and swallowed (same pattern as the
    existing indexing tasks); a later `reindex_all` self-heals search.

### Semantics

- `issue.event_count` remains a **lifetime** counter (Sentry semantics): it
  is not decremented when old events expire. An active issue's detail page
  may list fewer stored events than its count.
- Postgres is the source of truth and is cleaned first; each batch commits
  independently, so a crash mid-run loses nothing — the next nightly run
  resumes naturally.

## Out of scope

- Admin-UI or per-project retention configuration (possible later iteration).
- Partitioning the events table.
- Decrementing/recomputing issue aggregates.
- Cleaning notifications, invites, or other non-ingested data.

## Testing

Unit tests against the existing `megoobug_test` Postgres fixtures
(`backend/tests/`), exercising `_cleanup` directly:

- Stale issue (old `last_seen`) is deleted and its events cascade away;
  a fresh issue and its events survive.
- Active issue (recent `last_seen`) with one old and one new event keeps the
  issue and the new event; the old event is deleted.
- Cutoff boundary: events exactly newer than cutoff survive.
- Batching: with a small batch size parameter, the loop terminates and
  deletes everything past cutoff.
- `cleanup_old_data` with `RETENTION_DAYS=0` no-ops (monkeypatched setting).

Manual verification: seed old + new data in the dev DB, run the task once in
the worker container (`celery call` or direct invocation), confirm DB counts
and a Meilisearch search no longer returns the deleted event.
