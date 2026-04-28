# MegooBug — Product Requirements Document

> **Version:** 1.0 · **Date:** 2026-04-28 · **Status:** Draft · **License:** MIT (Open Source)

---

## 1. Overview

**MegooBug** is an open-source, self-hosted, real-time bug/error tracking platform inspired by Sentry. It consumes events via the **Sentry SDK/API**, aggregates them into actionable issues, and notifies the right people instantly — through in-app notifications and configurable email alerts.

### 1.1 Goals

| # | Goal |
|---|------|
| G1 | Provide a self-hosted alternative to Sentry with a streamlined, modern UI |
| G2 | Accept errors from any Sentry-compatible SDK (Python, JS, Go, etc.) |
| G3 | Real-time error ingestion, grouping, and notification |
| G4 | Role-based access with fine-grained permissions |
| G5 | One-command deployment via Docker Compose |

### 1.2 Non-Goals (v1)

- Distributed tracing / performance monitoring
- Replay sessions / profiling
- Billing or paid-tier gating

---

## 2. Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | **Next.js 16** (App Router, TypeScript) |
| Backend | **FastAPI** (Python 3.12, async) |
| Database | **PostgreSQL 16** |
| Cache / Pub-Sub | **Redis 7** |
| Task Queue | **Celery** (Redis broker) |
| Search Engine | **Meilisearch** (full-text search) |
| Containerization | **Docker** + **Docker Compose** |

---

## 3. Architecture

```
┌─────────────┐       ┌──────────────┐       ┌───────────┐
│  Sentry SDK │──────▶│  FastAPI      │──────▶│ PostgreSQL│
│  (clients)  │ HTTP  │  Backend      │       │           │
└─────────────┘       │  ┌──────────┐ │       └───────────┘
                      │  │ WebSocket│ │
                      │  │ Server   │ │       ┌───────────┐
┌─────────────┐       │  └──────────┘ │──────▶│   Redis   │
│  Next.js    │◀─────▶│  ┌──────────┐ │       └───────────┘
│  Frontend   │  API  │  │ Celery   │ │
└─────────────┘       │  │ Workers  │ │       ┌───────────┐
                      │  └──────────┘ │──────▶│   SMTP    │
                      └──────────────┘       └───────────┘
```

### 3.1 Data Flow

1. **Ingest** — Client SDKs POST to `/api/v1/store/` (Sentry-compatible envelope/store endpoint).
2. **Process** — FastAPI validates, normalizes, and groups the event into an **Issue**.
3. **Persist** — Event + Issue stored in PostgreSQL; counters updated in Redis.
4. **Index** — Celery task indexes the issue/event into Meilisearch for instant search.
5. **Notify** — Celery task fans out: WebSocket push (in-app bell) + email (if SMTP configured).
6. **Display** — Next.js frontend polls/subscribes for live updates.

---

## 4. DevOps & Infrastructure

### 4.1 Directory Layout

```
MegooBug/
├── frontend/                # Next.js app
│   ├── Dockerfile           # Multi-stage production build
│   ├── Dockerfile.dev       # Dev with hot-reload
│   ├── src/
│   │   ├── app/             # App Router pages & layouts
│   │   ├── components/      # Shared UI components
│   │   └── lib/             # API client, utilities
│   └── ...
├── backend/                 # FastAPI app
│   ├── Dockerfile           # Multi-stage production build
│   ├── Dockerfile.dev       # Dev with uvicorn --reload
│   ├── alembic/             # Alembic migrations (backup)
│   ├── alembic.ini
│   ├── requirements.txt
│   └── app/
│       ├── main.py          # App factory + auto-migrate + auto-seed
│       ├── config.py        # Pydantic settings (from env)
│       ├── database.py      # Async SQLAlchemy engine + session
│       ├── dependencies.py  # Auth + RBAC dependencies
│       ├── logging.py       # Structured logging configuration
│       ├── worker.py        # Celery configuration
│       ├── api/v1/          # API route modules
│       ├── models/          # SQLAlchemy ORM models
│       ├── schemas/         # Pydantic request/response schemas
│       ├── services/        # Business logic (auth, etc.)
│       ├── tasks/           # Celery task modules
│       └── scripts/         # CLI scripts (seed, etc.)
├── docker-compose.yml       # Production
├── docker-compose.dev.yml   # Development (hot-reload)
├── Makefile                 # Convenience commands
├── .env.example             # Template env vars
└── docs/
    └── prd.md
```

