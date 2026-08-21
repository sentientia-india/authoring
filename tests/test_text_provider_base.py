from __future__ import annotations

from typing import Any

import pytest

from course_mcp_server.security import RequestContext
from course_mcp_server.text_providers.base import (
    ProviderKeySource,
    TextProvider,
    TextProviderError,
    resolve_api_key,
)

CONTEXT = RequestContext(tenant_id="tenant-1", user_id="user-1")


class FakeTextProvider:
    """Structurally implements the TextProvider Protocol (no explicit inheritance needed)."""

    def generate_json(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        schema_name: str,
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        return {"system_prompt": system_prompt, "payload": user_payload, "schema": schema_name, "model": model}


def test_fake_provider_satisfies_text_provider_protocol_structurally() -> None:
    provider: TextProvider = FakeTextProvider()
    result = provider.generate_json("sys", {"a": 1}, "schema_a", model="gpt-x")
    assert result == {"system_prompt": "sys", "payload": {"a": 1}, "schema": "schema_a", "model": "gpt-x"}


def test_fake_provider_generate_json_defaults_model_to_none() -> None:
    provider: TextProvider = FakeTextProvider()
    result = provider.generate_json("sys", {}, "schema_a")
    assert result["model"] is None


def test_resolve_api_key_prefers_explicit_request_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    value, source = resolve_api_key("openrouter", CONTEXT, request_key="request-key")
    assert (value, source) == ("request-key", "request")


def test_resolve_api_key_falls_back_to_env_when_request_key_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY_FILE", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    value, source = resolve_api_key("openrouter", CONTEXT, request_key=None)
    assert (value, source) == ("env-key", "env")


def test_resolve_api_key_returns_none_env_when_neither_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY_FILE", raising=False)
    value, source = resolve_api_key("openrouter", CONTEXT)
    assert value is None
    assert source == "env"


def test_resolve_api_key_treats_empty_request_key_as_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY_FILE", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    value, source = resolve_api_key("openrouter", CONTEXT, request_key="")
    assert (value, source) == ("env-key", "env")


def test_provider_key_source_literal_values() -> None:
    values: tuple[ProviderKeySource, ProviderKeySource] = ("env", "request")
    assert values == ("env", "request")


def test_text_provider_error_is_an_exception() -> None:
    with pytest.raises(TextProviderError):
        raise TextProviderError("boom")


@pytest.mark.parametrize(
    "provider_id,env_var",
    [
        ("openrouter", "OPENROUTER_API_KEY"),
        ("deepseek", "DEEPSEEK_API_KEY"),
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("gemini", "GEMINI_API_KEY"),
    ],
)
def test_get_text_provider_key_source_is_env_when_no_request_key_given(
    monkeypatch: pytest.MonkeyPatch, provider_id: str, env_var: str
) -> None:
    """All five env-backed providers (not just openrouter) must expose key_source == "env"
    when built via get_text_provider() with no per-request api_key override -- this was the
    P5-2b bug: _env_backed_provider() built deepseek/openai/anthropic/gemini via
    dataclasses.replace() directly, never calling resolve_api_key(), so those four never got a
    key_source attribute at all."""
    from course_mcp_server.text_providers.registry import get_text_provider

    monkeypatch.setenv(env_var, "env-value-for-" + provider_id)
    provider = get_text_provider(provider_id)

    assert hasattr(provider, "key_source")
    assert provider.key_source == "env"


@pytest.mark.parametrize(
    "provider_id,env_var",
    [
        ("openrouter", "OPENROUTER_API_KEY"),
        ("deepseek", "DEEPSEEK_API_KEY"),
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("gemini", "GEMINI_API_KEY"),
    ],
)
def test_get_text_provider_key_source_is_request_when_request_key_given(
    monkeypatch: pytest.MonkeyPatch, provider_id: str, env_var: str
) -> None:
    """A per-request api_key override must win over any env-configured key, and must be
    reflected as key_source == "request" -- for all five env-backed providers, not just
    openrouter."""
    from course_mcp_server.text_providers.registry import get_text_provider

    monkeypatch.setenv(env_var, "env-value-for-" + provider_id)
    provider = get_text_provider(provider_id, api_key="request-value-for-" + provider_id)

    assert provider.key_source == "request"
    assert provider.config.api_key == "request-value-for-" + provider_id


def test_get_text_provider_openai_compatible_key_source_reflects_request() -> None:
    """The sixth provider (openai_compatible / GenericOpenAICompatibleProvider) already set
    key_source correctly before this fix -- covered here so all six providers get_text_provider()
    can build are proven to expose key_source in one place."""
    from course_mcp_server.text_providers.registry import get_text_provider

    provider = get_text_provider(
        "openai_compatible",
        api_key="request-value-for-openai_compatible",
        base_url="https://example-vendor.test/v1",
        model="some-custom-model",
    )

    assert provider.key_source == "request"
