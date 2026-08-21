from __future__ import annotations

import json
import time
from typing import Any, Callable, Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..security import RequestContext, read_secret

# Mirrors video_providers/base.py's provider-contract shape (Protocol + a base error type),
# but the concurrency model is deliberately DIFFERENT, not just a rename:
#
#   VideoProvider is submit()/poll()/fetch() because a real video/avatar job (HeyGen, Veo)
#   can take minutes and this codebase has no async job/worker infrastructure -- the caller
#   has to be able to check back later without blocking a request for that long.
#
#   TextProvider.generate_json() is a single SYNCHRONOUS call. Even a slow LLM's chat-completion
#   endpoint is one blocking HTTP round trip (seconds, not minutes) with no server-side job to
#   poll -- see llm_openrouter.py's OpenRouterClient.generate_json(), which this Protocol is
#   modeled on. There is no "processing" status and no separate fetch step: the response is the
#   result, or the call raises. Do not add poll()/fetch() here just for symmetry with
#   VideoProvider -- that would misrepresent how every text-generation backend in this codebase
#   actually behaves.
TextProviderJson = dict[str, Any]


class TextProviderError(Exception):
    """Raised when a text-generation provider call fails safely (not configured, HTTP failure, malformed response, etc.)."""


# Where a given call's API key came from, for audit logging: "env" means it was resolved from
# server-side configuration (read_secret), "request" means the caller supplied it explicitly
# for that one call (e.g. a per-tenant/bring-your-own-key request).
ProviderKeySource = Literal["env", "request"]


