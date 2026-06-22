# Protecting reads from ingest load (single-server contention fix)

**Date:** 2026-06-22
**Status:** Approved

## Problem

During high-volume ingest storms the dashboard and read APIs become slow or
time out, even though event ingestion itself keeps returning fast `200`s. The
queue-based ingest pipeline shipped on 2026-06-10
([async ingestion spec](2026-06-10-async-ingestion-pipeline-design.md)) already
moved processing off the request path — accept-and-enqueue endpoints, a
dedicated `ingest` Celery queue drained by `celery-ingest`, and
queue-depth backpressure (`429` past `INGEST_QUEUE_MAX`). So the remaining pain
is **not** the broker; it is single-box resource contention: the ingest worker's
write load on Postgres starves the dashboard's read queries.

The user again asked whether RabbitMQ/Kafka would help.

## Decision (user-approved)

**No RabbitMQ/Kafka — again.** Redis + Celery already provides the queue; the
2026-06-10 spec recorded a user-approved "No RabbitMQ" decision, and nothing has
changed that calculus. Swapping the broker would not touch the actual
bottleneck (read-side contention on shared Postgres).

**Approved approach: protect the reads and bound the ingest footprint, all on a
single server, with no new services** ("Approach A"). Two heavier options were
considered and deferred:

- **Approach B** (shrink the write footprint): micro-batch worker DB writes +
  PgBouncer. Deferred until metrics show the worker itself saturating Postgres
  after A. Micro-batching was already deferred by the 2026-06-10 spec.
- **Approach C** (structural isolation): read replica, split read tier,
  multi-host worker scaling. This is the horizontal-scaling story the
  2026-06-10 spec put out of scope for a single server. Non-goal until A/B are
  proven insufficient.

## Root causes (single box, "dashboard gets slow under ingest")

1. **Expensive, unindexed, uncached reads.** `GET /stats/dashboard` runs
   `COUNT(events.id) WHERE received_at >= now-24h` live on every load, but
   `events.received_at` has **no index** (only `events.timestamp` is indexed,
   via `ix_events_timestamp`). `GET /stats/projects/{slug}/trends` does
   `date_trunc('day', received_at)` grouped over the same column with no
   `(project_id, received_at)` index. `issues.status` is also unindexed, so the
   unresolved-issue count scans. These aggregates run directly against the
   `events`/`issues` tables that ingest is actively writing.
2. **Ingest drains at full tilt.** The worker processes as fast as it can with
   no rate cap, so a storm pegs Postgres CPU/IO; the queue + `429` already
   absorb bursts, so the worker does not need to sprint.
3. **No resource isolation.** `docker-compose.yml` sets no CPU/memory limits and
   does not budget Postgres connections; the backend engine alone allows up to
   ~60 connections (`pool_size=20 + max_overflow=10`, ×2 uvicorn workers)
   against Postgres's default `max_connections=100`, on top of the worker pools.

## Design

### 1. Indexes (one Alembic migration)

Add the following indexes via Alembic, idempotent with `if_not_exists`:

> **Update (2026-06-22, post-implementation, user-approved):** The original
> design specified `CREATE INDEX CONCURRENTLY` inside an `autocommit_block()` to
> avoid write-locking a large `events` table. This proved **incompatible with
> the app's auto-migrate**: `app/main.py` runs Alembic during startup while
> holding `pg_advisory_lock(727274)` on a connection with an open transaction,
> and `CREATE INDEX CONCURRENTLY` waits for all concurrent transactions
> (including that lock holder) to finish — a deadlock that hangs startup. The
> migration therefore uses **plain `CREATE INDEX IF NOT EXISTS`**. The one-time
> deploy build takes a `SHARE` lock that briefly blocks writes (ingest INSERTs,
> which are Celery-queued and simply pause) but never blocks reads. For a very
> large `events` table, an operator may pre-create these indexes manually with
> `CONCURRENTLY` before deploying so the migration no-ops.

- `ix_events_received_at` on `events(received_at)` — backs `errors_24h`.
- `ix_events_project_received_at` on `events(project_id, received_at)` — backs
  `project_trends` and per-project time-window counts.
- `ix_issues_unresolved` — **partial** index
  `ON issues(project_id) WHERE status = 'unresolved'`. Serves both the
  admin-wide and project-scoped unresolved counts; stays small (unresolved rows
  only).

`downgrade()` drops all three (also via `autocommit_block()`).

### 2. Cached dashboard/stats aggregates (keystone)

Add a small JSON cache helper to `app/services/pubsub.py`, reusing the existing
async Redis pool and its `decode_responses=True` client:

- `cache_get_json(key) -> dict | None` and
  `cache_set_json(key, value, ttl) -> None`.
- Both **fail open**: any Redis error is caught and logged at warning; a get
  failure behaves as a cache miss, a set failure is ignored. Caching must never
  break or block a request.

Apply in `app/api/v1/stats.py`:

