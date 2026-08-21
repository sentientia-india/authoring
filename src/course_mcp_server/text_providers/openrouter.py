from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from typing import Any
from urllib.request import Request

from ..security import RequestContext, read_secret
from .base import ProviderKeySource, Transport, default_transport, resolve_api_key, send_with_retries

DEFAULT_OPENROUTER_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Synthetic identity used only when a caller injects an api_key directly (via
# OpenRouterTextProvider(api_key=...)) without supplying its own RequestContext.
# resolve_api_key() accepts request_context purely so an audit-event write at the call
# site can correlate "who this key resolution was for" -- it performs no I/O with it and
# does not gate the key-resolution outcome on it, so a placeholder is safe here.
_SYSTEM_REQUEST_CONTEXT = RequestContext(tenant_id="system", user_id="system")


class OpenRouterError(RuntimeError):
    """Raised when the internal OpenRouter provider call fails safely."""


@dataclass(frozen=True)
class OpenRouterConfig:
    api_key: str | None = None
    model: str = DEFAULT_OPENROUTER_MODEL
    base_url: str = DEFAULT_OPENROUTER_BASE_URL
    timeout_seconds: float = 60.0
    max_retries: int = 2
    retry_backoff_seconds: float = 0.5
    site_url: str | None = None
    app_title: str = "Samrat Course MCP"

    @classmethod
    def from_env(cls) -> "OpenRouterConfig":
        return cls(
            api_key=read_secret("OPENROUTER_API_KEY"),
            model=os.getenv("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL),
            base_url=os.getenv("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL),
            timeout_seconds=float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "60")),
            max_retries=int(os.getenv("OPENROUTER_MAX_RETRIES", "2")),
            retry_backoff_seconds=float(os.getenv("OPENROUTER_RETRY_BACKOFF_SECONDS", "0.5")),
            site_url=os.getenv("OPENROUTER_SITE_URL") or None,
            app_title=os.getenv("OPENROUTER_APP_TITLE", "Samrat Course MCP"),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


def extract_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise OpenRouterError("OpenRouter response did not contain a JSON object")
    try:
        parsed = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as exc:
        raise OpenRouterError("OpenRouter response contained invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise OpenRouterError("OpenRouter response JSON was not an object")
    return parsed


class OpenRouterClient:
    """Low-level OpenRouter chat-completions client (retry/backoff + JSON extraction).

    Kept exactly as it behaved when this lived in llm_openrouter.py -- every pre-existing
    caller (course_generator.py, apps/scorm_editor/server.py, smoke.py, and the test suite)
    imports this class by name and constructs/uses it exactly as before. OpenRouterTextProvider
    below is a thin TextProvider-protocol adapter built on top of this, not a replacement.
    """

    def __init__(
        self,
        config: OpenRouterConfig | None = None,
        transport: Transport = default_transport,
    ) -> None:
        self.config = config or OpenRouterConfig.from_env()
        self._transport = transport

    def generate_json(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        schema_name: str,
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        if not self.config.api_key:
            raise OpenRouterError("OpenRouter API key is not configured")

        effective_model = model or self.config.model
        body = {
            "model": effective_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"schema": schema_name, "payload": user_payload},
                        ensure_ascii=True,
                    ),
                },
            ],
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "X-OpenRouter-Title": self.config.app_title,
        }
        if self.config.site_url:
            headers["HTTP-Referer"] = self.config.site_url

        request = Request(
            f"{self.config.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        response = self._send_with_retries(request)

        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenRouterError("OpenRouter response shape was invalid") from exc
        if not isinstance(content, str):
            raise OpenRouterError("OpenRouter response content was invalid")
        return extract_json_object(content)

    def _send_with_retries(self, request: Request) -> dict[str, Any]:
        return send_with_retries(
            request,
            transport=self._transport,
            max_retries=self.config.max_retries,
            timeout_seconds=self.config.timeout_seconds,
            retry_backoff_seconds=self.config.retry_backoff_seconds,
            error_cls=OpenRouterError,
            error_prefix="OpenRouter",
        )


class OpenRouterTextProvider:
    """TextProvider-protocol adapter over OpenRouterClient (see text_providers/base.py).

    Delegates all retry/transport/parsing behavior to OpenRouterClient verbatim -- this
    class only adds the TextProvider-shaped constructor/call surface: an explicit
    `api_key` constructor parameter (resolved via resolve_api_key() so an injected key
    never falls back to reading OPENROUTER_API_KEY from the environment) alongside the
    existing `from_env()`-based `OpenRouterConfig` classmethod.
    """

    def __init__(
        self,
        config: OpenRouterConfig | None = None,
        transport: Transport = default_transport,
        *,
        api_key: str | None = None,
        request_context: RequestContext | None = None,
    ) -> None:
        base_config = config if config is not None else OpenRouterConfig.from_env()
        self.key_source: ProviderKeySource
        if api_key is not None:
            resolved_key, self.key_source = resolve_api_key(
                "openrouter",
                request_context or _SYSTEM_REQUEST_CONTEXT,
                request_key=api_key,
            )
            base_config = replace(base_config, api_key=resolved_key)
        else:
            self.key_source = "env"
        self._client = OpenRouterClient(base_config, transport=transport)

    @classmethod
    def from_env(cls) -> "OpenRouterTextProvider":
        return cls(OpenRouterConfig.from_env())

    @property
    def config(self) -> OpenRouterConfig:
        return self._client.config

    def generate_json(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        schema_name: str,
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        return self._client.generate_json(system_prompt, user_payload, schema_name, model=model)
