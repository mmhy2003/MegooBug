# Async ingestion pipeline (queue-based ingest on Celery/Redis)

**Date:** 2026-06-10
**Status:** Approved

## Problem

Under sustained high event volume (and during error storms), ingestion
overwhelms the server. Today every `POST /api/{id}/store|envelope/` request
does all processing inline: an uncached DSN lookup, issue dedup SELECT,
issue insert/update (with hot-row contention on `event_count` for a single
storming issue), full-JSONB event INSERT, and commit — all while holding a
pooled DB connection, on a **single uvicorn process** (prod Dockerfile has
no `--workers`).

The user asked whether to introduce RabbitMQ.

## Decision (user-approved)

**No RabbitMQ.** The queue *pattern* is right, but the queue already exists:
Redis + Celery. RabbitMQ would add a fourth stateful service for delivery
guarantees and routing features that best-effort error ingestion does not
need. Revisit a dedicated broker only if guaranteed no-loss ingestion or
multiple independent consumers become requirements.

**Approved architecture: accept-then-process on Celery/Redis** (Sentry
semantics: SDK gets 200 when the event is queued, not stored; dashboard
visibility lags by queue depth; a Redis crash loses queued events —
explicitly accepted).

Calibration (user input): single server, **sustained** high volume — so the
design includes worker throughput and bounded-queue backpressure, not just
burst absorption.

## Design

### 1. Thin ingest endpoints (`app/api/ingest.py`)

`store_event` and `store_envelope` keep their URLs, auth behavior, and
response shapes. New flow: DSN resolve → decompress/parse → size cap →
queue-depth check → enqueue → `200 {"id": <event_id>}`. The endpoints drop
their `get_db` dependency; DB is touched only on DSN cache misses.

- **DSN cache** (`app/services/ingest.py`): in-process dict
  `{dsn_key: (project_snapshot | None, expires_at)}`; positive TTL 60s,
  negative TTL 10s (invalid-key floods must not hammer the DB). The
  snapshot carries `id`, `name`, `slug` only. Cache module-level with a
  small helper so tests can clear it. On a cache miss the helper opens its
  own short-lived session via `async_session_factory()` (the endpoints no
  longer carry a `Depends(get_db)` session at all).
- **Size cap**: decompressed body larger than `MAX_EVENT_BYTES`
  (new setting, default 1_048_576) → `413`. Protects Redis memory now that
  payloads transit the queue.
- **Queue-depth backpressure**: `LLEN ingest` via the shared async Redis
  client (`app/services/pubsub.py`); depth > `INGEST_QUEUE_MAX`
  (new setting, default 50_000) → `429` with `Retry-After: 30` (Sentry SDKs
  honor 429). The depth value is cached in-process for 1s. This bounds the
  queue under sustained overload instead of letting Redis grow to OOM.
- **Enqueue failure** (broker unreachable; publish timeouts are already
  bounded): `503` — SDKs retry with backoff. Never fall back to inline
  processing (that would reintroduce the connection-pool failure mode).

### 2. Ingest worker (`app/tasks/ingest_tasks.py`)

- Task `ingest_event(project_id: str, event_data: dict)` registered as
  `"ingest_event"`, routed to a dedicated **`ingest` queue** via
  `task_routes` in `app/worker.py`.
- The task re-fetches the `Project` by id and calls the existing
  `process_event(project, event_data, db)` unchanged — dedup, issue upsert,
  event insert, notification dispatch, Meilisearch indexing, and websocket
  publishes all keep their current behavior, now on the worker. If the
  project was deleted in the interim, log and drop.
- **Persistent loop + engine per worker child** (the key mechanism):
  `process_event` is async; Celery tasks are sync; creating an asyncpg
  engine per task cannot sustain hundreds of events/sec. Each prefork child
  lazily creates ONE event loop and ONE async engine + sessionmaker at
  module level and reuses them for every task (`loop.run_until_complete`).
  Engine pool small (e.g., `pool_size=5`). Documented in the module
  docstring — this is non-obvious and load-bearing.
- New compose service **`celery-ingest`** in both compose files:
  `celery -A app.worker worker -Q ingest --concurrency=4 --loglevel=info`
  (no `-B`; beat stays on the existing worker). The existing `celery-worker`
  keeps the default queue (emails, indexing, cleanup) — storms and email
  latency can never starve each other.

### 3. Serving capacity

Prod backend runs `uvicorn app.main:app --host 0.0.0.0 --port 8000
--workers ${UVICORN_WORKERS:-2}` (compose `command:` so the env var
interpolates; Dockerfile CMD stays as the single-process fallback).
`UVICORN_WORKERS=2` documented in `.env.example`. Dev keeps autoreload
single-process.

### 4. Unchanged

Ingest URLs and response bodies; DSN auth semantics; `process_event` logic;
the dashboard websocket flow; dev ergonomics (dev gets the same pipeline).
The sentry-compat read API is untouched.

## Error handling summary

| Condition | Response |
|---|---|
| Invalid/unknown DSN | 401 (as today; negative-cached 10s) |
| Malformed payload | 400 (as today) |
| Payload > MAX_EVENT_BYTES | 413 |
| Ingest queue > INGEST_QUEUE_MAX | 429 + Retry-After: 30 |
| Broker unreachable at enqueue | 503 |
| Worker task failure | logged with event_id; fire-once, event dropped (accepted best-effort semantics) |

## Out of scope

- RabbitMQ/Kafka.
- Micro-batching DB writes in the worker (issue `event_count` row-lock
  serialization moves off the API path; revisit batching only if a single
  hot issue caps worker throughput in practice).
- Per-project rate limiting / quotas.
- Horizontal scaling across hosts.
- Retry/dead-letter for failed worker tasks.

## Testing

On the existing scaffold (`backend/tests/`, real test Postgres):

1. Endpoint enqueues: POST a valid store payload with `ingest_event.delay`
   monkeypatched → 200, captured payload has the event_data and project id;
   no event row written synchronously.
2. 413 on oversized decompressed payload.
3. 429 when the queue-depth helper reports depth above the cap
   (helper monkeypatched).
4. 503 when `delay` raises.
5. DSN cache: second request with the same key does not query the DB
   (SELECT counter via monkeypatched session/exec or cache inspection);
   negative caching returns 401 without a query within TTL.
6. Worker end-to-end: `ingest_event.run(project_id, event_data)` against the
   test DB creates the issue + event rows (exercises the persistent
   loop/engine machinery).
7. Existing 20 tests stay green.

Manual verification on dev: burst ~200 events via a loop → all 200s at ~ms
latency, queue drains, rows appear; stop `celery-ingest` mid-burst → API
still 200s instantly and events process after restart; depth cap forced low
→ 429.
