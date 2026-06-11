# centinela

**Flight recorder & firewall for AI agents** — _Caja negra y firewall para agentes de IA_

[![CI](https://github.com/centinela-ai/centinela-python/actions/workflows/ci.yml/badge.svg)](https://github.com/centinela-ai/centinela-python/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/centinela.svg)](https://pypi.org/project/centinela/)
[![Python](https://img.shields.io/pypi/pyversions/centinela.svg)](https://pypi.org/project/centinela/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Centinela records what your AI agent actually did — every tool call, every LLM call, every error — as auditable evidence you can replay. The Python SDK is open source (MIT); a hosted backend visualizes the traces, and real-time blocking is on the roadmap.

> _Centinela registra lo que tu agente de IA realmente hizo — cada llamada a herramienta, cada llamada al LLM, cada error — como evidencia auditable que puedes reproducir._

<!-- TODO: dashboard GIF showing a single trace expanded into its action tree -->
![Centinela trace view](docs/trace-demo.gif)

## Install

```bash
pip install centinela
```

Only one runtime dependency (`httpx`). Python 3.9+.

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

No backend yet? Set `CENTINELA_ENDPOINT=stdout` and events print to your console so you can see exactly what gets recorded.

## Supported frameworks

| Framework        | `c.wrap(...)` | How                                                        |
| ---------------- | :-----------: | ---------------------------------------------------------- |
| OpenAI SDK       |       ✅       | Patches `chat.completions.create`                          |
| Anthropic SDK    |       ✅       | Patches `messages.create`                                  |
| LangChain        |       ✅       | Attaches a `BaseCallbackHandler`                           |
| Any other        |   Manual      | `c.trace(...)` / `t.log_action(...)` — framework-agnostic  |

Unrecognized objects passed to `wrap()` raise a clear error pointing here, to manual instrumentation.

## Manual instrumentation

`wrap()` is convenience; the trace API works everywhere and is the contract.

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

## Configuration

| Setting     | Argument            | Environment variable  | Notes                                              |
| ----------- | ------------------- | --------------------- | -------------------------------------------------- |
| API key     | `api_key=`          | `CENTINELA_API_KEY`   | Sent as the `X-Centinela-Key` header.              |
| Endpoint    | `endpoint=`         | `CENTINELA_ENDPOINT`  | For self-hosting. `stdout` prints events locally.  |
| Kill switch | `disabled=`         | `CENTINELA_DISABLED`  | `true` makes the SDK a no-op.                       |
| Redaction   | `redact=True`       | —                     | Strips `input`/`output` before events leave the process. |

### Redaction for compliance

```python
c = Centinela(api_key="ctl_...", project="mi-agente", redact=True)
```

With `redact=True`, action payloads (`input`/`output`) never leave your process — only the structure, timing, names, and status are shipped.

## Design guarantees

- **Never breaks your agent.** Event delivery is asynchronous and **fail-open**: events are queued in memory and flushed from a background thread every 2s (or every 20 events). If the backend is slow, erroring, or unreachable, your agent never blocks, slows, or crashes — failures are logged and dropped.
- **Tiny footprint.** One dependency (`httpx`), Python 3.9+.

## Why

Agents in production fail expensively — a wrong tool call, a hallucinated argument, a silent retry loop — and by the time you notice, the context is gone. Centinela gives you auditable evidence from day one: a replayable record of every action, so you can prove what happened, debug it, and (soon) block it before it does damage.

> _Los agentes en producción fallan caro, y cuando te enteras el contexto ya desapareció. Centinela te da evidencia auditable desde el día uno._

## License

MIT © centinela-ai
