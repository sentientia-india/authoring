import json
from urllib.error import HTTPError, URLError

from course_mcp_server.security import redact_text
from course_mcp_server.text_providers.gemini import (
    DEFAULT_GEMINI_MODEL,
    GeminiConfig,
    GeminiError,
    GeminiTextProvider,
)

RAW_KEY = "AIzaSyTestSecretValue1234567890"


def test_gemini_config_defaults_to_requested_model(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    config = GeminiConfig.from_env()

    assert config.model == DEFAULT_GEMINI_MODEL
    assert config.api_key is None
    assert config.enabled is False


def test_gemini_provider_sends_generate_content_request_with_key_in_query_string():
    captured = {}

    def fake_transport(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return {
            "candidates": [
                {"content": {"parts": [{"text": '{"course_title":"Ramp Safety","modules":[]}'}]}},
            ],
        }

    provider = GeminiTextProvider(
        GeminiConfig(api_key=RAW_KEY, model="gemini-2.5-pro"),
        transport=fake_transport,
    )

    result = provider.generate_json(
        system_prompt="Return JSON.",
        user_payload={"topic": "Ramp Safety"},
        schema_name="CourseOutline",
    )

    assert result == {"course_title": "Ramp Safety", "modules": []}

    # The API key rides in the URL query string -- NOT a header.
    assert captured["url"] == (
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={RAW_KEY}"
    )
    assert "Authorization" not in captured["headers"]
    assert "X-api-key" not in captured["headers"]
    assert not any(RAW_KEY in value for value in captured["headers"].values())

    # Request body shape: contents[].parts[].text, systemInstruction as a separate top-level field.
    assert captured["body"]["systemInstruction"] == {"parts": [{"text": "Return JSON."}]}
    assert captured["body"]["contents"] == [
        {
            "parts": [
                {
                    "text": json.dumps(
                        {"schema": "CourseOutline", "payload": {"topic": "Ramp Safety"}},
                        ensure_ascii=True,
                    )
                }
            ]
        }
    ]


def test_gemini_provider_uses_override_model_in_url():
    captured = {}

    def fake_transport(request, timeout):
        captured["url"] = request.full_url
        return {"candidates": [{"content": {"parts": [{"text": '{"ok":true}'}]}}]}

    provider = GeminiTextProvider(
        GeminiConfig(api_key=RAW_KEY, model="gemini-2.5-pro"),
        transport=fake_transport,
    )

    provider.generate_json("Return JSON.", {}, "Any", model="gemini-2.5-flash")

    assert ":generateContent" in captured["url"]
    assert "gemini-2.5-flash" in captured["url"]
    assert "gemini-2.5-pro" not in captured["url"]


def test_gemini_parses_candidates_content_parts_shape():
    def fake_transport(request, timeout):
        return {"candidates": [{"content": {"parts": [{"text": '{"a":1}'}]}}]}

    provider = GeminiTextProvider(GeminiConfig(api_key=RAW_KEY), transport=fake_transport)

    assert provider.generate_json("Return JSON.", {}, "Any") == {"a": 1}


def test_gemini_disabled_without_api_key_raises():
    provider = GeminiTextProvider(GeminiConfig(api_key=None))

    try:
        provider.generate_json("Return JSON.", {}, "Any")
    except GeminiError as exc:
        assert "not configured" in str(exc)
    else:
        raise AssertionError("Expected GeminiError")


def test_gemini_retries_transient_url_errors():
    attempts = {"count": 0}

    def flaky_transport(_request, _timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise URLError("temporary network problem")
        return {"candidates": [{"content": {"parts": [{"text": '{"ok":true}'}]}}]}

    provider = GeminiTextProvider(
        GeminiConfig(api_key=RAW_KEY, max_retries=1, retry_backoff_seconds=0),
        transport=flaky_transport,
    )

    assert provider.generate_json("Return JSON.", {}, "Any") == {"ok": True}
    assert attempts["count"] == 2


def test_gemini_retries_5xx_http_errors_only():
    attempts = {"count": 0}

    def flaky_transport(_request, _timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise HTTPError(
                url=f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={RAW_KEY}",
                code=503,
                msg="Service unavailable",
                hdrs=None,
                fp=None,
            )
        return {"candidates": [{"content": {"parts": [{"text": '{"ok":true}'}]}}]}

    provider = GeminiTextProvider(
        GeminiConfig(api_key=RAW_KEY, max_retries=1, retry_backoff_seconds=0),
        transport=flaky_transport,
    )

    assert provider.generate_json("Return JSON.", {}, "Any") == {"ok": True}
    assert attempts["count"] == 2


def test_gemini_fails_fast_on_4xx_no_retry():
    attempts = {"count": 0}

    def fake_transport(_request, _timeout):
        attempts["count"] += 1
        raise HTTPError(
            url=f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={RAW_KEY}",
            code=400,
            msg="Bad request",
            hdrs=None,
            fp=None,
        )

    provider = GeminiTextProvider(
        GeminiConfig(api_key=RAW_KEY, max_retries=2, retry_backoff_seconds=0),
        transport=fake_transport,
    )

    try:
        provider.generate_json("Return JSON.", {}, "Any")
    except GeminiError as exc:
        assert str(exc) == "Gemini request failed with status 400"
    else:
        raise AssertionError("Expected GeminiError")

    assert attempts["count"] == 1


def test_gemini_api_key_never_leaks_unredacted_in_exception_or_log_text():
    """Proves the key never appears in this adapter's exceptions, AND that if the raw
    request URL (which does legitimately contain the key) were ever logged or audited via
    security.redact_text, the key would be scrubbed -- this is the SECRET_PATTERNS extension
    this change made for the key-in-query-string shape."""

    captured_request = {}

    def fake_transport(request, _timeout):
        captured_request["url"] = request.full_url
        raise HTTPError(
            url=request.full_url,
            code=401,
            msg=f"Unauthorized for key={RAW_KEY}",
            hdrs=None,
            fp=None,
        )

    provider = GeminiTextProvider(GeminiConfig(api_key=RAW_KEY, max_retries=0), transport=fake_transport)

    try:
        provider.generate_json("Return JSON.", {"topic": "Ramp"}, "CourseOutline")
        raise AssertionError("Expected GeminiError")
    except GeminiError as exc:
        # 1. The adapter's own exception text never contains the raw key.
        assert RAW_KEY not in str(exc)
        assert str(exc) == "Gemini request failed with status 401"

    # 2. The request URL genuinely does carry the raw key (sanity check the test is real).
    assert RAW_KEY in captured_request["url"]

    # 3. Feeding that URL through the shared redaction helper (what any audit/log call site
    # in this codebase uses before writing text out) scrubs the key.
    redacted = redact_text(captured_request["url"])
    assert RAW_KEY not in redacted
    assert "[REDACTED]" in redacted

    # 4. And a log-style message embedding both a "key=" query fragment and the raw value is
    # also fully scrubbed.
    log_line = f"Gemini call failed, request={captured_request['url']}"
    redacted_log_line = redact_text(log_line)
    assert RAW_KEY not in redacted_log_line