### 4.2 Docker — Frontend

**`frontend/Dockerfile`** (production — multi-stage)

```
Stage 1: deps     → install node_modules
Stage 2: build    → next build (standalone output)
Stage 3: runner   → node server.js (minimal image)
```

**`frontend/Dockerfile.dev`** — single stage, mounts source, runs `next dev`.

### 4.3 Docker — Backend

**`backend/Dockerfile`** (production — multi-stage)

```
Stage 1: build    → install Python deps into venv
Stage 2: runner   → copy venv, set PYTHONPATH=/app, run uvicorn
```

**`backend/Dockerfile.dev`** — single stage, mounts source, `PYTHONPATH=/app`, runs `uvicorn --reload`.

> **Note:** `PYTHONPATH=/app` is required so that Alembic and CLI scripts can resolve the `app` package from the `/app` workdir.

### 4.4 Docker Compose — Production (`docker-compose.yml`)

Services: `frontend`, `backend`, `celery-worker`, `postgres`, `redis`, `meilisearch`

- All services on internal Docker network.
- Frontend exposes `:3000`, Backend exposes `:8000`.
- Named volumes for `postgres_data`, `redis_data`, and `meili_data`.
- Health checks on all services.

### 4.5 Docker Compose — Development (`docker-compose.dev.yml`)

Services: `frontend`, `backend`, `celery-worker`, `postgres`, `redis`, `meilisearch`

- Source directories bind-mounted for hot-reload.
- Frontend on `:3000`, Backend on `:8000` (exposed directly).
- `WATCHFILES_FORCE_POLLING=true` for backend.
- Debug ports exposed.

### 4.6 Auto-Migration & Auto-Seed

The backend **automatically runs database migrations** (`Base.metadata.create_all`) and **seeds the initial admin user** on every startup via the FastAPI lifespan handler. This eliminates the need for manual `make migrate` / `make seed` steps.

- Tables are created/verified on each boot (idempotent).
- Admin user is seeded from `ADMIN_EMAIL` / `ADMIN_PASSWORD` / `ADMIN_NAME` env vars only if no admin exists.
- Alembic remains available as a backup for complex schema changes (`make migrate`).

### 4.7 Structured Logging

The backend uses a centralized logging module (`app/logging.py`) instead of `print()` statements.

- **`setup_logging()`** — called once at app startup, configures root logger.
- **`get_logger(name)`** — returns a child logger under the `megoobug.*` namespace.
- Development: human-readable timestamped format to stdout.
- Production: structured format with noisy third-party loggers (SQLAlchemy, uvicorn access, httpx) suppressed to WARNING level.

### 4.8 Makefile Targets

| Target | Description |
|--------|-------------|
| `make dev` | Build & start development stack (detached) |
| `make prod` | Start production stack |
| `make down` | Stop all containers |
| `make logs` | Tail all service logs |
| `make migrate` | Run Alembic migrations (backup — auto-migrate handles this) |
| `make seed` | Seed admin user (backup — auto-seed handles this) |
| `make test` | Run backend + frontend tests |
| `make lint` | Lint both codebases (ruff + eslint) |
| `make clean` | Remove volumes and images |
| `make shell-be` | Shell into backend container |
| `make shell-fe` | Shell into frontend container |

---

## 5. User Management

### 5.1 Authentication

| Feature | Details |
|---------|---------|
| Method | JWT (access + refresh tokens), HTTP-only cookies |
| Signup | Controlled via `ALLOW_SIGNUP=true/false` env var |
| Invite | Admins generate invite links (token-based, expirable) |
| Password | bcrypt hashed, min 8 chars |
| Sessions | Refresh token rotation, configurable TTL |

### 5.2 Roles & Permissions

| Permission | Admin | Developer | Viewer |
|------------|:-----:|:---------:|:------:|
| View dashboard | ✅ | ✅ | ✅ |
| View issues/events | ✅ | ✅ | ✅ |
| Resolve/ignore issues | ✅ | ✅ | ❌ |
| Create/edit projects | ✅ | ✅ | ❌ |
| Delete projects | ✅ | ❌ | ❌ |
| Manage users & roles | ✅ | ❌ | ❌ |
| Configure settings (SMTP, etc.) | ✅ | ❌ | ❌ |
| Invite users | ✅ | ❌ | ❌ |
| View/manage own profile | ✅ | ✅ | ✅ |

