# Centinela Backend

Closed-source ingestion & query API for the Centinela "flight recorder" for AI agents.
FastAPI + PostgreSQL 16 + SQLAlchemy 2 + Alembic. Runs 100% locally.

## Endpoints

- `POST /v1/events` — batch ingest (≤ 500 events). Auth via `X-Centinela-Key`. Validates
  per event and returns `{"accepted": n, "rejected": [{"index", "error"}]}`.
- `GET /v1/traces/{trace_id}` — full trace, events ordered by timestamp.
- `GET /v1/traces?from=&to=&limit=&offset=` — paginated trace summaries for the caller's org.
- `GET /health` — liveness + DB check.

All data is scoped to the org resolved from the API key (strict multitenancy).

## Quickstart — sin Docker (Postgres nativo)

Requires Python 3.11+ and a local PostgreSQL 16 with a `centinela` role and a
`centinela_dev` database (`CENTINELA_DATABASE_URL` overrides the default DSN).

```bash
python -m venv .venv && .venv/Scripts/activate        # Windows; use source .venv/bin/activate on Unix
pip install -e ".[dev]"                                 # install backend + dev deps
copy .env.example .env                                  # adjust CENTINELA_DATABASE_URL if needed
alembic upgrade head                                    # create tables + monthly partitions
uvicorn app.main:app --port 8000                        # serve the API
```

## Quickstart — con Docker (solo Postgres)

Same as above but the database runs in a container instead of a native install:

```bash
docker compose up -d                                    # start Postgres 16 (port 5432)
alembic upgrade head                                    # migrate
uvicorn app.main:app --port 8000                        # serve the API
```

## Admin CLI

```bash
python cli.py create-org "Acme"                         # -> prints org id
python cli.py create-key <org-id-or-name> "prod key"    # prints the key ONCE
python cli.py revoke-key <api-key-id>
python cli.py cleanup --older-than-days 30              # delete events past retention
```

## Tests & smoke

```bash
pytest                                                  # suite runs against a real Postgres test DB
python scripts/smoke_e2e.py                              # real SDK -> API -> Postgres, 10k events
```

`pytest` uses `CENTINELA_TEST_DATABASE_URL` (default `centinela_test`); it migrates and
TRUNCATEs between tests. The smoke script provisions a fresh org/key, emits 10,000 events
through the real SDK, and verifies they all land complete and ordered. Point it elsewhere
with `CENTINELA_ENDPOINT` (default `http://localhost:8000`).

## Configuration

Environment variables (prefix `CENTINELA_`, see `.env.example`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `CENTINELA_DATABASE_URL` | `postgresql+psycopg://centinela:centinela@localhost:5432/centinela_dev` | Postgres DSN |
| `CENTINELA_MAX_BATCH` | `500` | Max events per ingest request |
| `CENTINELA_MAX_BODY_BYTES` | `8388608` | Request-size guard (8 MiB) |
| `CENTINELA_MAX_LIST_LIMIT` | `1000` | Cap on trace-list page size |

## Partitions

The `events` table is RANGE-partitioned by month on `timestamp`. The initial migration
creates partitions for 2025–2027 plus an `events_default` catch-all. To add future
months, follow the pattern documented at the bottom of
`alembic/versions/0001_initial.py`.