class TextProvider(Protocol):
    """Common shape for any JSON-generating text/LLM provider (see module docstring)."""

    def generate_json(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        schema_name: str,
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Generate and return a JSON object for the given prompt/payload. Blocks until done or raises."""
        ...


def resolve_api_key(
    provider_id: str,
    request_context: RequestContext,
    *,
    request_key: str | None = None,
) -> tuple[str | None, ProviderKeySource]:
    """Resolve the API key to use for one call to `provider_id`.

    An explicit `request_key` (e.g. a per-tenant/bring-your-own-key supplied for that single
    request) always wins. Otherwise falls back to the server-side secret named
    f"{provider_id.upper()}_API_KEY" via security.read_secret, which itself supports the
    "_FILE" convention -- this preserves today's env-var-only behavior unchanged for every
    caller that never passes `request_key`. Never raises for a missing key -- callers decide
    whether a missing key is fatal.

    `request_context` identifies who this resolution is for (tenant_id/user_id/request_id) so a
    caller can attach it to its own audit-event write alongside the returned ProviderKeySource --
    e.g. "tenant X's call to provider Y used a request-supplied key, not the shared server key".
    This function itself performs no I/O beyond read_secret and writes no audit event, matching
    video_providers/base.py's dependency-free style; `request_context` is accepted here (rather
    than left for the caller to thread through separately) purely so the source-of-key decision
    and the identity it was made for travel together at the call site.
    """
    if request_key:
        return request_key, "request"
    return read_secret(f"{provider_id.upper()}_API_KEY"), "env"


# Shared HTTP transport + retry-loop implementation.
#
# Every adapter in this package (openrouter.py, deepseek.py, openai.py, anthropic.py,
# gemini.py, generic_openai_compatible.py) previously copy-pasted an identical ~3-line
# urlopen+json.loads transport function and an identical ~14-line retry-loop method
# (retry count derived from max_retries, 5xx-retry/4xx-fail-fast branching via HTTPError.code,
# `backoff * (attempt + 1)` sleep formula, URLError treated as always-retryable-until-exhausted).
# This is that logic, extracted once. Adapters differ only in: which error class to raise, what
# provider-name prefix to put in the message, and their own (currently identical, but
# independently configurable) retry-policy values -- all supplied as parameters so each
# adapter's exact current behavior is preserved unchanged.
Transport = Callable[[Request, float], dict[str, Any]]


def default_transport(request: Request, timeout: float) -> dict[str, Any]:
    with urlopen(request, timeout=timeout) as response:  # nosec B310 - fixed HTTPS provider URL
        return json.loads(response.read().decode("utf-8"))


def send_with_retries(
    request: Request,
    *,
    transport: Transport,
    max_retries: int,
    timeout_seconds: float,
    retry_backoff_seconds: float,
    error_cls: type[Exception],
    error_prefix: str,
) -> dict[str, Any]:
    """Send `request` via `transport`, retrying 5xx/connection failures with backoff.

    4xx HTTPErrors fail fast (retrying a malformed/unauthorized request cannot help).
    5xx HTTPErrors and URLErrors (e.g. connection refused, DNS failure, timeout) retry up to
    `max_retries` additional times, sleeping `retry_backoff_seconds * (attempt + 1)` between
    attempts. Raises `error_cls(f"{error_prefix} request failed...")` on final failure.

    Deliberately builds every raised message from only `error_prefix` and `exc.code` -- never
    from `exc.filename`/`exc.url` -- since for some providers (e.g. Gemini) the request URL
    itself carries a secret (an API key in the query string) that must never end up in an
    exception message or log line.
    """
    attempts = max_retries + 1
    for attempt in range(attempts):
        try:
            return transport(request, timeout_seconds)
        except HTTPError as exc:
            if exc.code < 500 or attempt == attempts - 1:
                raise error_cls(f"{error_prefix} request failed with status {exc.code}") from exc
        except URLError as exc:
            if attempt == attempts - 1:
                raise error_cls(f"{error_prefix} request failed") from exc
        if retry_backoff_seconds > 0:
            time.sleep(retry_backoff_seconds * (attempt + 1))
    raise error_cls(f"{error_prefix} request failed")


# Shared OpenAI-compatible chat-completions request body + response parsing.
#
# openai.py, deepseek.py, and generic_openai_compatible.py each independently duplicated the
# exact same `{"model", "messages": [system, user-json], "temperature": 0.2}` request-body
# construction (two of the three also add `"response_format": {"type": "json_object"}`) and the
# exact same `response["choices"][0]["message"]["content"]` extraction/parsing sequence. This is
# that logic, extracted once. Deliberately NOT used by anthropic.py or gemini.py -- those have
# genuinely different request/response shapes -- nor by openrouter.py, which has its own
# OpenRouter-specific headers/body already modeled independently.
def build_chat_completions_body(
    system_prompt: str,
    user_payload: dict[str, Any],
    schema_name: str,
    model: str,
    *,
    temperature: float = 0.2,
    response_format_json: bool = True,
) -> dict[str, Any]:
    """Build an OpenAI-compatible /chat/completions request body.

    `response_format_json` controls whether `"response_format": {"type": "json_object"}` is
    included -- openai.py and generic_openai_compatible.py set this (True, the default);
    deepseek.py's API does not support/require it and omits it (pass False).
    """
    body: dict[str, Any] = {
        "model": model,
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
        "temperature": temperature,
    }
    if response_format_json:
        body["response_format"] = {"type": "json_object"}
    return body


def extract_chat_completion_content(
    response: dict[str, Any],
    error_cls: type[Exception],
    error_prefix: str,
    *,
    try_json_loads_first: bool = True,
) -> dict[str, Any]:
    """Extract and parse the JSON object from an OpenAI-compatible chat-completions response.

    Pulls `response["choices"][0]["message"]["content"]`, raising `error_cls` with a
    provider-prefixed message if the shape is malformed or the content isn't a string.

    `try_json_loads_first` mirrors a genuine, deliberate difference between adapters: openai.py
    and generic_openai_compatible.py request `response_format={"type": "json_object"}`, so they
    first attempt a direct `json.loads` of the content and only fall back to the tolerant
    `extract_json_object` (which tolerates stray markdown fences etc.) if that fails or the
    result isn't a dict. deepseek.py does not request that response_format at all, so it skips
    the direct-`json.loads` attempt entirely and goes straight to `extract_json_object` -- pass
    `try_json_loads_first=False` to reproduce that.
    """
    # Local import to avoid a module-level import cycle: openrouter.py itself imports several
    # names from base.py (ProviderKeySource, Transport, default_transport, resolve_api_key,
    # send_with_retries), so importing openrouter.py at base.py's module scope would be circular.
    from .openrouter import OpenRouterError, extract_json_object

    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise error_cls(f"{error_prefix} response shape was invalid") from exc
    if not isinstance(content, str):
        raise error_cls(f"{error_prefix} response content was invalid")

    if try_json_loads_first:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed

    try:
        return extract_json_object(content)
    except OpenRouterError as exc:
        raise error_cls(str(exc)) from exc