### 5.3 Invite Flow

1. Admin opens **Users** page → clicks **Invite User**.
2. Enters email + selects role → system generates a signed invite token (expires in 48h).
3. Invitee receives email with link → lands on registration form (pre-filled email, role locked).
4. On submit → account created, token invalidated.

---

## 6. Pages & UI

### 6.1 Global Layout

```
┌─────────────────────────────────────────────────┐
│ ┌──────┐ ┌────────────────────────────────────┐ │
│ │      │ │  Header Bar (search, bell, avatar) │ │
│ │  N   │ ├────────────────────────────────────┤ │
│ │  A   │ │                                    │ │
│ │  V   │ │         Page Content               │ │
│ │  B   │ │                                    │ │
│ │  A   │ │                                    │ │
│ │  R   │ │                                    │ │
│ │      │ │                                    │ │
│ └──────┘ └────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

- **Left Sidebar Navbar** — Collapsible (icon-only mode). Contains: logo, Dashboard, Projects, Users (admin only), Settings, theme toggle, user avatar/logout.
- **Header Bar** — Global search, notification bell (badge count), user dropdown.
- **Mobile** — Navbar becomes a hamburger drawer overlay.

### 6.2 Dashboard (`/dashboard`)

| Card | Data |
|------|------|
| Total Projects | Count of all projects |
| Total Errors (24h) | Errors received in last 24 hours |
| Unresolved Issues | Open issue count |
| Active Users | Users who triggered events today |

Additional sections:
- **Error Trend Chart** — Line/area chart showing errors over time (7d/30d toggle).
- **Recent Issues** — Table of latest 10 issues with severity, project, timestamp.
- **Top Projects by Errors** — Bar chart of most-errored projects.

### 6.3 Projects (`/projects`)

**List View:**
- Cards/table showing: project name, platform icon, DSN (masked), error count, last event time.
- Create Project button (Admin/Developer).

**Project Detail (`/projects/:slug`):**
- **Overview** tab — Stats, error trend, DSN display with copy button.
- **Issues** tab — Filterable/sortable list of grouped issues (status, severity, first/last seen, count).
- **Issue Detail (`/projects/:slug/issues/:id`)** — Full stack trace, breadcrumbs, tags, environment, browser/OS info, event timeline, resolve/ignore actions.
- **Settings** tab — Rename, delete, manage notification subscribers.
- **Members** tab — Users assigned to this project (for notification routing).

### 6.4 Users (`/users`) — Admin Only

- Table: avatar, name, email, role, status (active/invited/disabled), joined date.
- Actions: change role, disable/enable, remove.
- **Invite User** button → modal with email + role selector.

### 6.5 Settings (`/settings`)

Tabs:

| Tab | Contents |
|-----|----------|
| **General** | Instance name, URL, signup toggle |
| **Email / SMTP** | SMTP host, port, encryption, username, password, from address, test button |
| **Notifications** | Default notification rules (e.g., notify on first occurrence, every Nth, regression) |
| **Profile** | Current user's name, email, password change, avatar |
| **API Keys** | Create/revoke personal API tokens for Sentry CLI, MCP, and external integrations. Table: name, token prefix, last used, created, expiry, revoke button. |

---

## 6.6 Global Search (Header Bar)

- **Search input** in the header bar with keyboard shortcut (`Ctrl+K` / `⌘+K`).
- **Powered by Meilisearch** — instant, typo-tolerant full-text search.
- Searches across: **issues** (title, message, stack trace), **projects** (name), and **events** (event data).
- Results grouped by category with highlighted matches.
- Clicking a result navigates to the relevant detail page.
- Debounced input (200ms) to avoid excessive API calls.

### Search Indexing

| Index | Indexed Fields | Filterable | Sortable |
|-------|---------------|------------|----------|
| `issues` | title, fingerprint, metadata, level, status | project_id, status, level | last_seen, event_count |
| `events` | event_id, data (message, stack trace, tags) | project_id, issue_id | timestamp |
| `projects` | name, slug, platform | — | created_at |

- Indexes are updated asynchronously via **Celery tasks** on create/update/delete.
- Full re-index available via `make reindex` Makefile target.

---

## 7. Notification System

### 7.1 In-App Notifications (Bell Icon)

- **Bell icon** in header bar with unread count badge.
- Dropdown panel shows recent notifications grouped by project.
- Each notification: icon (error/warning/info), title, project name, relative time.
- "Mark all read" and per-item "mark read" actions.
- **Real-time delivery** via WebSocket (Redis pub/sub → backend WS → frontend).

### 7.2 Email Notifications

- Sent when a **new issue** is created or a **resolved issue regresses**.
- Only sent to users **subscribed to the project**.
- Requires SMTP configuration in Settings.
- Email contains: issue title, stack trace summary, direct link to issue detail.
- **Throttling** — Configurable rate limit per project (e.g., max 10 emails/hour).

### 7.3 Notification Preferences

Users can configure per-project:
- Receive in-app only / email only / both / none
- Frequency: every occurrence / first only / every Nth

---

## 8. Sentry API Compatibility

### 8.1 Ingest Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /api/{project_id}/store/` | Legacy store endpoint |
| `POST /api/{project_id}/envelope/` | Envelope endpoint (modern SDKs) |
| `GET /api/{project_id}/security/` | CSP/security reports |

