"""P5-2b: redaction/audit hardening for BYO (bring-your-own) per-request text-provider keys.

Covers two adapters with different key-format characteristics:
  - OpenRouter: keys have a distinctive `sk-or-...` prefix, already matched by
    security.SECRET_PATTERNS' generic `sk-[A-Za-z0-9_\\-]{12,}` pattern.
  - Gemini: keys have no distinctive prefix at all and ride in the URL query string
    (`?key=...`) rather than a header -- covered by the `[?&]key=...` pattern.

For each, this file forces a real provider-call failure (a 401/403-shaped HTTPError from a
fake transport) and asserts the raw key is absent from:
  (a) str(exc) -- the exception raised by the adapter
  (b) the event dict that would be handed to record_audit_event via security.audit_event
  (c) redact_text()/redact_output() applied to the exception message and to a synthetic
      log line built from it

It also exercises security.redact_text directly against realistic raw-key strings for all
six vendor key shapes to document which are caught by which pattern.
"""

from __future__ import annotations

from urllib.error import HTTPError

import pytest

from course_mcp_server.security import RequestContext, audit_event, redact_output, redact_text
from course_mcp_server.text_providers.gemini import GeminiError, GeminiTextProvider
from course_mcp_server.text_providers.openrouter import OpenRouterError, OpenRouterTextProvider

OPENROUTER_RAW_KEY = "sk-or-v1-abcdefghijklmnopqrstuvwxyz0123456789"
GEMINI_RAW_KEY = "AIzaSyDaGmWKa4JsXZ-HjGw7ISLan_Miidwd0rQ"  # realistic-shaped, no distinctive prefix


def _failing_transport(exc: Exception):
    def _transport(_request, _timeout):
        raise exc

    return _transport


def test_openrouter_failure_never_leaks_raw_key_anywhere():
    http_error = HTTPError(
        url="https://openrouter.ai/api/v1/chat/completions",
        code=401,
        msg="Unauthorized",
        hdrs=None,
        fp=None,
    )
    provider = OpenRouterTextProvider(transport=_failing_transport(http_error), api_key=OPENROUTER_RAW_KEY)

    with pytest.raises(OpenRouterError) as excinfo:
        provider.generate_json(
            system_prompt="Return JSON.",
            user_payload={"topic": "Ramp Safety"},
            schema_name="CourseOutline",
        )

    message = str(excinfo.value)
    assert OPENROUTER_RAW_KEY not in message
    assert "401" in message  # sanity: it's still a useful error, just not a leaky one

    # (b) whatever an audit-event write would capture for this failure -- audit_event() only
    # ever stores a sha256 hash of the payload (security.hash_payload), never the raw string,
    # so the raw key cannot appear in the persisted event regardless of what the message says.
    context = RequestContext(tenant_id="t1", user_id="u1", request_id="r1")
    event = audit_event("generate_course_blueprint", context, {"error": message}, {})
    assert OPENROUTER_RAW_KEY not in repr(event)
    assert OPENROUTER_RAW_KEY not in str(event.get("input_hash"))
    assert OPENROUTER_RAW_KEY not in str(event.get("output_hash"))

    # (c) redact_text/redact_output over the message and a synthetic log line
    assert OPENROUTER_RAW_KEY not in redact_text(message)
    synthetic_log_line = f"provider call failed: {message} (api_key={OPENROUTER_RAW_KEY})"
    redacted_log_line = redact_text(synthetic_log_line)
    assert OPENROUTER_RAW_KEY not in redacted_log_line
    assert "[REDACTED]" in redacted_log_line
    assert OPENROUTER_RAW_KEY not in redact_output({"detail": synthetic_log_line})["detail"]


