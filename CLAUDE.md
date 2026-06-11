# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

The SDK (Bloque 1) and the backend (Bloque 2) are implemented. The `centinela` package lives at the repo root; the closed-source ingestion/query API lives in `backend/`. Dashboard and landing (Bloques 3–4) are not in this repo — see "Wider product" below. The sections below describe the intended design; keep them in sync as code evolves.

### Layout

- `centinela/` — the SDK package. `client.py` (the `Centinela` entry point), `trace.py` (the `trace`/`log_action` API + the active-trace `contextvars`), `transport.py` (async queue + background flush thread, fail-open delivery, `stdout` mode), `events.py` (the `Event` dataclass and its JSON contract), `config.py` (env-var resolution; dev endpoint defaults to `http://localhost:8000` when `CENTINELA_ENV=dev`), `errors.py`.
- `centinela/integrations/` — `wrap()` auto-instrumentation. `__init__.py` does framework detection by module name + duck typing (no framework is an import-time dependency); `openai.py` / `anthropic.py` patch the client's `create` method; `langchain.py` builds a `BaseCallbackHandler` lazily; `_common.py` has the shared span emitter that attaches to the active trace or starts a standalone one.
- `tests/` — SDK pytest. `conftest.py` provides a `captured` fixture (a client whose transport is swapped for an in-memory capture) used to assert on emitted events without a network backend.
- `backend/` — the closed-source FastAPI ingestion/query API. See "Backend" under "Wider product" and `backend/README.md`.

## What this is

CENTINELA is a **flight recorder & firewall for AI agents** — a black box that records agent actions as auditable evidence. The product is positioned as auditable evidence + (v2) blocking, deliberately *not* "another observability tool."

**Open-core model:** this repo (`centinela-ai/centinela-python`) is the open-source Python SDK (MIT). It only *records and ships events*. A separate closed-source SaaS backend visualizes them and (v2) enforces blocking. The SDK must never assume backend behavior beyond the event contract below.

CENTINELA spans more than this repo: a closed-source **backend** (event ingestion + read API), a **dashboard**, and a **landing page**. They are separate components (this repo is only the SDK). Their specs are summarized under "Wider product" below so SDK changes stay consistent with what consumes the events.

## Architecture (SDK v0.1)

The SDK is built around one principle: **it must never break or slow down the customer's agent.** Everything follows from that.

- **Public entry point** is the `Centinela` class. Two instrumentation paths:
  - `c.wrap(agent)` — automatic. v0.1 supports LangChain (`BaseCallbackHandler`) and monkey-patching the OpenAI / Anthropic SDK clients. Unrecognized frameworks must raise a clear error linking to manual instrumentation — never fail silently.
  - `c.trace(name)` context manager + `t.log_action(...)` — manual, framework-agnostic, works anywhere.
- **Event delivery is async and non-blocking.** Events go to an in-memory queue; a background thread flushes every **2 seconds or 20 events**, whichever comes first.
- **Fail-open is non-negotiable.** If the backend is unreachable or errors, the customer's agent must never crash or stall — log a warning and drop/retry, but never propagate. Any change that could let SDK failure surface into the host application is a regression.
- **Minimal dependencies.** Only `httpx`. Adding heavy dependencies works against adoption and should be avoided; justify any new dependency.
- **Python ≥ 3.9.**
- **Auth:** the SDK authenticates to the backend by sending the API key in the `X-Centinela-Key` request header.
- **Redaction is a v0.1 feature, not a later add-on.** `c = Centinela(..., redact=True)` must strip/exclude `input`/`output` payloads before they leave the process. This is a compliance selling point — keep it in scope.
- **`stdout` endpoint mode.** When `CENTINELA_ENDPOINT=stdout`, the SDK prints events instead of shipping them. This lets the SDK work and demo locally with no backend — keep it functional.

### Standard event contract

Every recorded action serializes to this JSON shape. Keep it stable — the backend depends on it:

```json
{
  "trace_id": "uuid", "span_id": "uuid", "parent_span_id": null,
  "project": "str", "timestamp": "ISO8601",
  "type": "tool_call | llm_call | agent_start | agent_end | error",
  "name": "str", "input": {}, "output": {}, "metadata": {},
  "duration_ms": 0, "status": "ok | error"
}
```

### Configuration (environment variables)

- `CENTINELA_API_KEY` — auth key (`ctl_...`); sent to the backend as the `X-Centinela-Key` header.
- `CENTINELA_ENDPOINT` — backend URL; overridable for future self-hosting. Special value `stdout` prints events locally instead of shipping (demo/no-backend mode).
- `CENTINELA_DISABLED=true` — kill switch; the SDK becomes a no-op.

## Commands

```powershell
# Set up an environment (Windows / PowerShell)
python -m venv .venv ; .venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# Run the full test suite
pytest -q

# Run a single test file / test
pytest tests/test_wrap.py
pytest tests/test_wrap.py::test_wrap_openai_records_llm_call

# Try the SDK with no backend (prints events to stdout)
$env:CENTINELA_ENDPOINT = "stdout"

# Build a distribution (for PyPI)
python -m build
```

