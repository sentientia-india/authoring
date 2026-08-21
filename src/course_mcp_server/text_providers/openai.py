from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.request import Request

from ..security import read_secret
from .base import (
    Transport,
    TextProviderError,
    build_chat_completions_body,
    default_transport,
    extract_chat_completion_content,
    send_with_retries,
)

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


class OpenAIError(TextProviderError):
    """Raised when the internal OpenAI provider call fails safely."""


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str | None = None
    model: str = DEFAULT_OPENAI_MODEL
    base_url: str = DEFAULT_OPENAI_BASE_URL
    timeout_seconds: float = 60.0
    max_retries: int = 2
    retry_backoff_seconds: float = 0.5

    @classmethod
    def from_env(cls) -> "OpenAIConfig":
        return cls(
            api_key=read_secret("OPENAI_API_KEY"),
            model=os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
            base_url=os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL),
            timeout_seconds=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "60")),
            max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "2")),
            retry_backoff_seconds=float(os.getenv("OPENAI_RETRY_BACKOFF_SECONDS", "0.5")),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


class OpenAITextProvider:
    def __init__(
        self,
        config: OpenAIConfig | None = None,
        transport: Transport = default_transport,
    ) -> None:
        self.config = config or OpenAIConfig.from_env()
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
            raise OpenAIError("OpenAI API key is not configured")

        body = build_chat_completions_body(
            system_prompt,
            user_payload,
            schema_name,
            model or self.config.model,
        )
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        request = Request(
            f"{self.config.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        response = self._send_with_retries(request)

        # response_format={"type": "json_object"} should guarantee valid JSON, but not every
        # model/deployment honors it faithfully -- extract_chat_completion_content runs the
        # content through the same tolerant extraction OpenRouter uses as a defensive fallback
        # (handles stray markdown fences etc).
        return extract_chat_completion_content(response, OpenAIError, "OpenAI")

    def _send_with_retries(self, request: Request) -> dict[str, Any]:
        return send_with_retries(
            request,
            transport=self._transport,
            max_retries=self.config.max_retries,
            timeout_seconds=self.config.timeout_seconds,
            retry_backoff_seconds=self.config.retry_backoff_seconds,
            error_cls=OpenAIError,
            error_prefix="OpenAI",
        )