### 8.2 DSN Format

```
https://<public_key>@<host>/api/<project_id>
```

Generated per-project. Displayed in project settings with copy-to-clipboard.

### 8.3 Event Processing

1. **Auth** — Validate DSN public key against project.
2. **Parse** — Decode envelope/JSON payload, extract exception, breadcrumbs, contexts.
3. **Fingerprint** — Group by exception type + top frame (configurable).
4. **Dedup** — If existing issue matches fingerprint → increment count, update `last_seen`.
5. **Store** — Persist raw event JSON + normalized issue record.
6. **Side-effects** — Trigger notification tasks if issue is new or regressed.

### 8.4 Sentry-Compatible REST API (`/api/0/`)

To enable integration with **Sentry CLI**, **Sentry MCP Server**, and other Sentry-compatible tooling, MegooBug exposes a compatibility API layer under the `/api/0/` prefix. This mirrors the subset of Sentry's Web API that external tools rely on.

> **Note:** MegooBug is single-organization by design. The `{organization_slug}` parameter in Sentry's API is accepted but ignored — all projects belong to the single instance.

#### Authentication

All `/api/0/` endpoints authenticate via **Bearer token** in the `Authorization` header:

```
Authorization: Bearer <api_token>
```

Tokens are scoped API keys created per-user in **Settings → API Keys**. Each token carries the same role permissions as its owner.

#### Compatibility Endpoints

| Method | Path | Sentry Equivalent | Description |
|--------|------|-------------------|-------------|
| GET | `/api/0/` | `/api/0/` | API index / server info |
| GET | `/api/0/organizations/` | List orgs | Returns single org (the instance) |
| GET | `/api/0/organizations/{org}/` | Org detail | Instance detail |
| GET | `/api/0/organizations/{org}/projects/` | List org projects | All projects |
| GET | `/api/0/projects/` | List projects | All projects (flat) |
| GET | `/api/0/projects/{org}/{project_slug}/` | Project detail | Project by slug |
| GET | `/api/0/projects/{org}/{project_slug}/issues/` | List project issues | Filterable issue list |
| GET | `/api/0/organizations/{org}/issues/` | List org issues | All issues across projects |
| GET | `/api/0/issues/{issue_id}/` | Issue detail | Full issue with metadata |
| PUT | `/api/0/issues/{issue_id}/` | Update issue | Resolve, ignore, assign |
| GET | `/api/0/issues/{issue_id}/events/` | Issue events | Events for an issue |
| GET | `/api/0/issues/{issue_id}/events/latest/` | Latest event | Most recent event |
| GET | `/api/0/events/{event_id}/` | Event detail | Full event payload |
| GET | `/api/0/projects/{org}/{project_slug}/keys/` | List DSN keys | Client keys (DSNs) |

#### Sentry CLI Configuration

Users can configure Sentry CLI to point at MegooBug by setting:

```bash
# Environment variables
export SENTRY_URL=http://your-megoobug-host:8000
export SENTRY_AUTH_TOKEN=<your-api-token>
export SENTRY_ORG=megoobug            # accepted but ignored
export SENTRY_PROJECT=<project-slug>
```

Or via `.sentryclirc`:

```ini
[defaults]
url = http://your-megoobug-host:8000
org = megoobug
project = <project-slug>

[auth]
token = <your-api-token>
```

#### Sentry MCP Server Configuration

