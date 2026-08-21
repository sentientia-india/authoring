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

DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class DeepSeekError(TextProviderError):
    """Raised when the internal DeepSeek provider call fails safely."""


@dataclass(frozen=True)
class DeepSeekConfig:
    api_key: str | None = None
    model: str = DEFAULT_DEEPSEEK_MODEL
    base_url: str = DEFAULT_DEEPSEEK_BASE_URL
    timeout_seconds: float = 60.0
    max_retries: int = 2
    retry_backoff_seconds: float = 0.5

    @classmethod
    def from_env(cls) -> "DeepSeekConfig":
        return cls(
            api_key=read_secret("DEEPSEEK_API_KEY"),
            model=os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL),
            base_url=os.getenv("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL),
            timeout_seconds=float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "60")),
            max_retries=int(os.getenv("DEEPSEEK_MAX_RETRIES", "2")),
            retry_backoff_seconds=float(os.getenv("DEEPSEEK_RETRY_BACKOFF_SECONDS", "0.5")),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


class DeepSeekTextProvider:
    """TextProvider implementation for DeepSeek's OpenAI-compatible chat completions API."""

    def __init__(
        self,
        config: DeepSeekConfig | None = None,
        transport: Transport = default_transport,
    ) -> None:
        self.config = config or DeepSeekConfig.from_env()
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
            raise DeepSeekError("DeepSeek API key is not configured")

        body = build_chat_completions_body(
            system_prompt,
            user_payload,
            schema_name,
            model or self.config.model,
            response_format_json=False,
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

        # DeepSeek's API does not support response_format={"type": "json_object"}, so (unlike
        # openai.py/generic_openai_compatible.py) there is no point attempting a direct
        # json.loads first -- go straight to the tolerant extract_json_object fallback.
        return extract_chat_completion_content(
            response, DeepSeekError, "DeepSeek", try_json_loads_first=False
        )

    def _send_with_retries(self, request: Request) -> dict[str, Any]:
        return send_with_retries(
            request,
            transport=self._transport,
            max_retries=self.config.max_retries,
            timeout_seconds=self.config.timeout_seconds,
            retry_backoff_seconds=self.config.retry_backoff_seconds,
            error_cls=DeepSeekError,
            error_prefix="DeepSeek",
        )
