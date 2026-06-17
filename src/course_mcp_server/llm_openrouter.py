from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .security import read_secret

DEFAULT_OPENROUTER_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


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


Transport = Callable[[Request, float], dict[str, Any]]


def _default_transport(request: Request, timeout: float) -> dict[str, Any]:
    with urlopen(request, timeout=timeout) as response:  # nosec B310 - fixed HTTPS provider URL
        return json.loads(response.read().decode("utf-8"))


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
    def __init__(
        self,
        config: OpenRouterConfig | None = None,
        transport: Transport = _default_transport,
    ) -> None:
        self.config = config or OpenRouterConfig.from_env()
        self._transport = transport

    def generate_json(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        schema_name: str,
    ) -> dict[str, Any]:
        if not self.config.api_key:
            raise OpenRouterError("OpenRouter API key is not configured")

        body = {
            "model": self.config.model,
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
        attempts = self.config.max_retries + 1
        for attempt in range(attempts):
            try:
                return self._transport(request, self.config.timeout_seconds)
            except HTTPError as exc:
                if exc.code < 500 or attempt == attempts - 1:
                    raise OpenRouterError(f"OpenRouter request failed with status {exc.code}") from exc
            except URLError as exc:
                if attempt == attempts - 1:
                    raise OpenRouterError("OpenRouter request failed") from exc
            if self.config.retry_backoff_seconds > 0:
                time.sleep(self.config.retry_backoff_seconds * (attempt + 1))
        raise OpenRouterError("OpenRouter request failed")
