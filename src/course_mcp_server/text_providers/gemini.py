from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote
from urllib.request import Request

from .openrouter import OpenRouterError, extract_json_object
from ..security import read_secret
from .base import Transport, TextProviderError, default_transport, send_with_retries

# A real, current Gemini model id (Gemini 2.5 generation). Not a snapshot/date-suffixed variant.
DEFAULT_GEMINI_MODEL = "gemini-2.5-pro"
DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiError(TextProviderError):
    """Raised when the internal Gemini provider call fails safely."""


@dataclass(frozen=True)
class GeminiConfig:
    api_key: str | None = None
    model: str = DEFAULT_GEMINI_MODEL
    base_url: str = DEFAULT_GEMINI_BASE_URL
    timeout_seconds: float = 60.0
    max_retries: int = 2
    retry_backoff_seconds: float = 0.5

    @classmethod
    def from_env(cls) -> "GeminiConfig":
        return cls(
            api_key=read_secret("GEMINI_API_KEY"),
            model=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
            base_url=os.getenv("GEMINI_BASE_URL", DEFAULT_GEMINI_BASE_URL),
            timeout_seconds=float(os.getenv("GEMINI_TIMEOUT_SECONDS", "60")),
            max_retries=int(os.getenv("GEMINI_MAX_RETRIES", "2")),
            retry_backoff_seconds=float(os.getenv("GEMINI_RETRY_BACKOFF_SECONDS", "0.5")),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


class GeminiTextProvider:
    """TextProvider backed by Google's Gemini `generateContent` endpoint.

    Another shape distinct from the OpenAI-style chat-completions adapters in this package:
    the request body nests text under `contents[].parts[].text` (with an optional top-level
    `systemInstruction`), and the response nests text under
    `candidates[].content.parts[].text`. The genuinely security-relevant divergence is that the
    API key rides in the URL QUERY STRING (`?key=...`), not in a header -- see the
    `_build_url`/`_redacted_url_for_errors` split below, and `security.SECRET_PATTERNS`, which
    was extended in this change to redact a `key=<value>` query-string shape so this key can
    never leak into a log/audit string unredacted.
    """

    def __init__(
        self,
        config: GeminiConfig | None = None,
        transport: Transport = default_transport,
    ) -> None:
        self.config = config or GeminiConfig.from_env()
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
            raise GeminiError("Gemini API key is not configured")

        resolved_model = model or self.config.model
        body: dict[str, Any] = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": json.dumps(
                                {"schema": schema_name, "payload": user_payload},
                                ensure_ascii=True,
                            )
                        }
                    ]
                }
            ],
        }
        # v1beta supports a top-level systemInstruction field, structured the same as a content
        # entry (parts[].text) but without a role -- distinct from contents[], which holds the
        # actual conversation turns.
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        headers = {"Content-Type": "application/json"}
        url = self._build_url(resolved_model)

        request = Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        response = self._send_with_retries(request)

        try:
            candidates = response["candidates"]
            first_candidate = candidates[0]
            parts = first_candidate["content"]["parts"]
        except (KeyError, IndexError, TypeError) as exc:
            raise GeminiError("Gemini response shape was invalid") from exc

        text_parts = [
            part.get("text") for part in parts if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        if not text_parts:
            raise GeminiError("Gemini response did not contain a text part")
        content = "".join(text_parts)

        try:
            return extract_json_object(content)
        except OpenRouterError as exc:
            raise GeminiError(str(exc)) from exc

    def _build_url(self, model: str) -> str:
        # The API key is a URL query parameter for this API, never a header -- this is the one
        # place the raw key value is constructed. Keep it out of any exception message or log
        # line: error paths below only ever reference the model name, never this URL.
        base = self.config.base_url.rstrip("/")
        return f"{base}/models/{quote(model)}:generateContent?key={quote(self.config.api_key or '')}"

    def _send_with_retries(self, request: Request) -> dict[str, Any]:
        # send_with_retries() (text_providers/base.py) deliberately never references
        # exc.filename/exc.url when building its message -- which matters here specifically,
        # since this adapter's request URL carries the ?key=... query string (see class
        # docstring / _build_url above) and must never leak into an exception message or log.
        return send_with_retries(
            request,
            transport=self._transport,
            max_retries=self.config.max_retries,
            timeout_seconds=self.config.timeout_seconds,
            retry_backoff_seconds=self.config.retry_backoff_seconds,
            error_cls=GeminiError,
            error_prefix="Gemini",
        )