For AI agent integration via the **Sentry MCP Server** (`@sentry/mcp-server`), configure it in local/stdio mode pointing at the MegooBug instance:

```json
{
  "mcpServers": {
    "MegooBug": {
      "command": "npx",
      "args": [
        "@sentry/mcp-server@latest",
        "--access-token", "<your-api-token>"
      ],
      "env": {
        "SENTRY_URL": "http://your-megoobug-host:8000"
      }
    }
  }
}
```

This allows AI coding assistants (Cursor, Claude Desktop, etc.) to query issues, investigate errors, and search events directly from MegooBug.

### 8.5 API Token Management

#### Token Model

```
api_tokens
├── id (UUID, PK)
├── user_id (FK → users)
├── name (str — human label, e.g. "CI/CD Token")
├── token_hash (str — bcrypt hash of the token; raw token shown once on creation)
├── token_prefix (str — first 8 chars, for display/identification)
├── scopes (JSONB — reserved for future fine-grained permissions)
├── last_used_at (datetime, nullable)
├── expires_at (datetime, nullable — null = never expires)
├── created_at
└── updated_at
```

#### Token Lifecycle

1. **Create** — User navigates to **Settings → API Keys** → "Create Token". Enters a name, optional expiry. System generates a random token (`mgb_<32-char-hex>`), displays it **once**, stores only the hash.
2. **Use** — Token is sent as `Bearer <token>` on `/api/0/` requests. Backend hashes the incoming token and looks up by `token_prefix` + hash comparison.
3. **Revoke** — User deletes the token from Settings. Immediate invalidation.
4. **Expiry** — If `expires_at` is set and passed, the token is rejected.

#### Token Format

Tokens use a recognizable prefix for easy identification:

```
mgb_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
└─┘ └──────────────────────────────────┘
prefix          32 random hex chars
```

---

## 9. Database Schema (Key Models)

```
users
├── id (UUID, PK)
├── email (unique)
├── name
├── password_hash
├── role (enum: admin, developer, viewer)
├── is_active (bool)
├── avatar_url
└── created_at / updated_at

projects
├── id (UUID, PK)
├── name
├── slug (unique)
├── platform (str)
├── dsn_public_key (unique)
├── created_by (FK → users)
└── created_at / updated_at

project_members
├── project_id (FK)
├── user_id (FK)
├── notify_email (bool)
├── notify_inapp (bool)
└── joined_at

issues
├── id (UUID, PK)
├── project_id (FK)
├── title (str)
├── fingerprint (str, indexed)
├── status (enum: unresolved, resolved, ignored)
├── level (enum: fatal, error, warning, info)
├── first_seen / last_seen
├── event_count (int)
└── metadata (JSONB)

events
├── id (UUID, PK)
├── issue_id (FK)
├── project_id (FK)
├── event_id (str, Sentry event ID)
├── data (JSONB — full event payload)
├── timestamp
└── received_at

notifications
├── id (UUID, PK)
├── user_id (FK)
├── issue_id (FK, nullable)
├── project_id (FK, nullable)
├── type (enum: new_issue, regression, assigned, mention)
├── title / body
├── is_read (bool)
└── created_at

invites
├── id (UUID, PK)
├── email
├── role
├── token (unique)
├── invited_by (FK → users)
├── expires_at
├── accepted_at (nullable)
└── created_at

settings
├── key (PK, str)
├── value (JSONB)
└── updated_at

api_tokens
├── id (UUID, PK)
├── user_id (FK → users)
├── name (str)
├── token_hash (str)
├── token_prefix (str, 8 chars)
├── scopes (JSONB)
├── last_used_at (nullable)
├── expires_at (nullable)
├── created_at
└── updated_at
```

---

## 10. API Endpoints (Backend)

### Auth
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/login` | Login (returns JWT) |
| POST | `/api/v1/auth/signup` | Register (if enabled) |
| POST | `/api/v1/auth/refresh` | Refresh access token |
| POST | `/api/v1/auth/logout` | Invalidate refresh token |
| POST | `/api/v1/auth/accept-invite` | Register via invite token |

### Users
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/users` | List users (admin) |
| GET | `/api/v1/users/me` | Current user profile |
| PATCH | `/api/v1/users/me` | Update profile |
| PATCH | `/api/v1/users/me/password` | Change password |
| PATCH | `/api/v1/users/{id}/role` | Change role (admin) |
| PATCH | `/api/v1/users/{id}/status` | Enable/disable user (admin) |
| DELETE | `/api/v1/users/{id}` | Remove user (admin) |

