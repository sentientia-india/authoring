from __future__ import annotations

from urllib.error import HTTPError, URLError

from course_mcp_server.video_providers import ElevenLabsConfig, ElevenLabsNarrationProvider
from course_mcp_server.video_providers.elevenlabs import DEFAULT_ELEVENLABS_MODEL_ID, ElevenLabsError


def test_elevenlabs_config_defaults(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_MODEL_ID", raising=False)

    config = ElevenLabsConfig.from_env()

    assert config.api_key is None
    assert config.model_id == DEFAULT_ELEVENLABS_MODEL_ID
    assert config.enabled is False


def test_not_configured_raises_before_any_transport_call():
    def fail_transport(_request, _timeout):
        raise AssertionError("transport should not be called when the provider is not configured")

    provider = ElevenLabsNarrationProvider(
        config=ElevenLabsConfig(api_key=None), transport=fail_transport
    )

    try:
        provider.submit({"text": "Welcome to the course."})
    except ElevenLabsError as exc:
        assert "not configured" in str(exc)
    else:
        raise AssertionError("Expected ElevenLabsError")


def test_submit_poll_fetch_success_with_fake_mp3_bytes():
    captured = {}
    fake_mp3 = b"ID3\x03\x00\x00\x00" + b"\x00" * 64  # realistic-looking fake MP3 header + payload

    def fake_transport(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["method"] = request.get_method()
        captured["timeout"] = timeout
        return fake_mp3

    provider = ElevenLabsNarrationProvider(
        config=ElevenLabsConfig(api_key="key-123", voice_id="voice-abc"),
        transport=fake_transport,
    )

    result = provider.submit({"text": "Welcome to the course."})

    assert result.status == "completed"
    assert result.content_type == "audio/mpeg"
    assert captured["url"] == "https://api.elevenlabs.io/v1/text-to-speech/voice-abc"
    assert captured["method"] == "POST"
    assert captured["headers"]["Xi-api-key"] == "key-123"
    assert captured["headers"]["Accept"] == "audio/mpeg"

    polled = provider.poll(result.job_id)
    assert polled.status == "completed"
    assert polled.job_id == result.job_id

    fetched = provider.fetch(result.job_id)
    assert fetched == fake_mp3


def test_submit_fails_fast_on_401_without_retry():
    attempts = {"count": 0}

    def unauthorized_transport(_request, _timeout):
        attempts["count"] += 1
        raise HTTPError(
            url="https://api.elevenlabs.io/v1/text-to-speech/voice-abc",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )

    provider = ElevenLabsNarrationProvider(
        config=ElevenLabsConfig(api_key="bad-key", max_retries=2, retry_backoff_seconds=0),
        transport=unauthorized_transport,
    )

    try:
        provider.submit({"text": "Welcome to the course."})
    except ElevenLabsError as exc:
        assert "401" in str(exc)
    else:
        raise AssertionError("Expected ElevenLabsError")

    assert attempts["count"] == 1  # 4xx must not retry


def test_submit_fails_fast_on_429_rate_limit_without_retry():
    attempts = {"count": 0}
    fake_mp3 = b"ID3fake-audio-bytes"

    def flaky_transport(_request, _timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise HTTPError(
                url="https://api.elevenlabs.io/v1/text-to-speech/voice-abc",
                code=429,
                msg="Too Many Requests",
                hdrs=None,
                fp=None,
            )
        return fake_mp3

    provider = ElevenLabsNarrationProvider(
        config=ElevenLabsConfig(api_key="key-123", max_retries=1, retry_backoff_seconds=0),
        transport=flaky_transport,
    )

    # NOTE: 429 is a 4xx status. Mirroring OpenRouterClient's _send_with_retries exactly,
    # only 5xx and URLError are retried -- a 4xx (including 429) fails fast. This test
    # documents that intentional behavior rather than asserting a retry happens.
    try:
        provider.submit({"text": "Welcome to the course."})
    except ElevenLabsError as exc:
        assert "429" in str(exc)
    else:
        raise AssertionError("Expected ElevenLabsError")
    assert attempts["count"] == 1


def test_submit_retries_5xx_then_succeeds():
    attempts = {"count": 0}
    fake_mp3 = b"ID3fake-audio-bytes"

    def flaky_transport(_request, _timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise HTTPError(
                url="https://api.elevenlabs.io/v1/text-to-speech/voice-abc",
                code=503,
                msg="Service unavailable",
                hdrs=None,
                fp=None,
            )
        return fake_mp3

    provider = ElevenLabsNarrationProvider(
        config=ElevenLabsConfig(api_key="key-123", max_retries=1, retry_backoff_seconds=0),
        transport=flaky_transport,
    )

    result = provider.submit({"text": "Welcome to the course."})

    assert attempts["count"] == 2
    assert provider.fetch(result.job_id) == fake_mp3


def test_submit_retries_transient_url_errors():
    attempts = {"count": 0}
    fake_mp3 = b"ID3fake-audio-bytes"

    def flaky_transport(_request, _timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise URLError("temporary network problem")
        return fake_mp3

    provider = ElevenLabsNarrationProvider(
        config=ElevenLabsConfig(api_key="key-123", max_retries=1, retry_backoff_seconds=0),
        transport=flaky_transport,
    )

    result = provider.submit({"text": "Welcome to the course."})

    assert attempts["count"] == 2
    assert provider.fetch(result.job_id) == fake_mp3


def test_submit_requires_nonempty_text():
    provider = ElevenLabsNarrationProvider(
        config=ElevenLabsConfig(api_key="key-123"),
        transport=lambda request, timeout: b"unused",
    )

    try:
        provider.submit({"text": "   "})
    except ElevenLabsError as exc:
        assert "missing text" in str(exc)
    else:
        raise AssertionError("Expected ElevenLabsError")
