# Forte dev commands. Run `make help`.
SHELL := /bin/bash
API := cd api &&
WEB := cd web &&

.PHONY: help setup up down reset-db api web migrate migration test test-api test-web lint fmt \
        openapi gen check seed demo-reset paystub-pdfs key

help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-14s %s\n",$$1,$$2}'

setup: ## First-time setup: .env, deps, containers, migrations
	@[ -f .env ] || cp .env.example .env
	$(API) uv sync
	$(WEB) npm ci
	$(MAKE) up migrate

up: ## Start Postgres, Mailpit, MinIO (+ create versioned bucket)
	docker compose up -d db mailpit minio minio-init

down: ## Stop containers (data kept)
	docker compose down

reset-db: ## Drop ALL local data (db + minio volumes) and start fresh
	docker compose down -v && $(MAKE) up migrate

api: ## Run the API with reload on :8000
	$(API) uv run --env-file ../.env uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

web: ## Run the web app on :3000 (0.0.0.0 so a phone on the same Wi-Fi can reach it)
	$(WEB) npm run dev -- -H 0.0.0.0

migrate: ## Apply migrations
	$(API) uv run --env-file ../.env alembic upgrade head

migration: ## New migration: make migration m="add foo"
	$(API) uv run --env-file ../.env alembic revision --autogenerate -m "$(m)"

test: test-api test-web ## All tests

test-api: ## API tests (Postgres needed; storage is in-memory)
	$(API) uv run --env-file ../.env pytest

test-web: ## Web typecheck + lint
	$(WEB) npm run typecheck && npm run lint

lint: ## Lint everything
	$(API) uv run ruff check . && uv run ruff format --check .
	$(WEB) npm run lint

fmt: ## Auto-format the API
	$(API) uv run ruff format . && uv run ruff check --fix .

openapi: ## Write api/openapi.json from the FastAPI app
	$(API) uv run python -m app.openapi > openapi.json

gen: openapi ## Regenerate web/src/lib/api/schema.d.ts from the API (run after changing schemas)
	$(WEB) npm run gen:api

check: lint test gen ## What CI runs; also fails if generated files are stale
	git diff --exit-code -- api/openapi.json web/src/lib/api/schema.d.ts

seed: ## Load a demo scene: make seed scene=demo  (empty | demo | demo_paid)
	$(API) uv run --env-file ../.env python -m app.seed $(scene)

demo-reset: ## Reset to the demo starting point (scene demo)
	$(MAKE) seed scene=demo

paystub-pdfs: ## Render+store any final paystub PDFs that are missing (never re-renders)
	$(API) uv run --env-file ../.env python -m app.paystubs.pdf_store

key: ## Generate a new Fernet encryption key
	@python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
