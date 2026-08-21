import json
from urllib.error import HTTPError, URLError

from course_mcp_server.text_providers.openai import (
    DEFAULT_OPENAI_MODEL,
    OpenAIConfig,
    OpenAIError,
    OpenAITextProvider,
)


def test_openai_config_defaults_to_requested_model(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY_FILE", raising=False)

    config = OpenAIConfig.from_env()

    assert config.model == DEFAULT_OPENAI_MODEL
    assert config.api_key is None


def test_openai_config_enabled_is_false_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY_FILE", raising=False)

    config = OpenAIConfig.from_env()

    assert config.enabled is False


def test_openai_config_enabled_is_true_with_api_key():
    config = OpenAIConfig(api_key="key-123")

    assert config.enabled is True


def test_openai_provider_sends_chat_completion_request():
    captured = {}

    def fake_transport(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"course_title":"Ramp Safety","modules":[]}',
                    }
                }
            ]
        }

    provider = OpenAITextProvider(
        OpenAIConfig(api_key="key-123", model="gpt-4o-mini"),
        transport=fake_transport,
    )

    result = provider.generate_json(
        system_prompt="Return JSON.",
        user_payload={"topic": "Ramp Safety"},
        schema_name="CourseOutline",
    )

    assert result == {"course_title": "Ramp Safety", "modules": []}
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer key-123"
    assert captured["body"]["model"] == "gpt-4o-mini"
    assert captured["body"]["messages"][0]["role"] == "system"
    assert captured["body"]["messages"][1]["role"] == "user"
    assert captured["body"]["response_format"] == {"type": "json_object"}


def test_openai_provider_uses_explicit_model_override_when_given():
    captured = {}

    def fake_transport(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return {"choices": [{"message": {"content": "{}"}}]}

    provider = OpenAITextProvider(
        OpenAIConfig(api_key="key-123", model="gpt-4o-mini"),
        transport=fake_transport,
    )

    provider.generate_json("sys", {}, "Any", model="gpt-4o")

    assert captured["body"]["model"] == "gpt-4o"


def test_openai_provider_falls_back_to_extract_json_object_when_not_pure_json():
    def fake_transport(_request, _timeout):
        return {
            "choices": [
                {
                    "message": {
                        "content": 'Here is the JSON:\n```json\n{"ok":true}\n```',
                    }
                }
            ]
        }

    provider = OpenAITextProvider(OpenAIConfig(api_key="key-123"), transport=fake_transport)

    assert provider.generate_json("sys", {}, "Any") == {"ok": True}


def test_openai_provider_raises_when_api_key_missing():
    provider = OpenAITextProvider(OpenAIConfig(api_key=None), transport=lambda r, t: {})

    try:
        provider.generate_json("sys", {}, "Any")
    except OpenAIError as exc:
        assert "not configured" in str(exc)
    else:
        raise AssertionError("Expected OpenAIError")


def test_openai_errors_do_not_expose_response_body():
    def fake_transport(_request, _timeout):
        raise HTTPError(
            url="https://api.openai.com/v1/chat/completions",
            code=401,
            msg="Unauthorized secret-token",
            hdrs=None,
            fp=None,
        )

    provider = OpenAITextProvider(OpenAIConfig(api_key="bad-key"), transport=fake_transport)

    try:
        provider.generate_json("Return JSON.", {"topic": "Ramp"}, "CourseOutline")
    except OpenAIError as exc:
        assert str(exc) == "OpenAI request failed with status 401"
    else:
        raise AssertionError("Expected OpenAIError")


def test_openai_fails_fast_on_4xx_without_retrying():
    attempts = {"count": 0}

    def flaky_transport(_request, _timeout):
        attempts["count"] += 1
        raise HTTPError(
            url="https://api.openai.com/v1/chat/completions",
            code=400,
            msg="Bad request",
            hdrs=None,
            fp=None,
        )

    provider = OpenAITextProvider(
        OpenAIConfig(api_key="key-123", max_retries=2, retry_backoff_seconds=0),
        transport=flaky_transport,
    )

    try:
        provider.generate_json("Return JSON.", {}, "Any")
    except OpenAIError:
        pass
    else:
        raise AssertionError("Expected OpenAIError")

    assert attempts["count"] == 1


def test_openai_retries_transient_url_errors():
    attempts = {"count": 0}

    def flaky_transport(_request, _timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise URLError("temporary network problem")
        return {"choices": [{"message": {"content": '{"ok":true}'}}]}

    provider = OpenAITextProvider(
        OpenAIConfig(api_key="key-123", max_retries=1, retry_backoff_seconds=0),
        transport=flaky_transport,
    )

    assert provider.generate_json("Return JSON.", {}, "Any") == {"ok": True}
    assert attempts["count"] == 2


def test_openai_retries_5xx_http_errors_then_succeeds():
    attempts = {"count": 0}

    def flaky_transport(_request, _timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise HTTPError(
                url="https://api.openai.com/v1/chat/completions",
                code=503,
                msg="Service unavailable",
                hdrs=None,
                fp=None,
            )
        return {"choices": [{"message": {"content": '{"ok":true}'}}]}

    provider = OpenAITextProvider(
        OpenAIConfig(api_key="key-123", max_retries=1, retry_backoff_seconds=0),
        transport=flaky_transport,
    )

    assert provider.generate_json("Return JSON.", {}, "Any") == {"ok": True}
    assert attempts["count"] == 2
