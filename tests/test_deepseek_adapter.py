import json
from urllib.error import HTTPError, URLError

from course_mcp_server.text_providers.deepseek import (
    DEFAULT_DEEPSEEK_MODEL,
    DeepSeekConfig,
    DeepSeekError,
    DeepSeekTextProvider,
)


def test_deepseek_config_defaults_to_requested_model(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    config = DeepSeekConfig.from_env()

    assert config.model == DEFAULT_DEEPSEEK_MODEL
    assert config.api_key is None
    assert config.enabled is False


def test_deepseek_provider_sends_chat_completion_request():
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

    provider = DeepSeekTextProvider(
        DeepSeekConfig(api_key="key-123", model="deepseek-chat"),
        transport=fake_transport,
    )

    result = provider.generate_json(
        system_prompt="Return JSON.",
        user_payload={"topic": "Ramp Safety"},
        schema_name="CourseOutline",
    )

    assert result == {"course_title": "Ramp Safety", "modules": []}
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer key-123"
    assert captured["headers"]["Content-type"] == "application/json"
    assert captured["body"]["model"] == "deepseek-chat"
    assert captured["body"]["messages"][0] == {"role": "system", "content": "Return JSON."}
    assert captured["body"]["messages"][1]["role"] == "user"
    assert json.loads(captured["body"]["messages"][1]["content"]) == {
        "schema": "CourseOutline",
        "payload": {"topic": "Ramp Safety"},
    }


def test_deepseek_provider_uses_override_model():
    captured = {}

    def fake_transport(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return {"choices": [{"message": {"content": '{"ok":true}'}}]}

    provider = DeepSeekTextProvider(
        DeepSeekConfig(api_key="key-123", model="deepseek-chat"),
        transport=fake_transport,
    )

    provider.generate_json("Return JSON.", {}, "Any", model="deepseek-reasoner")

    assert captured["body"]["model"] == "deepseek-reasoner"


def test_deepseek_disabled_without_api_key_raises():
    provider = DeepSeekTextProvider(DeepSeekConfig(api_key=None))

    try:
        provider.generate_json("Return JSON.", {}, "Any")
    except DeepSeekError as exc:
        assert "not configured" in str(exc)
    else:
        raise AssertionError("Expected DeepSeekError")


def test_deepseek_errors_do_not_expose_response_body():
    def fake_transport(_request, _timeout):
        raise HTTPError(
            url="https://api.deepseek.com/chat/completions",
            code=401,
            msg="Unauthorized secret-token",
            hdrs=None,
            fp=None,
        )

    provider = DeepSeekTextProvider(DeepSeekConfig(api_key="bad-key"), transport=fake_transport)

    try:
        provider.generate_json("Return JSON.", {"topic": "Ramp"}, "CourseOutline")
    except DeepSeekError as exc:
        assert str(exc) == "DeepSeek request failed with status 401"
    else:
        raise AssertionError("Expected DeepSeekError")


def test_deepseek_retries_transient_url_errors():
    attempts = {"count": 0}

    def flaky_transport(_request, _timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise URLError("temporary network problem")
        return {"choices": [{"message": {"content": '{"ok":true}'}}]}

    provider = DeepSeekTextProvider(
        DeepSeekConfig(api_key="key-123", max_retries=1, retry_backoff_seconds=0),
        transport=flaky_transport,
    )

    assert provider.generate_json("Return JSON.", {}, "Any") == {"ok": True}
    assert attempts["count"] == 2


def test_deepseek_retries_5xx_http_errors_only():
    attempts = {"count": 0}

    def flaky_transport(_request, _timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise HTTPError(
                url="https://api.deepseek.com/chat/completions",
                code=503,
                msg="Service unavailable",
                hdrs=None,
                fp=None,
            )
        return {"choices": [{"message": {"content": '{"ok":true}'}}]}

    provider = DeepSeekTextProvider(
        DeepSeekConfig(api_key="key-123", max_retries=1, retry_backoff_seconds=0),
        transport=flaky_transport,
    )

    assert provider.generate_json("Return JSON.", {}, "Any") == {"ok": True}
    assert attempts["count"] == 2


def test_deepseek_fails_fast_on_4xx_no_retry():
    attempts = {"count": 0}

    def fake_transport(_request, _timeout):
        attempts["count"] += 1
        raise HTTPError(
            url="https://api.deepseek.com/chat/completions",
            code=400,
            msg="Bad request",
            hdrs=None,
            fp=None,
        )

    provider = DeepSeekTextProvider(
        DeepSeekConfig(api_key="key-123", max_retries=2, retry_backoff_seconds=0),
        transport=fake_transport,
    )

    try:
        provider.generate_json("Return JSON.", {}, "Any")
    except DeepSeekError as exc:
        assert str(exc) == "DeepSeek request failed with status 400"
    else:
        raise AssertionError("Expected DeepSeekError")

    assert attempts["count"] == 1
