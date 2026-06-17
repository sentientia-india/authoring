import json
from urllib.error import HTTPError, URLError

from course_mcp_server.llm_openrouter import (
    DEFAULT_OPENROUTER_MODEL,
    OpenRouterClient,
    OpenRouterConfig,
    OpenRouterError,
    extract_json_object,
)


def test_openrouter_config_defaults_to_requested_model(monkeypatch):
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    config = OpenRouterConfig.from_env()

    assert config.model == DEFAULT_OPENROUTER_MODEL
    assert config.api_key is None


def test_extract_json_object_from_markdown_response():
    content = 'Here is the course:\n```json\n{"course_title":"Ramp Safety","modules":[]}\n```'

    assert extract_json_object(content) == {"course_title": "Ramp Safety", "modules": []}


def test_openrouter_client_sends_chat_completion_request():
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

    client = OpenRouterClient(
        OpenRouterConfig(api_key="key-123", model="nvidia/nemotron-3-ultra-550b-a55b:free"),
        transport=fake_transport,
    )

    result = client.generate_json(
        system_prompt="Return JSON.",
        user_payload={"topic": "Ramp Safety"},
        schema_name="CourseOutline",
    )

    assert result == {"course_title": "Ramp Safety", "modules": []}
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer key-123"
    assert captured["body"]["model"] == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert captured["body"]["messages"][0]["role"] == "system"


def test_openrouter_errors_do_not_expose_response_body():
    def fake_transport(_request, _timeout):
        raise HTTPError(
            url="https://openrouter.ai/api/v1/chat/completions",
            code=401,
            msg="Unauthorized secret-token",
            hdrs=None,
            fp=None,
        )

    client = OpenRouterClient(OpenRouterConfig(api_key="bad-key"), transport=fake_transport)

    try:
        client.generate_json("Return JSON.", {"topic": "Ramp"}, "CourseOutline")
    except OpenRouterError as exc:
        assert str(exc) == "OpenRouter request failed with status 401"
    else:
        raise AssertionError("Expected OpenRouterError")


def test_openrouter_retries_transient_url_errors():
    attempts = {"count": 0}

    def flaky_transport(_request, _timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise URLError("temporary network problem")
        return {"choices": [{"message": {"content": '{"ok":true}'}}]}

    client = OpenRouterClient(
        OpenRouterConfig(api_key="key-123", max_retries=1, retry_backoff_seconds=0),
        transport=flaky_transport,
    )

    assert client.generate_json("Return JSON.", {}, "Any") == {"ok": True}
    assert attempts["count"] == 2


def test_openrouter_retries_5xx_http_errors_only():
    attempts = {"count": 0}

    def flaky_transport(_request, _timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise HTTPError(
                url="https://openrouter.ai/api/v1/chat/completions",
                code=503,
                msg="Service unavailable",
                hdrs=None,
                fp=None,
            )
        return {"choices": [{"message": {"content": '{"ok":true}'}}]}

    client = OpenRouterClient(
        OpenRouterConfig(api_key="key-123", max_retries=1, retry_backoff_seconds=0),
        transport=flaky_transport,
    )

    assert client.generate_json("Return JSON.", {}, "Any") == {"ok": True}
    assert attempts["count"] == 2