CI runs `pytest` across Python 3.9–3.13 (`.github/workflows/ci.yml`). Publishing to PyPI is automated on GitHub release via trusted publishing (`.github/workflows/publish.yml`).

## Wider product

The dashboard and landing live outside this repo. The **backend lives in `backend/`** (closed-source). Summarized here so the SDK's event contract and config stay aligned with their consumers. **Deploy is deliberately simple: one service, no Kubernetes, no microservices.**

### Backend (`backend/`) — FastAPI + PostgreSQL 16, runs 100% locally

Stack: Python 3.11+, FastAPI, SQLAlchemy 2 + Alembic (psycopg 3 driver), Pydantic 2, typer CLI. Tests use pytest + httpx against a real Postgres (no DB mocks).

Layout: `app/main.py` (app + body-size middleware), `app/routers/` (`health`, `events`, `traces`), `app/models.py` (`Org`, `ApiKey`, `Event`), `app/schemas.py` (Pydantic ingest/read models), `app/auth.py` (`require_org` dependency), `app/security.py` (key generation + salted SHA-256), `app/config.py`, `app/db.py`. Migrations in `alembic/versions/`. Admin CLI at `cli.py`. Smoke test at `scripts/smoke_e2e.py`.

Endpoints:
- `POST /v1/events` — batch ingest (≤ 500). Auth via `X-Centinela-Key`. Validates per event, rejecting only invalid ones: `{"accepted": n, "rejected": [{"index", "error"}]}`.
- `GET /v1/traces?from=&to=&limit=&offset=` — paginated trace summaries (count, error_count, duration) for the caller's org.
- `GET /v1/traces/{trace_id}` — full trace, events ordered by timestamp; 404 if unknown.
- `GET /health` — liveness + DB check.

Data model: `orgs`, `api_keys` (public `key_prefix` indexed for O(1) lookup, salted SHA-256 `key_hash`, never plaintext, `revoked_at`), `events` (full payload in JSONB, **RANGE-partitioned by month on `timestamp`** — composite PK `(id, timestamp)`; partitions created via raw SQL in the migration). **Strict multitenancy:** every query is filtered by the `org_id` resolved from the API key; an optional `org_id` param must match (403 otherwise).

Rate limiting in this phase is intentionally just a request-size guard (`CENTINELA_MAX_BODY_BYTES`); sophisticated per-key limits are out of scope. Retention is enforced manually via `cli.py cleanup --older-than-days N`.

**Closure criterion:** `scripts/smoke_e2e.py` must pass — the real SDK emits 10,000 events (nested traces) to a running backend and the script verifies all 10,000 land complete and ordered.

### Backend commands

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate   # Windows; source .venv/bin/activate on Unix
pip install -e ".[dev]"
alembic upgrade head                              # tables + monthly partitions
uvicorn app.main:app --port 8000                 # serve the API
pytest                                            # suite against a real Postgres test DB
python scripts/smoke_e2e.py                       # 10k-event end-to-end smoke (closure criterion)
python cli.py create-org "Acme"                  # admin: orgs/keys/cleanup
docker compose up -d                              # alternative: Postgres in a container
```

### Dashboard — Next.js + Tailwind on Vercel, Supabase Auth (Google + GitHub)

Exactly three screens in v0.1, nothing more:
1. **Traces** — table with filters (project, status, date); columns: name, time, duration, #actions, status.
2. **Trace detail** — timeline/tree of actions with expandable input/output. This is the README GIF; it must look good.
3. **Setup** — API key + copyable install snippet.

Language v0.1: English, with an ES toggle only if cheap; otherwise English-only and ES on the landing.

### Landing + pricing

Bilingual (EN default, `/es`): problem (costly agent failures) → demo GIF → quickstart → "Start free" CTA. Show pricing from day one even though only the free tier exists — Free (7-day retention) / Pro $49/mo (coming soon: alerts, 90d retention, reports) / Enterprise (contact). Day-one legal: Privacy Policy + Terms, clear notice of what data the backend receives, and the SDK `redact=True` option as the compliance answer.

## Out of MVP scope — note it and resist

Do not build these in Fase 1 (some are announced as roadmap for positioning, but not implemented):
- Real-time action **blocking** (Fase 2 — the firewall positioning advertises it as roadmap only).
- Hallucination detection, evals, alerts, PDF reports, multi-team, SSO.

## Conventions

- The README is the repo's landing page and a primary adoption surface — keep the 3-line quickstart, supported-frameworks table, bilingual (EN/ES) tagline, and "Why" section accurate and current when SDK behavior changes.
- Public API stability matters: `Centinela`, `wrap`, `trace`, `log_action`, the `redact` option, and the event schema are the contract. Treat changes to them as breaking.
