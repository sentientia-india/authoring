import json
from urllib.error import HTTPError, URLError

from course_mcp_server.text_providers.generic_openai_compatible import (
    GenericOpenAICompatibleConfig,
    GenericOpenAICompatibleError,
    GenericOpenAICompatibleProvider,
)

CUSTOM_BASE_URL = "https://example-vendor.test/v1"
CUSTOM_MODEL = "some-custom-model"


def test_config_has_no_env_defaults_and_requires_explicit_fields():
    config = GenericOpenAICompatibleConfig(base_url=CUSTOM_BASE_URL, model=CUSTOM_MODEL)

    assert config.base_url == CUSTOM_BASE_URL
    assert config.model == CUSTOM_MODEL
    assert config.api_key is None
    assert not hasattr(GenericOpenAICompatibleConfig, "from_env")


def test_provider_sends_request_to_caller_supplied_base_url_not_any_default():
    captured = {}

    def fake_transport(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return {
            "choices": [
                {"message": {"content": '{"course_title":"Ramp Safety","modules":[]}'}}
            ]
        }

    provider = GenericOpenAICompatibleProvider(
        base_url=CUSTOM_BASE_URL,
        api_key="key-123",
        model=CUSTOM_MODEL,
        transport=fake_transport,
    )

    result = provider.generate_json(
        system_prompt="Return JSON.",
        user_payload={"topic": "Ramp Safety"},
        schema_name="CourseOutline",
    )

    assert result == {"course_title": "Ramp Safety", "modules": []}
    # (a) request goes to the caller-supplied base_url, not api.openai.com or openrouter.ai
    assert captured["url"] == "https://example-vendor.test/v1/chat/completions"
    assert "api.openai.com" not in captured["url"]
    assert "openrouter.ai" not in captured["url"]
    assert captured["body"]["model"] == CUSTOM_MODEL


def test_no_vendor_specific_headers_leak_into_the_request():
    """(b) No OpenRouter/OpenAI-specific headers leak into the request.

    OpenRouterClient.generate_json() (openrouter.py) always sets X-OpenRouter-Title and
    conditionally sets HTTP-Referer. This adapter must never send those -- an arbitrary
    OpenAI-compatible endpoint (Ollama, Together.ai, Groq, Fireworks, ...) has no reason to
    understand OpenRouter-specific headers, and sending them would leak an assumption that
    the target is OpenRouter.
    """
    captured = {}

    def fake_transport(request, timeout):
        captured["headers"] = dict(request.header_items())
        return {"choices": [{"message": {"content": "{}"}}]}

    provider = GenericOpenAICompatibleProvider(
        base_url=CUSTOM_BASE_URL,
        api_key="key-123",
        model=CUSTOM_MODEL,
        transport=fake_transport,
    )
    provider.generate_json("sys", {}, "Any")

    header_names = {name.lower() for name in captured["headers"]}
    assert "x-openrouter-title" not in header_names
    assert "http-referer" not in header_names
    assert header_names == {"content-type", "authorization"}
    assert captured["headers"]["Authorization"] == "Bearer key-123"


def test_omits_authorization_header_when_no_api_key_supplied():
    """A local Ollama endpoint typically needs no credential at all."""
    captured = {}

    def fake_transport(request, timeout):
        captured["headers"] = dict(request.header_items())
        return {"choices": [{"message": {"content": "{}"}}]}

    provider = GenericOpenAICompatibleProvider(
        base_url="http://localhost:11434/v1",
        api_key=None,
        model="llama3",
        transport=fake_transport,
    )
    provider.generate_json("sys", {}, "Any")

    header_names = {name.lower() for name in captured["headers"]}
    assert "authorization" not in header_names


def test_response_parsing_matches_openai_adapter_behavior():
    """(c) Response parsing works the same as the OpenAI adapter's, including the tolerant
    fallback extraction for content that isn't pure JSON despite response_format."""

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

    provider = GenericOpenAICompatibleProvider(
        base_url=CUSTOM_BASE_URL,
        api_key="key-123",
        model=CUSTOM_MODEL,
        transport=fake_transport,
    )

    assert provider.generate_json("sys", {}, "Any") == {"ok": True}


def test_fails_fast_on_4xx_without_retrying():
    """(d) retry-on-5xx/fail-fast-on-4xx still work."""
    attempts = {"count": 0}

    def flaky_transport(_request, _timeout):
        attempts["count"] += 1
        raise HTTPError(
            url=CUSTOM_BASE_URL + "/chat/completions",
            code=400,
            msg="Bad request",
            hdrs=None,
            fp=None,
        )

    provider = GenericOpenAICompatibleProvider(
        base_url=CUSTOM_BASE_URL,
        api_key="key-123",
        model=CUSTOM_MODEL,
        max_retries=2,
        retry_backoff_seconds=0,
        transport=flaky_transport,
    )

    try:
        provider.generate_json("Return JSON.", {}, "Any")
    except GenericOpenAICompatibleError:
        pass
    else:
        raise AssertionError("Expected GenericOpenAICompatibleError")

    assert attempts["count"] == 1


def test_retries_5xx_http_errors_then_succeeds():
    attempts = {"count": 0}

    def flaky_transport(_request, _timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise HTTPError(
                url=CUSTOM_BASE_URL + "/chat/completions",
                code=503,
                msg="Service unavailable",
                hdrs=None,
                fp=None,
            )
        return {"choices": [{"message": {"content": '{"ok":true}'}}]}

    provider = GenericOpenAICompatibleProvider(
        base_url=CUSTOM_BASE_URL,
        api_key="key-123",
        model=CUSTOM_MODEL,
        max_retries=1,
        retry_backoff_seconds=0,
        transport=flaky_transport,
    )

    assert provider.generate_json("Return JSON.", {}, "Any") == {"ok": True}
    assert attempts["count"] == 2


def test_retries_transient_connection_errors_like_a_not_yet_running_local_server():
    """A local Ollama endpoint that isn't running yet fails the TCP connection outright
    (URLError), not with an HTTP status -- confirm that still retries generically."""
    attempts = {"count": 0}

    def flaky_transport(_request, _timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise URLError("connection refused")
        return {"choices": [{"message": {"content": '{"ok":true}'}}]}

    provider = GenericOpenAICompatibleProvider(
        base_url="http://localhost:11434/v1",
        api_key=None,
        model="llama3",
        max_retries=1,
        retry_backoff_seconds=0,
        transport=flaky_transport,
    )

    assert provider.generate_json("Return JSON.", {}, "Any") == {"ok": True}
    assert attempts["count"] == 2


def test_explicit_model_override_is_respected():
    captured = {}

    def fake_transport(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return {"choices": [{"message": {"content": "{}"}}]}

    provider = GenericOpenAICompatibleProvider(
        base_url=CUSTOM_BASE_URL,
        api_key="key-123",
        model=CUSTOM_MODEL,
        transport=fake_transport,
    )

    provider.generate_json("sys", {}, "Any", model="override-model")

    assert captured["body"]["model"] == "override-model"


def test_key_source_is_request_when_api_key_is_supplied():
    provider = GenericOpenAICompatibleProvider(
        base_url=CUSTOM_BASE_URL,
        api_key="key-123",
        model=CUSTOM_MODEL,
        transport=lambda r, t: {"choices": [{"message": {"content": "{}"}}]},
    )

    assert provider.key_source == "request"