### Invites
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/invites` | Create invite (admin) |
| GET | `/api/v1/invites` | List pending invites |
| DELETE | `/api/v1/invites/{id}` | Revoke invite |

### Projects
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/projects` | List projects |
| POST | `/api/v1/projects` | Create project |
| GET | `/api/v1/projects/{slug}` | Project detail |
| PATCH | `/api/v1/projects/{slug}` | Update project |
| DELETE | `/api/v1/projects/{slug}` | Delete project (admin) |
| GET | `/api/v1/projects/{slug}/members` | List members |
| POST | `/api/v1/projects/{slug}/members` | Add member |
| DELETE | `/api/v1/projects/{slug}/members/{uid}` | Remove member |

### Issues & Events
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/projects/{slug}/issues` | List issues (filterable) |
| GET | `/api/v1/issues/{id}` | Issue detail |
| PATCH | `/api/v1/issues/{id}` | Update status (resolve/ignore) |
| GET | `/api/v1/issues/{id}/events` | List events for issue |
| GET | `/api/v1/events/{id}` | Single event detail |

### Notifications
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/notifications` | List user notifications |
| PATCH | `/api/v1/notifications/{id}/read` | Mark as read |
| POST | `/api/v1/notifications/read-all` | Mark all as read |
| GET | `/api/v1/notifications/unread-count` | Unread badge count |
| WS | `/ws/notifications` | Real-time notification stream |

### Settings (Admin)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/settings` | Get all settings |
| PATCH | `/api/v1/settings` | Update settings |
| POST | `/api/v1/settings/smtp/test` | Send test email |

### API Tokens
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/api-tokens` | List current user's tokens |
| POST | `/api/v1/api-tokens` | Create token (returns raw token once) |
| DELETE | `/api/v1/api-tokens/{id}` | Revoke a token |

### Sentry Ingest
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/{project_id}/store/` | Legacy event store |
| POST | `/api/{project_id}/envelope/` | Envelope ingest |

### Stats
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/stats/dashboard` | Dashboard aggregates |
| GET | `/api/v1/stats/projects/{slug}/trends` | Error trend data |

### Search
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/search` | Global search (issues, projects, events) |
| GET | `/api/v1/search/issues` | Search issues only |
| GET | `/api/v1/search/events` | Search events only |

---

## 11. UI / UX Design

### 11.1 Theme — CyberPunk

**Color Palette:**

| Token | Dark Mode | Light Mode |
|-------|-----------|------------|
| `--bg-primary` | `#0a0a0f` | `#f0f0f5` |
| `--bg-secondary` | `#12121a` | `#e4e4ed` |
| `--bg-card` | `#1a1a2e` | `#ffffff` |
| `--accent-primary` | `#00f0ff` (cyan neon) | `#0088aa` |
| `--accent-secondary` | `#ff00ff` (magenta) | `#aa0088` |
| `--accent-warning` | `#ffcc00` (neon yellow) | `#cc9900` |
| `--accent-error` | `#ff3366` (hot pink) | `#cc1144` |
| `--accent-success` | `#00ff88` (neon green) | `#009955` |
| `--text-primary` | `#e0e0ff` | `#1a1a2e` |
| `--text-secondary` | `#8888aa` | `#555577` |
| `--border` | `#2a2a3e` | `#ccccdd` |
| `--glow` | `0 0 20px rgba(0,240,255,0.3)` | `none` |

**Design Language:**
- Neon glow effects on interactive elements (dark mode).
- Glassmorphism cards with `backdrop-filter: blur()` and subtle borders.
- Monospace/tech fonts for data (JetBrains Mono); clean sans-serif for UI (Inter/Outfit).
- Scan-line subtle texture overlay on dark backgrounds.
- Animated gradient borders on focused elements.
- Severity badges with pulsing glow animations.

### 11.2 Theme Switching

- Three modes: **Light**, **Dark**, **System** (follows `prefers-color-scheme`).
- Toggle in sidebar footer.
- Stored in `localStorage` and cookie (SSR hydration).
- Smooth CSS transition on switch (`transition: background-color 0.3s, color 0.3s`).

### 11.3 Responsive Breakpoints

| Breakpoint | Width | Layout |
|------------|-------|--------|
| Desktop | ≥1280px | Full sidebar + content |
| Tablet | 768–1279px | Collapsed sidebar (icons only) |
| Mobile | <768px | Hidden sidebar, hamburger menu drawer |

