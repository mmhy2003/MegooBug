# Fix Sentry MCP event lookup 404 (event ID type mismatch)

**Date:** 2026-06-10
**Status:** Approved

## Problem

The Sentry MCP's `get_sentry_resource` tool (and `getEventForIssue`) fails with
`API error (404): Event not found` when fetching a specific event, e.g.:

- organizationSlug: `megoobug`
- issueId: `WEBMAIL-BACKEND-2954`
- eventId: `31472ffb67c14b8d85ceb68f067146ae`

Root cause is in MegooBug's Sentry-compat API, not the MCP. Sentry event IDs
are 32-character dashless hex strings, and Python's `uuid.UUID()` accepts
dashless hex. In `get_org_issue_event`
(`backend/app/api/sentry_compat/organizations.py`, route
`GET /api/0/organizations/{org}/issues/{issue_id}/events/{event_id}/`):

```python
try:
    eid = UUID(event_id)                      # succeeds for dashless hex!
    ... where(Event.id == eid, ...)           # internal PK — never matches
except ValueError:
    ... where(Event.event_id == event_id, ...)  # dead code for real Sentry IDs
```

Every real Sentry `eventID` parses as a UUID and is compared against the
internal `Event.id` primary key (a random uuid4) instead of the
`Event.event_id` column, so the lookup always returns 404. The fallback that
queries the correct column is unreachable.

The same bug class exists in `get_event`
(`backend/app/api/sentry_compat/issues.py`, route `GET /api/0/events/{event_id}/`):
the path parameter is typed `UUID` and only the PK is queried.

Issue shortId resolution (`WEBMAIL-BACKEND-2954`) is **not** affected:
`issue_number` is a global sequence, so `_resolve_issue` works correctly.

## Scope

Fix both event endpoints (approved):

1. `GET /api/0/organizations/{org}/issues/{issue_id}/events/{event_id}/`
   (`organizations.py: get_org_issue_event`) — the endpoint the MCP hit.
2. `GET /api/0/events/{event_id}/` (`issues.py: get_event`).

Not in scope: a full audit of other ID lookups (issues/projects were checked
and are fine), release tracking, or other MCP tool gaps.

## Design

### Shared helper (new module)

`backend/app/api/sentry_compat/event_lookup.py`:

```python
async def find_event(db, raw_id: str, issue_id=None):
    conds = [Event.event_id == raw_id]
    try:
        conds.append(Event.id == UUID(raw_id))
    except ValueError:
        pass
    q = select(Event).where(or_(*conds))
    if issue_id is not None:
        q = q.where(Event.issue_id == issue_id)
    return (await db.execute(q)).scalar_one_or_none()
```

Single DB round-trip; accepts either the Sentry hex `eventID` or the internal
UUID `id` (both of which the API returns to clients). Lives in its own module
because both route files need it and neither should import from the other.

### `organizations.py: get_org_issue_event`

- Keep the `event_id == "latest"` special case unchanged.
- Replace the try/except lookup with `find_event(db, event_id, issue_id=issue.id)`.
- Access control unchanged: `_resolve_issue` already enforces project access
  before the event lookup.

### `issues.py: get_event`

- Change the path parameter type from `UUID` to `str`.
- Use `find_event(db, event_id)` (no issue filter).
- Keep the existing `check_project_access` check on the found event.

### Error handling

Unchanged: 404 `"Event not found"` when no match; same access-check 404s.

## Testing

Pytest is in `requirements.txt` but the repo has no test infrastructure yet.
Add a minimal scaffold:

- `backend/tests/` with a focused async test for `find_event`: a
  dashless-hex Sentry ID must match via the `event_id` column; an internal
  UUID must match via the PK; an unknown ID returns `None`; the `issue_id`
  filter excludes events from other issues.
- The models use Postgres-specific column types (`UUID`, `JSONB`), so the
  tests run against the dev-stack Postgres (from `docker-compose.dev.yml`),
  using a dedicated test database created/dropped by a conftest fixture —
  not SQLite.
- Manual verification: run the dev stack, hit
  `/api/0/organizations/megoobug/issues/<shortId>/events/<hex-id>/` with a
  seeded event, confirm 200 with the event payload (and that the MCP call
  that previously failed now succeeds).
