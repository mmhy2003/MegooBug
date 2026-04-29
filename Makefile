.PHONY: help dev prod down logs migrate seed test lint clean shell-be shell-fe reindex

.DEFAULT_GOAL := help

# ── Help ──
help:
	@echo ""
	@echo "  MegooBug - Available Commands"
	@echo "  ============================="
	@echo ""
	@echo "  Development:"
	@echo "    make dev          Build and start dev stack (detached)"
	@echo "    make prod         Build and start production stack"
	@echo "    make down         Stop all containers"
	@echo ""
	@echo "  Logs:"
	@echo "    make logs         Tail all service logs"
	@echo "    make logs-be      Tail backend logs only"
	@echo "    make logs-fe      Tail frontend logs only"
	@echo ""
	@echo "  Database:"
	@echo "    make migrate      Run Alembic migrations"
	@echo "    make migration    Create new migration (msg=\"description\")"
	@echo "    make seed         Seed admin user"
	@echo ""
	@echo "  Search:"
	@echo "    make reindex      Full Meilisearch re-index"
	@echo ""
	@echo "  Testing:"
	@echo "    make test         Run all tests"
	@echo "    make test-be      Run backend tests only"
	@echo "    make test-fe      Run frontend tests only"
	@echo ""
	@echo "  Code Quality:"
	@echo "    make lint         Lint backend + frontend"
	@echo ""
	@echo "  Utilities:"
	@echo "    make shell-be     Shell into backend container"
	@echo "    make shell-fe     Shell into frontend container"
	@echo "    make clean        Remove all volumes and images"
	@echo ""

# ── Development ──
dev:
	docker compose -f docker-compose.dev.yml up --build -d

# ── Production ──
prod:
	docker compose -f docker-compose.yml up --build -d

# ── Stop ──
down:
	docker compose -f docker-compose.dev.yml down
	docker compose -f docker-compose.yml down

# ── Logs ──
logs:
	docker compose -f docker-compose.dev.yml logs -f

logs-be:
	docker compose -f docker-compose.dev.yml logs -f backend

logs-fe:
	docker compose -f docker-compose.dev.yml logs -f frontend

# ── Database ──
migrate:
	docker compose -f docker-compose.dev.yml exec backend alembic upgrade head

migration:
	docker compose -f docker-compose.dev.yml exec backend alembic revision --autogenerate -m "$(msg)"

seed:
	docker compose -f docker-compose.dev.yml exec backend python -m app.scripts.seed

# ── Search ──
reindex:
	docker compose -f docker-compose.dev.yml exec backend python -m app.scripts.reindex

# ── Testing ──
test:
	docker compose -f docker-compose.dev.yml exec backend pytest
	docker compose -f docker-compose.dev.yml exec frontend npm test

test-be:
	docker compose -f docker-compose.dev.yml exec backend pytest

test-fe:
	docker compose -f docker-compose.dev.yml exec frontend npm test

# ── Linting ──
lint:
	docker compose -f docker-compose.dev.yml exec backend ruff check .
	docker compose -f docker-compose.dev.yml exec frontend npm run lint

# ── Cleanup ──
clean:
	docker compose -f docker-compose.dev.yml down -v --rmi local
	docker compose -f docker-compose.yml down -v --rmi local

# ── Shell Access ──
shell-be:
	docker compose -f docker-compose.dev.yml exec backend bash

shell-fe:
	docker compose -f docker-compose.dev.yml exec frontend sh