### 11.4 Sidebar Navigation

**Expanded state:**
- Logo + app name
- Nav items with icon + label: Dashboard, Projects, Users*, Settings
- Theme toggle (sun/moon/monitor icons)
- User avatar + name + logout

**Collapsed state:**
- Logo icon only
- Nav icons with tooltips
- Toggle button at bottom

**Mobile:**
- Hamburger icon in header triggers slide-in drawer with overlay.

> *Users link visible only to Admin role.

---

## 12. Environment Variables

```env
# ── General ──
APP_NAME=MegooBug
APP_URL=http://localhost:3000
SECRET_KEY=<random-64-char>
ENVIRONMENT=development          # development | production

# ── Auth ──
ALLOW_SIGNUP=false               # true | false
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
INVITE_TOKEN_EXPIRE_HOURS=48

# ── Database ──
POSTGRES_USER=megoo
POSTGRES_PASSWORD=password
POSTGRES_DB=megoobug
DATABASE_URL=postgresql+asyncpg://$POSTGRES_USER:$POSTGRES_PASSWORD@postgres:5432/$POSTGRES_DB

# ── Redis ──
REDIS_URL=redis://redis:6379/0

# ── SMTP (configurable via UI, env is fallback) ──
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_USE_TLS=true

# ── Meilisearch ──
MEILISEARCH_URL=http://meilisearch:7700
MEILISEARCH_MASTER_KEY=<random-32-char>

# ── Frontend ──
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000

# ── Seed Admin (used on first startup only) ──
ADMIN_EMAIL=admin@megoobug.local
ADMIN_PASSWORD=admin123456
ADMIN_NAME=Admin
```

---

## 13. Security Considerations

| Area | Implementation |
|------|----------------|
| Authentication | JWT with HTTP-only cookies (web UI); Bearer API tokens (`/api/0/` compat layer) |
| Authorization | Role-based middleware on every endpoint; API tokens inherit owner's role |
| API Tokens | Stored as bcrypt hashes; raw token shown once on creation; `mgb_` prefix for identification |
| DSN Auth | Public key validation on ingest endpoints |
| CSRF | SameSite cookie + CSRF token for mutations |
| Rate Limiting | Per-IP + per-DSN rate limits on ingest endpoints |
| Input Validation | Pydantic models for all request bodies |
| SQL Injection | SQLAlchemy ORM (parameterized queries) |
| XSS | React auto-escaping + CSP headers |
| Secrets | `.env` file, never committed; Docker secrets in prod |
| CORS | Configurable allowed origins |

---

## 14. Milestones

| Phase | Scope | Est. Duration |
|-------|-------|---------------|
| **Phase 1 — Foundation** ✅ | Project scaffold, Docker setup, Makefile, DB models (8), auth (login/signup/invite), user CRUD, role middleware, auto-migration, auto-seed, structured logging, CyberPunk CSS design system, frontend shell (all pages scaffolded) | 2 weeks |
| **Phase 2 — Core** | Project CRUD, Sentry ingest endpoints, event processing & grouping, issue management, API token management, Sentry-compatible REST API (`/api/0/`) for Sentry CLI & MCP integration | 3 weeks |
| **Phase 3 — Frontend** | Dashboard data integration, project detail with issues, issue detail with stack traces, user management integration | 3 weeks |
| **Phase 4 — Notifications** | WebSocket setup, in-app notification bell, email notifications, SMTP settings UI, notification preferences | 2 weeks |
| **Phase 5 — Polish** | CyberPunk theme finalization, responsive testing, dark/light/system, animations, performance optimization | 1 week |
| **Phase 6 — Release** | Documentation, README, contributing guide, CI/CD, initial release | 1 week |

---

## 15. Future Considerations (Post v1)

- **Source Maps** — Upload & process source maps for minified JS stack traces.
- **Alerting Rules** — Configurable conditions (error spike, new error type, etc.).
- **Integrations** — Slack, Discord, MS Teams webhooks.
- **Performance Monitoring** — Transaction tracing, spans, slow query detection.
- **Session Replay** — Record and replay user sessions.
- **Release Tracking** — Associate errors with deploy versions.
- **Multi-org / Teams** — Organization-level isolation.

---

> **Note:** This PRD is a living document. Update it as requirements evolve during implementation.
