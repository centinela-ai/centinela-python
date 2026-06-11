"""End-to-end smoke test: real SDK -> running backend -> Postgres.

Closure criterion for Bloque 2. Emits 10,000 events through the real Centinela
SDK (nested traces), waits for the async flush, then verifies via the HTTP API
that all 10,000 landed and that an arbitrary trace is retrievable, complete, and
ordered by timestamp.

Prerequisites:
  - Postgres up and migrated.
  - The API running at $CENTINELA_ENDPOINT (default http://localhost:8000):
        uvicorn app.main:app --port 8000

Run from the backend/ directory:
    python scripts/smoke_e2e.py
"""

from __future__ import annotations

import os
import sys
import time
import uuid

import httpx

# Backend modules (direct DB access to provision a fresh org + key).
from app.db import SessionLocal
from app.models import ApiKey, Org
from app.security import generate_key

# The real SDK under test.
from centinela import Centinela

ENDPOINT = os.environ.get("CENTINELA_ENDPOINT", "http://localhost:8000").rstrip("/")
TARGET_EVENTS = 10_000
TRACES = 1_000
ACTIONS_PER_TRACE = 9  # + 1 agent_end emitted on trace exit == 10 events/trace


def _provision_org_key() -> tuple[str, str]:
    """Create a fresh org + key so this run's events are isolated."""
    with SessionLocal() as db:
        org = Org(name=f"smoke-{uuid.uuid4().hex[:8]}")
        db.add(org)
        db.flush()
        generated = generate_key()
        db.add(
            ApiKey(
                org_id=org.id,
                name="smoke",
                key_prefix=generated.prefix,
                key_hash=generated.key_hash,
                salt=generated.salt,
            )
        )
        db.commit()
        return str(org.id), generated.full_key


def _wait_for_health(timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{ENDPOINT}/health", timeout=2.0)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise SystemExit(f"FAIL: backend not healthy at {ENDPOINT}")


def _emit(api_key: str) -> list[str]:
    client = Centinela(
        api_key=api_key,
        project="smoke",
        endpoint=ENDPOINT,
        max_batch=500,
        flush_interval=0.5,
    )
    trace_ids: list[str] = []
    for i in range(TRACES):
        with client.trace(f"trace-{i}") as t:
            trace_ids.append(t.trace_id)
            for j in range(ACTIONS_PER_TRACE):
                if j % 5 == 0:
                    t.log_action(
                        type="llm_call",
                        name="generate",
                        model="claude-sonnet-4",
                        tokens=100 + j,
                    )
                else:
                    t.log_action(
                        type="tool_call",
                        name=f"tool_{j}",
                        input={"i": i, "j": j},
                        output={"ok": True},
                    )
    assert client.flush(timeout=120), "SDK flush timed out"
    client.close()
    return trace_ids


def _verify(api_key: str, trace_ids: list[str]) -> None:
    headers = {"X-Centinela-Key": api_key}

    listing = httpx.get(
        f"{ENDPOINT}/v1/traces", params={"limit": TRACES}, headers=headers, timeout=30
    ).json()
    total = sum(t["event_count"] for t in listing["traces"])
    if len(listing["traces"]) != TRACES:
        raise SystemExit(
            f"FAIL: expected {TRACES} traces, got {len(listing['traces'])}"
        )
    if total != TARGET_EVENTS:
        raise SystemExit(f"FAIL: expected {TARGET_EVENTS} events, got {total}")

    # Retrieve an arbitrary trace in full and check completeness + ordering.
    sample = trace_ids[len(trace_ids) // 2]
    detail = httpx.get(
        f"{ENDPOINT}/v1/traces/{sample}", headers=headers, timeout=30
    ).json()
    if detail["event_count"] != ACTIONS_PER_TRACE + 1:
        raise SystemExit(
            f"FAIL: trace {sample} has {detail['event_count']} events, "
            f"expected {ACTIONS_PER_TRACE + 1}"
        )
    timestamps = [e["timestamp"] for e in detail["events"]]
    if timestamps != sorted(timestamps):
        raise SystemExit("FAIL: trace events are not ordered by timestamp")


def main() -> int:
    print(f"smoke: target endpoint {ENDPOINT}")
    _wait_for_health()
    org_id, api_key = _provision_org_key()
    print(f"smoke: provisioned org {org_id}")

    start = time.monotonic()
    print(f"smoke: emitting {TARGET_EVENTS} events across {TRACES} traces...")
    trace_ids = _emit(api_key)
    print(f"smoke: emit+flush took {time.monotonic() - start:.1f}s; verifying...")

    _verify(api_key, trace_ids)
    print(f"PASS: {TARGET_EVENTS} events ingested and verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
