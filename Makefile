.PHONY: dev prod down logs migrate seed test lint clean shell-be shell-fe reindex

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