def test_gemini_failure_never_leaks_raw_key_anywhere():
    # Gemini's key rides in the URL query string, so the realistic leak vector is the
    # HTTPError's .url/.filename carrying "?key=<raw>" -- confirm the adapter's own message
    # never references the URL at all (see gemini.py's _send_with_retries comment).
    http_error = HTTPError(
        url=f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={GEMINI_RAW_KEY}",
        code=403,
        msg="Forbidden",
        hdrs=None,
        fp=None,
    )
    provider = GeminiTextProvider.__new__(GeminiTextProvider)  # bypass from_env(); set config directly
    from dataclasses import replace

    from course_mcp_server.text_providers.gemini import GeminiConfig

    provider.config = replace(GeminiConfig(), api_key=GEMINI_RAW_KEY)
    provider._transport = _failing_transport(http_error)

    with pytest.raises(GeminiError) as excinfo:
        provider.generate_json(
            system_prompt="Return JSON.",
            user_payload={"topic": "Ramp Safety"},
            schema_name="CourseOutline",
        )

    message = str(excinfo.value)
    assert GEMINI_RAW_KEY not in message
    assert "403" in message

    context = RequestContext(tenant_id="t1", user_id="u1", request_id="r1")
    event = audit_event("generate_course_blueprint", context, {"error": message}, {})
    assert GEMINI_RAW_KEY not in repr(event)
    assert GEMINI_RAW_KEY not in str(event.get("input_hash"))
    assert GEMINI_RAW_KEY not in str(event.get("output_hash"))

    assert GEMINI_RAW_KEY not in redact_text(message)

    # A bare Gemini key has no distinctive prefix, so it is only reliably caught by the
    # `[?&]key=...` query-string pattern (added this cycle) -- confirm that pattern still
    # does its job on a realistic request-URL-shaped log line.
    synthetic_log_line = (
        f"outbound request to https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-pro:generateContent?key={GEMINI_RAW_KEY} failed"
    )
    redacted_log_line = redact_text(synthetic_log_line)
    assert GEMINI_RAW_KEY not in redacted_log_line
    assert "[REDACTED]" in redacted_log_line


@pytest.mark.parametrize(
    "raw_key",
    [
        "sk-or-v1-abcdefghijklmnopqrstuvwxyz0123456789",  # OpenRouter
        "sk-proj-abcdefghijklmnopqrstuvwxyz0123456789",  # OpenAI
        "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789",  # Anthropic
    ],
    ids=["openrouter", "openai", "anthropic"],
)
def test_distinctive_sk_prefixed_keys_are_redacted_by_generic_sk_pattern(raw_key):
    # All three of these vendors' key formats start with "sk-", so the pre-existing generic
    # `sk-[A-Za-z0-9_\-]{12,}` pattern in security.SECRET_PATTERNS already covers them --
    # no new vendor-specific pattern is needed for OpenRouter/OpenAI/Anthropic.
    text = f"Authorization: Bearer {raw_key}"
    redacted = redact_text(text)
    assert raw_key not in redacted
    assert "[REDACTED]" in redacted


def test_deepseek_key_without_header_label_relies_on_generic_key_value_pattern():
    # DeepSeek keys also happen to use an "sk-" prefix in practice, so they are additionally
    # caught by the generic sk- pattern. But even a DeepSeek-shaped key with no "sk-" prefix
    # at all is still caught by the pre-existing generic
    # `(api[_-]?key|token|secret|password)\s*[:=]\s*...` pattern as long as it appears in a
    # labeled key=value/key: value shape (the realistic shape for a log line or config dump).
    raw_key = "df-not-sk-prefixed-0123456789abcdef"
    text = f"api_key={raw_key}"
    redacted = redact_text(text)
    assert raw_key not in redacted
    assert "[REDACTED]" in redacted


def test_gemini_query_string_pattern_present_and_not_duplicated():
    # Documents/confirms the existing ?key=/&key= SECRET_PATTERNS entry (added earlier this
    # cycle for Gemini) is present exactly once -- this test fails loudly if a future change
    # accidentally adds a second, redundant query-string key pattern.
    from course_mcp_server.security import SECRET_PATTERNS

    query_key_patterns = [p for p in SECRET_PATTERNS if "key=" in p.pattern and ("?" in p.pattern or "&" in p.pattern)]
    assert len(query_key_patterns) == 1, (
        "expected exactly one ?key=/&key= query-string SECRET_PATTERNS entry, "
        f"found {len(query_key_patterns)}: {[p.pattern for p in query_key_patterns]}"
    )