- `GET /stats/dashboard`: cache the 4-number result under a key **scoped to the
  caller's project access** so RBAC is preserved —
  admins (`project_ids is None`) → `stats:dashboard:all`;
  scoped users → `stats:dashboard:{sha1(",".join(sorted(map(str, project_ids))))}`.
  TTL `STATS_CACHE_TTL` (default `30`). On miss: run the existing queries, store,
  return.
- `GET /stats/projects/{slug}/trends`: cache per project under
  `stats:trends:{project_id}:{days}`, TTL `60` (daily buckets move slowly). The
  access check (`check_project_access`) runs **before** the cache lookup so a
  cached payload is never served to an unauthorized caller.

No explicit invalidation — TTL expiry only. The dashboard already layers live
counts on top of these bases via the `stats_update` websocket deltas published
in `process_event`, so a ≤30s-stale base is invisible to users while removing
the repeated heavy counts from Postgres under load.

### 3. Throttle the ingest worker

Make the `ingest` drain rate bounded and configurable so a storm leaves Postgres
headroom for reads (the queue + `429` backpressure absorb the overflow):

- `celery-ingest` concurrency from `INGEST_CONCURRENCY` (default `4`,
  unchanged): `--concurrency=${INGEST_CONCURRENCY:-4}` in `docker-compose.yml`.
- Optional per-worker `rate_limit` on the `ingest_event` task driven by
  `INGEST_RATE_LIMIT` (default **unset = no cap**). When set (e.g. `"200/s"`),
  it is applied via the task decorator / `task_annotations` so sustained
  throughput is capped and reads keep headroom.

This is a deliberate ingestion-latency-vs-read-responsiveness knob with
conservative defaults; given the pain is read slowness (not ingestion lag),
trading a little ingest latency for read headroom is the correct default
direction. Default ships with no cap; operators set `INGEST_RATE_LIMIT` if a
storm still pressures Postgres.

### 4. Connection & resource budgeting (no new services)

- **Pools:** lower the backend engine in `app/database.py` to a budgeted size
  (proposed `pool_size=10, max_overflow=5`) and make both env-configurable
  (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`). Document the total connection budget
  (backend × uvicorn workers + celery-ingest children + celery-worker +
  ad-hoc reindex) against Postgres `max_connections`; raise `max_connections`
  on the `postgres` service (e.g. via `command: postgres -c max_connections=200`)
  if the budget requires it.
- **Resource limits:** add CPU/memory limits to `celery-ingest` (and sensible
  limits on the other services) in `docker-compose.yml` so an ingest storm
  cannot starve the backend/Postgres for CPU — the isolation backstop.
- **New settings** added to `app/config.py` and documented in `.env.example`:
  `STATS_CACHE_TTL`, `INGEST_CONCURRENCY`, `INGEST_RATE_LIMIT`, `DB_POOL_SIZE`,
  `DB_MAX_OVERFLOW`.

### 5. Unchanged

Ingest URLs, auth, and response shapes; `process_event` logic; the websocket /
real-time flow (including `stats_update` deltas); the sentry-compat read API;
the accept-and-enqueue pipeline and its backpressure.

## Error handling summary

| Condition | Behavior |
|---|---|
| Redis cache get fails | Treated as a miss; query Postgres, log warning |
| Redis cache set fails | Ignored; response still returned, log warning |
| Stats query (cache miss) | Unchanged from today |
| Unauthorized trends request | `404` **before** any cache lookup (unchanged) |
| Ingest worker over `INGEST_RATE_LIMIT` | Task waits in the `ingest` queue; depth past `INGEST_QUEUE_MAX` still returns `429` at the endpoint (unchanged) |

## Out of scope (reserved for B/C)

- PgBouncer; micro-batching worker DB writes.
- Stats rollup/aggregation tables.
- Postgres read replica; splitting the read API onto its own tier.
- Horizontal scaling across hosts; per-project rate limits / quotas.
- Changing the broker (RabbitMQ/Kafka).

## Testing

On the existing scaffold (`backend/tests/`, real test Postgres):

1. **Cache hit/miss:** first `/stats/dashboard` call queries the DB and stores
   the key; an immediate second call returns the cached payload without
   re-querying (DB call counter or monkeypatched session).
2. **Fail-open:** with the Redis helper raising, `/stats/dashboard` still
   returns correct numbers from Postgres.
3. **Scope-keying:** an admin and a project-scoped user produce different cache
   keys (no cross-scope leakage); the trends access check runs before the cache.
4. **TTL applied:** `cache_set_json` is called with `STATS_CACHE_TTL` /
   `60` respectively.
5. **Migration:** after `upgrade`, the three indexes exist; `EXPLAIN` shows
   `errors_24h` using `ix_events_received_at` (manual check).
6. **Throttle config:** `INGEST_RATE_LIMIT` / `INGEST_CONCURRENCY` are honored
   by the worker configuration (config-level assertion).
7. Existing tests stay green.

Manual verification on dev: burst ~1–5k events in a loop while polling
`/stats/dashboard`; confirm dashboard p95 latency stays low and the queue
drains; confirm the count query uses the new index via `EXPLAIN ANALYZE`.
