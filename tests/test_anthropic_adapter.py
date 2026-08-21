import json
from urllib.error import HTTPError, URLError

from course_mcp_server.text_providers.anthropic import (
    ANTHROPIC_API_VERSION,
    DEFAULT_ANTHROPIC_MODEL,
    AnthropicConfig,
    AnthropicError,
    AnthropicTextProvider,
)


def test_anthropic_config_defaults_to_requested_model(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    config = AnthropicConfig.from_env()

    assert config.model == DEFAULT_ANTHROPIC_MODEL
    assert config.api_key is None
    assert config.enabled is False


def test_anthropic_provider_sends_messages_api_request_with_top_level_system():
    captured = {}

    def fake_transport(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return {
            "content": [
                {"type": "text", "text": '{"course_title":"Ramp Safety","modules":[]}'},
            ],
        }

    provider = AnthropicTextProvider(
        AnthropicConfig(api_key="key-123", model="claude-opus-5"),
        transport=fake_transport,
    )

    result = provider.generate_json(
        system_prompt="Return JSON.",
        user_payload={"topic": "Ramp Safety"},
        schema_name="CourseOutline",
    )

    assert result == {"course_title": "Ramp Safety", "modules": []}
    assert captured["url"] == "https://api.anthropic.com/v1/messages"

    # Auth is x-api-key, NOT Authorization: Bearer.
    assert captured["headers"]["X-api-key"] == "key-123"
    assert "Authorization" not in captured["headers"]
    assert captured["headers"]["Anthropic-version"] == ANTHROPIC_API_VERSION

    # `system` must be a TOP-LEVEL request field, not a message with role="system".
    assert captured["body"]["system"] == "Return JSON."
    assert captured["body"]["model"] == "claude-opus-5"
    assert all(message.get("role") != "system" for message in captured["body"]["messages"])
    assert captured["body"]["messages"] == [
        {
            "role": "user",
            "content": json.dumps(
                {"schema": "CourseOutline", "payload": {"topic": "Ramp Safety"}},
                ensure_ascii=True,
            ),
        }
    ]


def test_anthropic_provider_uses_override_model():
    captured = {}

    def fake_transport(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return {"content": [{"type": "text", "text": '{"ok":true}'}]}

    provider = AnthropicTextProvider(
        AnthropicConfig(api_key="key-123", model="claude-opus-5"),
        transport=fake_transport,
    )

    provider.generate_json("Return JSON.", {}, "Any", model="claude-sonnet-5")

    assert captured["body"]["model"] == "claude-sonnet-5"


def test_anthropic_parses_content_block_array_not_choices_shape():
    def fake_transport(request, timeout):
        return {
            "content": [
                {"type": "text", "text": '{"a":1}'},
            ],
            "stop_reason": "end_turn",
        }

    provider = AnthropicTextProvider(AnthropicConfig(api_key="key-123"), transport=fake_transport)

    assert provider.generate_json("Return JSON.", {}, "Any") == {"a": 1}


def test_anthropic_disabled_without_api_key_raises():
    provider = AnthropicTextProvider(AnthropicConfig(api_key=None))

    try:
        provider.generate_json("Return JSON.", {}, "Any")
    except AnthropicError as exc:
        assert "not configured" in str(exc)
    else:
        raise AssertionError("Expected AnthropicError")


def test_anthropic_errors_do_not_expose_response_body():
    def fake_transport(_request, _timeout):
        raise HTTPError(
            url="https://api.anthropic.com/v1/messages",
            code=401,
            msg="Unauthorized secret-token",
            hdrs=None,
            fp=None,
        )

    provider = AnthropicTextProvider(AnthropicConfig(api_key="bad-key"), transport=fake_transport)

    try:
        provider.generate_json("Return JSON.", {"topic": "Ramp"}, "CourseOutline")
    except AnthropicError as exc:
        assert str(exc) == "Anthropic request failed with status 401"
    else:
        raise AssertionError("Expected AnthropicError")


def test_anthropic_retries_transient_url_errors():
    attempts = {"count": 0}

    def flaky_transport(_request, _timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise URLError("temporary network problem")
        return {"content": [{"type": "text", "text": '{"ok":true}'}]}

    provider = AnthropicTextProvider(
        AnthropicConfig(api_key="key-123", max_retries=1, retry_backoff_seconds=0),
        transport=flaky_transport,
    )

    assert provider.generate_json("Return JSON.", {}, "Any") == {"ok": True}
    assert attempts["count"] == 2


def test_anthropic_retries_5xx_http_errors_only():
    attempts = {"count": 0}

    def flaky_transport(_request, _timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise HTTPError(
                url="https://api.anthropic.com/v1/messages",
                code=529,
                msg="Overloaded",
                hdrs=None,
                fp=None,
            )
        return {"content": [{"type": "text", "text": '{"ok":true}'}]}

    provider = AnthropicTextProvider(
        AnthropicConfig(api_key="key-123", max_retries=1, retry_backoff_seconds=0),
        transport=flaky_transport,
    )

    assert provider.generate_json("Return JSON.", {}, "Any") == {"ok": True}
    assert attempts["count"] == 2


def test_anthropic_fails_fast_on_4xx_no_retry():
    attempts = {"count": 0}

    def fake_transport(_request, _timeout):
        attempts["count"] += 1
        raise HTTPError(
            url="https://api.anthropic.com/v1/messages",
            code=400,
            msg="Bad request",
            hdrs=None,
            fp=None,
        )

    provider = AnthropicTextProvider(
        AnthropicConfig(api_key="key-123", max_retries=2, retry_backoff_seconds=0),
        transport=fake_transport,
    )

    try:
        provider.generate_json("Return JSON.", {}, "Any")
    except AnthropicError as exc:
        assert str(exc) == "Anthropic request failed with status 400"
    else:
        raise AssertionError("Expected AnthropicError")

    assert attempts["count"] == 1
