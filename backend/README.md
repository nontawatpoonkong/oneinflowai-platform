# OneInFlow Platform — Backend

Modular Monolith backend. **Sprint 1 · Step 1** — infrastructure foundation only.

## Stack
Python 3.12 · FastAPI · PostgreSQL · SQLAlchemy 2.0 (async) · Alembic · Redis · Qdrant · Docker Compose · Pydantic v2

## What Step 1 includes
- Project structure (`app/` modular layout)
- Docker Compose (app, postgres, redis, qdrant) with healthchecks
- Async PostgreSQL connection + session management
- SQLAlchemy 2.0 declarative `Base` + UUID / timestamp mixins (foundation)
- Alembic (async) configuration
- Redis + Qdrant connections
- Configuration via `.env` (pydantic-settings)
- Structured JSON logging foundation
- Health check endpoints

> Not in Step 1: authentication, domain models, business logic, AI, RAG, LINE webhook.

## Endpoints
| Method | Path                   | Purpose                              |
|--------|------------------------|--------------------------------------|
| GET    | `/health`              | Liveness (always 200)                |
| GET    | `/health/readiness`    | Readiness — checks DB/Redis/Qdrant   |

## Run with Docker Compose
Dev (hot reload, console logs) — the override file is applied automatically:
```bash
cp .env.example .env
docker compose up --build
curl http://localhost:8000/health
curl http://localhost:8000/health/readiness
```

Prod (workers, JSON logs, no source mount):
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## Run locally (uv)
```bash
uv sync                        # creates .venv from uv.lock (add --no-dev for runtime-only)
cp .env.example .env           # keep *_HOST=localhost for local run
docker compose up -d postgres redis qdrant
uv run uvicorn app.main:app --reload
```

## Tooling
```bash
uv run ruff check .            # lint
uv run ruff format .           # format
uv run pytest                  # tests
uv run pre-commit install      # enable git hooks
```

## Email OTP delivery with Resend

Development and automated tests use the non-delivering `development` provider.
To perform a manual end-to-end test with a real recipient, configure these
environment-only values in the local `.env` file:

```dotenv
EMAIL_PROVIDER=resend
RESEND_API_KEY=<secret>
EMAIL_FROM_ADDRESS=<verified sender>
EMAIL_FROM_NAME=OneInFlow
OTP_HASH_SECRET=<secret>
```

In the Resend dashboard, create an API key and verify the sending domain. Add
the DNS records provided by Resend, wait for the domain to become verified, and
use an address on that domain for `EMAIL_FROM_ADDRESS`. Never commit `.env`.

Manual verification procedure:

1. Start PostgreSQL and apply the latest Alembic migration.
2. Start the backend and frontend with the environment above.
3. Register with an email inbox you control and confirm the OTP email arrives.
4. Enter the six-digit OTP, then log in successfully.
5. Register another address and confirm login is blocked before verification.
6. Exercise resend after the cooldown and confirm the new OTP works.
7. Enter an incorrect OTP and confirm verification is rejected.

Automated tests always inject fake SDK clients and never send real email.

## Observability
Every request gets an `X-Request-ID` (generated or echoed from the inbound
header). It is stored in a contextvar and injected into every log line, along
with `workspace_id` / `user_id` once the auth layer sets them (later sprint).

## Alembic
No models exist yet, so autogenerate produces an empty migration in Step 1.
```bash
alembic revision --autogenerate -m "init"
alembic upgrade head
```

## Layout
```
app/
  api/          # routers (health)
  core/         # config, logging, lifespan
  database/     # engine/session, Base, mixins, redis, qdrant
  schemas/      # standard response envelope
  models/       # (empty — Step 2)
  auth/ workspace/ customer/ conversation/ knowledge/ integrations/ ai/
  repositories/ services/ utils/
alembic/        # migration environment
```
