<div align="center">

# 🐛 MegooBug

**Open-source, self-hosted, Sentry-compatible error tracking.**

Drop in your existing Sentry DSN and start capturing errors instantly.

[![License: MIT](https://img.shields.io/badge/License-MIT-00f0ff.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-0088cc.svg)](docker-compose.yml)
[![Sentry SDK](https://img.shields.io/badge/Sentry_SDK-Compatible-ff3366.svg)](#sentry-sdk-setup)

</div>

---

## ✨ Features

- **🔌 Sentry SDK Compatible** — Works with any official Sentry SDK (Python, JavaScript, Go, Java, Ruby, etc.). Just swap your DSN.
- **⚡ Real-Time** — WebSocket-powered live updates across the entire UI. Issues, stats, and notifications update instantly.
- **🔍 Full-Text Search** — Instant, typo-tolerant search across issues, events, and projects powered by Meilisearch.
- **📧 Email Notifications** — Automated alerts on new issues and regressions with detailed HTML emails.
- **🔐 RBAC** — Three-tier role system (Admin / Developer / Viewer) with project-scoped access control.
- **🎨 Modern UI** — CyberPunk-inspired design with dark/light/system themes, glassmorphism, and micro-animations.
- **📱 Responsive** — Full mobile support with collapsible sidebar and adaptive layouts.
- **🐳 One-Command Deploy** — Production-ready Docker Compose setup with all dependencies included.
- **🔧 Sentry CLI & MCP** — Compatible with Sentry CLI and Sentry MCP Server for AI agent integration.

---

## 🏗️ Architecture

```
┌─────────────┐       ┌──────────────┐       ┌───────────┐
│  Sentry SDK │──────▶│  FastAPI      │──────▶│ PostgreSQL│
│  (clients)  │ HTTP  │  Backend      │       │           │
└─────────────┘       │  ┌──────────┐ │       └───────────┘
                      │  │ WebSocket│ │
┌─────────────┐       │  │ Server   │ │       ┌───────────┐
│  Next.js    │◀─────▶│  └──────────┘ │──────▶│   Redis   │
│  Frontend   │  API  │  ┌──────────┐ │       └───────────┘
└─────────────┘       │  │ Celery   │ │
                      │  │ Workers  │ │       ┌───────────┐
                      │  └──────────┘ │──────▶│Meilisearch│
                      └──────────────┘       └───────────┘
```

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 16 (App Router, TypeScript) |
| Backend | FastAPI (Python 3.12, async) |
| Database | PostgreSQL 16 |
| Cache / Pub-Sub | Redis 7 |
| Task Queue | Celery (Redis broker) |
| Search | Meilisearch |
| Containerization | Docker + Docker Compose |

---

## 🚀 Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/install/) v2+

### 1. Clone & Configure

```bash
git clone https://github.com/your-org/MegooBug.git
cd MegooBug

cp .env.example .env
# Edit .env — at minimum change SECRET_KEY and MEILISEARCH_MASTER_KEY
```

### 2. Start

**Development** (with hot-reload):

```bash
make dev
```

**Production**:

```bash
make prod
```

### 3. Access

| Service | URL |
|---------|-----|
| Frontend | [http://localhost:3000](http://localhost:3000) |
| Backend API | [http://localhost:8000](http://localhost:8000) |
| API Docs | [http://localhost:8000/docs](http://localhost:8000/docs) |

**Default admin credentials** (change these in `.env`):

```
Email:    admin@megoobug.local
Password: admin123456
```

> The database auto-migrates and seeds the admin user on first startup — no manual steps needed.

---

## 🔌 Sentry SDK Setup

MegooBug is fully compatible with Sentry SDKs. Point your DSN to your MegooBug instance:

### 1. Create a Project

Log in → **Projects** → **Create Project** → Copy the displayed DSN.

### 2. Configure Your App

**Python:**

```python
import sentry_sdk

sentry_sdk.init(
    dsn="http://<public_key>@your-megoobug-host:8000/api/<project_id>",
)
```

**JavaScript:**

```javascript
import * as Sentry from "@sentry/browser";

Sentry.init({
  dsn: "http://<public_key>@your-megoobug-host:8000/api/<project_id>",
});
```

**Any Sentry SDK** — just replace the DSN with the one from your MegooBug project settings.

---

## 🛠️ Sentry CLI & MCP Server

### Sentry CLI

```bash
export SENTRY_URL=http://your-megoobug-host:8000
export SENTRY_AUTH_TOKEN=<your-api-token>   # Create in Settings → API Keys
export SENTRY_ORG=megoobug                  # Accepted but ignored (single-org)
export SENTRY_PROJECT=<project-slug>
```

### Sentry MCP Server (AI Agents)

```json
{
  "mcpServers": {
    "MegooBug": {
      "command": "npx",
      "args": ["@sentry/mcp-server@latest", "--access-token", "<your-api-token>"],
      "env": { "SENTRY_URL": "http://your-megoobug-host:8000" }
    }
  }
}
```

This lets AI coding assistants (Cursor, Claude Desktop, etc.) query issues and investigate errors directly from MegooBug.

---

## 📄 Pages & Features

### Dashboard

Real-time overview with project count, error rate (24h), unresolved issues, and active users. Includes a live-updating recent issues table.

### Projects

Project cards with unresolved issue badges. Each project includes:

- **Overview** — DSN display, 14-day error trend chart, project metadata.
- **Issues** — Filterable table with inline Resolve/Ignore actions. Real-time updates via WebSocket.
- **Settings** — Project config, member management, danger zone.

### Issue Detail

Rich 5-tab issue viewer:

| Tab | Content |
|-----|---------|
| **Stack Trace** | Exception chain with expandable source context, in-app frame badges, line-by-line code highlighting |
| **Breadcrumbs** | Timestamped trail of user actions/logs leading to the error |
| **Context** | HTTP request (method, URL, headers), user identity (ID, email, IP), device/OS/browser/runtime info, extra data, installed modules |
| **Events** | Timeline of all occurrences |
| **Details** | Issue metadata, fingerprint, tags, SDK info, environment |

### Users (Admin)

User management with role permissions guide, inline role switching, enable/disable, project assignment modal, and invite system.

### Settings

Role-aware tab layout:

| Role | Tabs |
|------|------|
| Admin | General, SMTP, Profile, API Keys |
| Developer | Profile, API Keys |
| Viewer | Profile |

### Global Search

`Ctrl+K` / `⌘K` command palette with instant full-text search across issues, events, and projects.

---

## 🔐 Roles & Permissions

| Permission | Admin | Developer | Viewer |
|------------|:-----:|:---------:|:------:|
| View dashboard & issues | ✅ All | ✅ Own | ✅ Own |
| Resolve / Ignore issues | ✅ | ✅ | ❌ |
| Create / Edit projects | ✅ | ✅ | ❌ |
| Delete projects | ✅ | ❌ | ❌ |
| Manage users & roles | ✅ | ❌ | ❌ |
| Configure settings | ✅ | ❌ | ❌ |
| API Keys | ✅ | ✅ | ❌ |

> Non-admin users only see projects they've been assigned to. All access checks are enforced on both frontend and backend.

---

## ⚙️ Configuration

All configuration is via environment variables (`.env` file):

```env
# ── General ──
APP_NAME=MegooBug
APP_URL=http://localhost:3000        # Public-facing URL
SECRET_KEY=<random-64-chars>         # ⚠️ Change this!
ENVIRONMENT=production

# ── Auth ──
ALLOW_SIGNUP=false                   # Open registration or invite-only
INVITE_TOKEN_EXPIRE_HOURS=48

# ── Database ──
POSTGRES_USER=megoo
POSTGRES_PASSWORD=<strong-password>
POSTGRES_DB=megoobug

# ── SMTP (optional — also configurable via Settings UI) ──
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=noreply@example.com
SMTP_PASSWORD=<password>
SMTP_FROM_EMAIL=noreply@example.com

# ── Meilisearch ──
MEILISEARCH_MASTER_KEY=<random-32-chars>  # ⚠️ Change this!

# ── Seed Admin ──
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=<strong-password>
ADMIN_NAME=Admin
```

See [`.env.example`](.env.example) for the full template.

---

## 📋 Makefile Commands

```
make dev          Build & start development stack (hot-reload)
make prod         Build & start production stack
make down         Stop all containers
make logs         Tail all service logs
make logs-be      Tail backend logs
make logs-fe      Tail frontend logs
make migrate      Run Alembic migrations
make seed         Seed admin user
make reindex      Full Meilisearch re-index
make test         Run all tests
make lint         Lint backend + frontend
make shell-be     Shell into backend container
make shell-fe     Shell into frontend container
make clean        Remove all volumes and images
```

---

## 📁 Project Structure

```
MegooBug/
├── frontend/               # Next.js 16 (App Router, TypeScript)
│   ├── src/
│   │   ├── app/            # Pages & layouts
│   │   ├── components/     # Shared UI (sidebar, header, search, websocket)
│   │   └── lib/            # API client, WebSocket hook
│   ├── Dockerfile          # Production multi-stage build
│   └── Dockerfile.dev      # Development with hot-reload
├── backend/                # FastAPI (Python 3.12, async)
│   └── app/
│       ├── api/            # REST endpoints + WebSocket + Sentry ingest
│       ├── models/         # SQLAlchemy ORM models
│       ├── services/       # Business logic (auth, ingest, email, pubsub)
│       ├── tasks/          # Celery background tasks
│       └── scripts/        # CLI utilities (seed, reindex)
├── docker-compose.yml      # Production
├── docker-compose.dev.yml  # Development
├── Makefile                # Convenience commands
├── .env.example            # Configuration template
└── docs/
    └── prd.md              # Product Requirements Document
```

---

## 🔔 Notification System

### In-App (Real-Time)

- Bell icon with live unread badge
- WebSocket push via Redis pub/sub
- 30-second polling fallback when disconnected

### Email

- Triggered on new issues and regressions
- CyberPunk-themed HTML templates with direct issue links
- Per-project opt-in via `notify_email` flag
- SMTP configurable via Settings UI or environment variables

---

## 🤝 Contributing

Contributions are welcome! Here's how to get started:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Start the dev stack: `make dev`
4. Make your changes (frontend hot-reloads, backend auto-restarts)
5. Run linting: `make lint`
6. Commit your changes: `git commit -m "feat: add my feature"`
7. Push and open a PR

### Development Tips

- Frontend: `http://localhost:3000` with Turbopack hot-reload
- Backend: `http://localhost:8000/docs` for interactive API docs
- Backend logs: `make logs-be`
- Database auto-migrates on startup — no manual migration needed

---

## 📜 License

MegooBug is open-source software licensed under the [MIT License](LICENSE).

---

<div align="center">

**Built with ❤️ for developers who want to own their error tracking.**

[Documentation](docs/prd.md) · [Report Bug](../../issues) · [Request Feature](../../issues)

</div>