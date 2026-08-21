from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.request import Request

from ..security import RequestContext
from .base import (
    ProviderKeySource,
    TextProviderError,
    Transport,
    build_chat_completions_body,
    default_transport,
    extract_chat_completion_content,
    resolve_api_key,
    send_with_retries,
)

# Synthetic identity used only when a caller constructs this provider directly (via
# GenericOpenAICompatibleProvider(...)) without supplying its own RequestContext.
# resolve_api_key() accepts request_context purely so an audit-event write at the call
# site can correlate "who this key resolution was for" -- it performs no I/O with it and
# does not gate the key-resolution outcome on it, so a placeholder is safe here (mirrors
# openrouter.py's _SYSTEM_REQUEST_CONTEXT).
_SYSTEM_REQUEST_CONTEXT = RequestContext(tenant_id="system", user_id="system")


class GenericOpenAICompatibleError(TextProviderError):
    """Raised when the internal generic OpenAI-compatible provider call fails safely."""


@dataclass(frozen=True)
class GenericOpenAICompatibleConfig:
    """Config for an arbitrary OpenAI-chat-completions-compatible endpoint.

    UNLIKE every other adapter's Config in this package (OpenAIConfig, DeepSeekConfig,
    AnthropicConfig, GeminiConfig, OpenRouterConfig), this one deliberately has no
    `from_env()` classmethod and none of its fields default from environment variables.
    Every other adapter names one real vendor, so an env var like OPENAI_API_KEY or
    OPENAI_BASE_URL unambiguously identifies which backend/credential it configures. This
    adapter exists precisely because there ISN'T a single vendor to name -- it is meant to
    point at Ollama (http://localhost:11434/v1), Together.ai, Groq, Fireworks, an Azure
    OpenAI-compatible deployment, or any other backend that speaks the same
    /chat/completions dialect. A "GENERIC_BASE_URL"/"GENERIC_MODEL" env var would be
    actively misleading (which of those unrelated backends would it name at any given
    moment?), so base_url and model are required, explicit constructor arguments instead.

    api_key resolution still goes through resolve_api_key() (see
    GenericOpenAICompatibleProvider below) purely so a caller CAN supply it via the same
    per-request/bring-your-own-key mechanism every other provider uses. That said, there is
    no meaningful env var fallback for this adapter: resolve_api_key() would technically
    consult a secret named "GENERIC_OPENAI_COMPATIBLE_API_KEY" via read_secret(), but no
    such variable is documented, expected, or vendor-specific -- for this adapter treat
    api_key as something the caller supplies explicitly (or omits entirely for endpoints
    like a local Ollama server that don't require one).
    """

    base_url: str
    model: str
    api_key: str | None = None
    timeout_seconds: float = 60.0
    max_retries: int = 2
    retry_backoff_seconds: float = 0.5

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.model)


class GenericOpenAICompatibleProvider:
    """TextProvider for any endpoint that speaks the OpenAI chat-completions dialect.

    Reuses the exact request/response shape of OpenAITextProvider (text_providers/openai.py)
    but templates it against a caller-supplied base_url instead of a hardcoded
    https://api.openai.com/v1. Deliberately adds NO vendor-specific headers (no
    X-Title/HTTP-Referer like the OpenRouter adapter, no Azure-specific api-version query
    param, etc.) so it works generically against Ollama, Together.ai, Groq, Fireworks,
    Azure OpenAI-compatible endpoints, or anything else that implements this dialect.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        model: str,
        *,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
        transport: Transport = default_transport,
        request_context: RequestContext | None = None,
    ) -> None:
        resolved_key, self.key_source = self._resolve_key(api_key, request_context)
        self.config = GenericOpenAICompatibleConfig(
            base_url=base_url,
            model=model,
            api_key=resolved_key,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
        )
        self._transport = transport

    @staticmethod
    def _resolve_key(
        api_key: str | None, request_context: RequestContext | None
    ) -> tuple[str | None, ProviderKeySource]:
        # See GenericOpenAICompatibleConfig's docstring: there is no vendor-specific env var
        # for this adapter, so this call exists only to route the supplied key through the
        # same per-request resolution mechanism (and key_source bookkeeping) as every other
        # provider -- not to pick up a fallback secret from the environment.
        return resolve_api_key(
            "generic_openai_compatible",
            request_context or _SYSTEM_REQUEST_CONTEXT,
            request_key=api_key,
        )

    def generate_json(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        schema_name: str,
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        body = build_chat_completions_body(
            system_prompt,
            user_payload,
            schema_name,
            model or self.config.model,
        )
        headers = {"Content-Type": "application/json"}
        # Authorization is omitted entirely (not even an empty Bearer token) when no key is
        # configured, since plenty of OpenAI-compatible endpoints -- a local Ollama server
        # being the canonical example -- don't require one at all.
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        request = Request(
            f"{self.config.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        response = self._send_with_retries(request)

        # response_format={"type": "json_object"} should guarantee valid JSON, but not every
        # backend that claims this dialect honors it faithfully (this is even more true here
        # than for openai.py, since we cannot assume anything about the server on the other
        # end) -- extract_chat_completion_content falls back to the same tolerant extraction
        # OpenRouter/OpenAI use.
        return extract_chat_completion_content(
            response, GenericOpenAICompatibleError, "Generic OpenAI-compatible"
        )

    def _send_with_retries(self, request: Request) -> dict[str, Any]:
        # Kept intentionally generic rather than tuned to any one vendor's error semantics:
        # a hosted API might return a real HTTP 429/5xx, while a local endpoint like Ollama
        # that isn't running yet will typically fail the TCP connection outright (URLError,
        # e.g. "connection refused") rather than returning any HTTP status at all. Both
        # paths already retry the same way (see send_with_retries in text_providers/base.py)
        # -- 4xx fails fast (it means the request itself is wrong, retrying won't help against
        # any backend), 5xx and connection-level failures retry with backoff, since both
        # plausibly indicate a transient condition (an overloaded hosted API, or a local server
        # that is still starting up).
        return send_with_retries(
            request,
            transport=self._transport,
            max_retries=self.config.max_retries,
            timeout_seconds=self.config.timeout_seconds,
            retry_backoff_seconds=self.config.retry_backoff_seconds,
            error_cls=GenericOpenAICompatibleError,
            error_prefix="Generic OpenAI-compatible",
        )
