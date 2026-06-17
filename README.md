# centinela

**Flight recorder & firewall for AI agents — Caja negra y firewall para agentes de IA**

[![CI](https://github.com/centinela-ai/centinela-python/actions/workflows/ci.yml/badge.svg)](https://github.com/centinela-ai/centinela-python/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/centinela.svg)](https://pypi.org/project/centinela/)
[![Python](https://img.shields.io/pypi/pyversions/centinela.svg)](https://pypi.org/project/centinela/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Centinela records what your AI agent actually did — every tool call, every LLM call, every error — as **auditable evidence you can replay**. The Python SDK is open source (MIT); a hosted backend visualizes the traces and turns them into a compliance layer. Real-time blocking is on the roadmap.

> Centinela registra lo que tu agente de IA realmente hizo — cada llamada a herramienta, cada llamada al LLM, cada error — como evidencia auditable que puedes reproducir.

```bash
pip install centinela
```

One runtime dependency (`httpx`). Python 3.9+.

---

## Quickstart

```python
from centinela import Centinela

c = Centinela(api_key="ctl_...", project="mi-agente")

# Option A — automatic wrapper (LangChain, OpenAI SDK, Anthropic SDK)
agent = c.wrap(agent)

# Option B — manual instrumentation (works with any framework)
with c.trace("procesar_pedido") as t:
    t.log_action(type="tool_call", name="enviar_email", input={"to": "cliente@example.com"})
    t.log_action(type="llm_call", model="claude-sonnet-4", tokens=1234)
```

**No backend yet?** Set `CENTINELA_ENDPOINT=stdout` and events print to your console, so you can see exactly what gets recorded before you wire up anything.

---

## Supported frameworks

| Framework      | `c.wrap(...)` | How                                                   |
| -------------- | :-----------: | ----------------------------------------------------- |
| OpenAI SDK     | ✅            | Patches `chat.completions.create`                     |
| Anthropic SDK  | ✅            | Patches `messages.create`                             |
| LangChain      | ✅            | Attaches a `BaseCallbackHandler`                      |
| Any other      | Manual        | `c.trace(...)` / `t.log_action(...)` — framework-agnostic |

Unrecognized objects passed to `wrap()` raise a clear error pointing here, to manual instrumentation.

---

## Manual instrumentation

`wrap()` is convenience; the `trace` API works everywhere and **is the contract**.

```python
with c.trace("nightly_report") as t:
    rows = run_query()
    t.log_action(type="tool_call", name="run_query", input={"sql": "..."}, output={"rows": len(rows)})
    t.log_action(type="llm_call", name="summarize", model="claude-sonnet-4", tokens=842)
```

Every action becomes an event with this shape (the backend's contract):

```json
{
  "trace_id": "uuid", "span_id": "uuid", "parent_span_id": null,
  "project": "str", "timestamp": "ISO8601",
  "type": "tool_call | llm_call | agent_start | agent_end | error",
  "name": "str", "input": {}, "output": {}, "metadata": {},
  "duration_ms": 0, "status": "ok | error"
}
```

This 12-key shape is stable. Compliance signals (below) never add top-level keys — they travel inside a reserved `metadata["_centinela"]` sub-namespace, so instrumenting them is backward-compatible and an un-instrumented call stays byte-for-byte identical.

---

## Configuration

| Setting    | Argument    | Environment variable  | Notes                                                        |
| ---------- | ----------- | --------------------- | ------------------------------------------------------------ |
| API key    | `api_key=`  | `CENTINELA_API_KEY`   | Sent as the `X-Centinela-Key` header.                        |
| Endpoint   | `endpoint=` | `CENTINELA_ENDPOINT`  | Defaults to `https://api.getcentinela.dev`. `stdout` prints events locally; set your own URL to self-host. |
| Kill switch| `disabled=` | `CENTINELA_DISABLED`  | `true` makes the SDK a no-op.                                |
| Redaction  | `redact=`   | —                     | `True` strips all payloads; a list redacts named fields. See below. |

---

## Compliance signals

These are **optional**. They let the hosted backend evaluate your agent against a control library (see *Compliance layer*). Each is `Optional` and defaults to `None` — and **`None` emits no signal at all**: the backend reads an absent signal as *not applicable*, never as a silent pass. You only ever assert what you actually measured.

```python
# Did a human approve a risky action before it ran? (pre-execution gate)
t.log_action(type="tool_call", name="wire_transfer",
             blocked=False, human_review="approved")   # → CTL-003, CTL-007

# Was the end user told they're talking to an AI? (set once per trace)
with c.trace("chat_session", ai_disclosed=True) as t:  # → CTL-009
    ...
```

| Signal                              | Values                              | Maps to |
| ----------------------------------- | ----------------------------------- | ------- |
| `blocked`                           | `True` / `False`                    | CTL-003 — risk-action gating |
| `human_review`                      | `"approved"` / `"reviewed"` / `"none"` | CTL-003 + CTL-007 — human oversight |
| `ai_disclosed` (on `trace`)         | `True` / `False`                    | CTL-009 — AI disclosure |

`"approved"` means a human signed off **before** the action ran (it opens the gate). `"reviewed"` means after the fact (it satisfies oversight but does **not** open the gate). Be precise: the SDK records what you tell it, and the report says exactly that and nothing more.

---

## Redaction

```python
# Strip everything: action payloads never leave your process.
c = Centinela(api_key="ctl_...", project="mi-agente", redact=True)

# Or redact named fields only — still ships structure, timing and status,
# and records that the fields were present and masked. (→ CTL-004, PII)
c = Centinela(api_key="ctl_...", project="mi-agente",
              redact=["email", "ssn", "card_number"])
```

With `redact=True`, `input`/`output` never leave your process — only structure, timing, names, and status are shipped. Field-level mode masks the named keys (at any depth) before the event leaves, and emits an honest signal: *these sensitive fields were present, and all were masked*. It never claims "no leak was detected."

---

## Compliance layer (the plus)

Observability is the hook; this is the moat. The hosted backend takes your real traces and evaluates each **agent** against a control library aligned with the frameworks your enterprise customers are starting to ask about — **ISO/IEC 42001**, **NIST AI RMF**, and the **EU AI Act** — then issues a bilingual evidence report and a **Centinela Verified** badge you can show a client.

Honest by design:

- **Evidence, not certification.** Centinela documents what your agent did against each control. It does not certify your organization.
- **8 of 10 controls are measurable today** from SDK signals. Controls that need signals you haven't sent are reported as *not applicable* — never as a pass. Semantic checks (e.g. hallucination) require an evaluation engine that's still on the roadmap.
- **The seal can't be faked.** A blocking control failing → `suspended`. Any other failure → `provisional`. All applicable controls passing → `verified`.

If you build agents for clients, this is something to **sell**: ship the compliance evidence with the product instead of scrambling for it at audit time.

---

## Design guarantees

- **Never breaks your agent.** Event delivery is asynchronous and **fail-open**: events are queued in memory and flushed from a background thread every 2s (or every 20 events). If the backend is slow, erroring, or unreachable, your agent never blocks, slows, or crashes — failures are logged and dropped.
- **Tiny footprint.** One dependency (`httpx`), Python 3.9+.

---

## Why

Agents in production fail expensively — a wrong tool call, a hallucinated argument, a silent retry loop — and by the time you notice, the context is gone. Centinela gives you auditable evidence from day one: a replayable record of every action, so you can prove what happened, debug it, and (soon) block it before it does damage.

> Los agentes en producción fallan caro, y cuando te enteras el contexto ya desapareció. Centinela te da evidencia auditable desde el día uno.

---

## License

MIT © centinela-ai
