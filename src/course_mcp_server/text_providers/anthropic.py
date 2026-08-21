from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.request import Request

from .openrouter import OpenRouterError, extract_json_object
from ..security import read_secret
from .base import Transport, TextProviderError, default_transport, send_with_retries

# Anthropic's own current-model recommendation as of this cycle -- see the claude-api skill's
# model table. Do not append a date suffix; this is a complete model id string.
DEFAULT_ANTHROPIC_MODEL = "claude-opus-5"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"
ANTHROPIC_API_VERSION = "2023-06-01"
DEFAULT_ANTHROPIC_MAX_TOKENS = 4096


class AnthropicError(TextProviderError):
    """Raised when the internal Anthropic provider call fails safely."""


@dataclass(frozen=True)
class AnthropicConfig:
    api_key: str | None = None
    model: str = DEFAULT_ANTHROPIC_MODEL
    base_url: str = DEFAULT_ANTHROPIC_BASE_URL
    timeout_seconds: float = 60.0
    max_retries: int = 2
    retry_backoff_seconds: float = 0.5
    max_tokens: int = DEFAULT_ANTHROPIC_MAX_TOKENS

    @classmethod
    def from_env(cls) -> "AnthropicConfig":
        return cls(
            api_key=read_secret("ANTHROPIC_API_KEY"),
            model=os.getenv("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL),
            base_url=os.getenv("ANTHROPIC_BASE_URL", DEFAULT_ANTHROPIC_BASE_URL),
            timeout_seconds=float(os.getenv("ANTHROPIC_TIMEOUT_SECONDS", "60")),
            max_retries=int(os.getenv("ANTHROPIC_MAX_RETRIES", "2")),
            retry_backoff_seconds=float(os.getenv("ANTHROPIC_RETRY_BACKOFF_SECONDS", "0.5")),
            max_tokens=int(os.getenv("ANTHROPIC_MAX_TOKENS", str(DEFAULT_ANTHROPIC_MAX_TOKENS))),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


class AnthropicTextProvider:
    """TextProvider backed by Anthropic's Messages API.

    Structurally different from the OpenAI-style chat-completions shape every other adapter in
    this package follows: auth is an `x-api-key` header (not `Authorization: Bearer`), `system`
    is a top-level request field (not a message with role="system"), and the response carries a
    list of typed content blocks (`content: [{"type": "text", "text": ...}]`) rather than
    `choices[0].message.content`.
    """

    def __init__(
        self,
        config: AnthropicConfig | None = None,
        transport: Transport = default_transport,
    ) -> None:
        self.config = config or AnthropicConfig.from_env()
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
            raise AnthropicError("Anthropic API key is not configured")

        body = {
            "model": model or self.config.model,
            "max_tokens": self.config.max_tokens,
            # `system` is a top-level request field on the Messages API -- it is NOT a message
            # with role="system" the way OpenAI-compatible chat-completions APIs shape it.
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(
                        {"schema": schema_name, "payload": user_payload},
                        ensure_ascii=True,
                    ),
                },
            ],
        }
        headers = {
            # Anthropic auth is `x-api-key`, NOT `Authorization: Bearer`.
            "x-api-key": self.config.api_key,
            "anthropic-version": ANTHROPIC_API_VERSION,
            "Content-Type": "application/json",
        }

        request = Request(
            f"{self.config.base_url.rstrip('/')}/messages",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        response = self._send_with_retries(request)

        content_blocks = response.get("content")
        if not isinstance(content_blocks, list):
            raise AnthropicError("Anthropic response shape was invalid")

        text_parts = [
            block.get("text")
            for block in content_blocks
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
        ]
        if not text_parts:
            raise AnthropicError("Anthropic response did not contain a text content block")
        content = "".join(text_parts)

        # Claude models are not guaranteed to emit JSON-only output for an arbitrary prompt --
        # run the extracted text through the same tolerant extraction the other adapters use.
        try:
            return extract_json_object(content)
        except OpenRouterError as exc:
            raise AnthropicError(str(exc)) from exc

    def _send_with_retries(self, request: Request) -> dict[str, Any]:
        return send_with_retries(
            request,
            transport=self._transport,
            max_retries=self.config.max_retries,
            timeout_seconds=self.config.timeout_seconds,
            retry_backoff_seconds=self.config.retry_backoff_seconds,
            error_cls=AnthropicError,
            error_prefix="Anthropic",
        )
