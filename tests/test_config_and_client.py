from __future__ import annotations

from centinela import Centinela
from centinela.config import DEFAULT_ENDPOINT, DEV_ENDPOINT, resolve_config


def test_explicit_args_take_precedence(monkeypatch):
    monkeypatch.setenv("CENTINELA_API_KEY", "env-key")
    monkeypatch.setenv("CENTINELA_ENDPOINT", "https://env.example")
    cfg = resolve_config(api_key="explicit", endpoint="https://explicit.example")
    assert cfg.api_key == "explicit"
    assert cfg.endpoint == "https://explicit.example"


def test_env_fallback_and_defaults(monkeypatch):
    monkeypatch.delenv("CENTINELA_API_KEY", raising=False)
    monkeypatch.delenv("CENTINELA_ENDPOINT", raising=False)
    monkeypatch.delenv("CENTINELA_ENV", raising=False)
    monkeypatch.setenv("CENTINELA_API_KEY", "env-key")
    cfg = resolve_config()
    assert cfg.api_key == "env-key"
    assert cfg.endpoint == DEFAULT_ENDPOINT


def test_dev_env_defaults_to_localhost(monkeypatch):
    monkeypatch.delenv("CENTINELA_ENDPOINT", raising=False)
    monkeypatch.setenv("CENTINELA_ENV", "dev")
    cfg = resolve_config()
    assert cfg.endpoint == DEV_ENDPOINT


def test_explicit_endpoint_overrides_dev_env(monkeypatch):
    monkeypatch.setenv("CENTINELA_ENV", "dev")
    cfg = resolve_config(endpoint="https://explicit.example")
    assert cfg.endpoint == "https://explicit.example"


def test_endpoint_trailing_slash_stripped():
    cfg = resolve_config(endpoint="https://host.example/")
    assert cfg.endpoint == "https://host.example"


def test_disabled_flag_from_env(monkeypatch):
    monkeypatch.setenv("CENTINELA_DISABLED", "true")
    cfg = resolve_config()
    assert cfg.disabled is True


def test_disabled_client_is_noop(monkeypatch):
    client = Centinela(project="p", disabled=True)
    assert client._transport is None
    # Should not raise and should produce nothing.
    with client.trace("run") as t:
        t.log_action(type="tool_call", name="x")
    assert client.flush() is True
    client.close()


def test_redact_nulls_payloads(monkeypatch):
    client = Centinela(project="p", endpoint="stdout", redact=True)
    client._transport.close()

    captured = []
    client._transport = type(
        "T", (), {"enqueue": lambda self, e: captured.append(e),
                  "flush": lambda self, t=5.0: True,
                  "close": lambda self, t=5.0: None}
    )()

    with client.trace("run") as t:
        t.log_action(type="tool_call", name="x", input={"secret": 1}, output={"r": 2})

    action = captured[0]
    assert action["input"] is None
    assert action["output"] is None
    # name/type are not redacted
    assert action["name"] == "x"
