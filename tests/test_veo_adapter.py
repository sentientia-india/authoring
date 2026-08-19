from __future__ import annotations

import base64

from urllib.error import HTTPError, URLError

from course_mcp_server.video_providers import VeoConfig, VeoClipProvider
from course_mcp_server.video_providers.veo import VeoError


def _config(**overrides):
    defaults = dict(
        api_key="key-123",
        model="veo-3.0-generate-001",
        max_retries=1,
        retry_backoff_seconds=0,
    )
    defaults.update(overrides)
    return VeoConfig(**defaults)


def test_config_defaults(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY_FILE", raising=False)

    config = VeoConfig.from_env()

    assert config.api_key is None
    assert config.enabled is False


def test_not_configured_raises_before_any_transport_call():
    def fail_json(_request, _timeout):
        raise AssertionError("json transport should not be called when not configured")

    def fail_bytes(_request, _timeout):
        raise AssertionError("bytes transport should not be called when not configured")

    provider = VeoClipProvider(
        config=VeoConfig(api_key=None),
        json_transport=fail_json,
        bytes_transport=fail_bytes,
    )

    try:
        provider.submit({"prompt": "A drone shot of a warehouse safety briefing."})
    except VeoError as exc:
        assert "not configured" in str(exc)
    else:
        raise AssertionError("Expected VeoError")


def test_submit_does_not_block_or_call_full_generation():
    """submit() must only hit the fast start-generation (predictLongRunning) endpoint and
    return immediately with status="processing" -- it must never touch a "wait for full
    generation" transport.
    """

    def hanging_full_generation_transport(_request, _timeout):
        raise AssertionError(
            "submit() must not perform a call that waits for full generation to finish"
        )

    calls = {"count": 0}

    def start_generation_transport(request, _timeout):
        calls["count"] += 1
        assert request.get_method() == "POST"
        assert ":predictLongRunning" in request.full_url
        return {"name": "operations/op_123", "done": False}

    provider = VeoClipProvider(
        config=_config(),
        json_transport=start_generation_transport,
        bytes_transport=hanging_full_generation_transport,
    )

    result = provider.submit({"prompt": "A drone shot of a warehouse safety briefing."})

    assert result.status == "processing"
    assert result.job_id == "operations/op_123"
    assert calls["count"] == 1


def test_poll_transitions_from_processing_to_completed_without_real_sleep():
    """Simulates Veo taking a few polls to finish using a call counter -- no time.sleep
    anywhere in this test, so it stays fast and deterministic.
    """
    poll_calls = {"count": 0}

    def json_transport(request, _timeout):
        if ":predictLongRunning" in request.full_url:
            return {"name": "operations/op_456", "done": False}
        assert "/v1beta/operations/op_456" in request.full_url
        poll_calls["count"] += 1
        if poll_calls["count"] < 3:
            return {"name": "operations/op_456", "done": False}
        return {
            "name": "operations/op_456",
            "done": True,
            "response": {
                "generateVideoResponse": {
                    "generatedSamples": [
                        {"video": {"uri": "https://generativelanguage.googleapis.com/v1beta/files/abc"}}
                    ]
                }
            },
        }

    provider = VeoClipProvider(config=_config(), json_transport=json_transport)
    submitted = provider.submit({"prompt": "A warehouse safety scene."})

    first = provider.poll(submitted.job_id)
    assert first.status == "processing"
    second = provider.poll(submitted.job_id)
    assert second.status == "processing"
    third = provider.poll(submitted.job_id)
    assert third.status == "completed"
    assert third.metadata["video_uri"] == "https://generativelanguage.googleapis.com/v1beta/files/abc"

    assert poll_calls["count"] == 3


def test_poll_reports_failed_status_when_error_populated():
    def json_transport(request, _timeout):
        if ":predictLongRunning" in request.full_url:
            return {"name": "operations/op_err", "done": False}
        return {"name": "operations/op_err", "done": True, "error": {"message": "generation blocked"}}

    provider = VeoClipProvider(config=_config(), json_transport=json_transport)
    submitted = provider.submit({"prompt": "A warehouse safety scene."})

    polled = provider.poll(submitted.job_id)
    assert polled.status == "failed"


def test_poll_treats_done_true_with_no_response_or_error_as_failed():
    """done: true alone doesn't mean success -- must check response/error are populated."""

    def json_transport(request, _timeout):
        if ":predictLongRunning" in request.full_url:
            return {"name": "operations/op_ambiguous", "done": False}
        return {"name": "operations/op_ambiguous", "done": True}

    provider = VeoClipProvider(config=_config(), json_transport=json_transport)
    submitted = provider.submit({"prompt": "A warehouse safety scene."})

    polled = provider.poll(submitted.job_id)
    assert polled.status == "failed"


def test_fetch_raises_if_job_still_processing():
    def json_transport(request, _timeout):
        if ":predictLongRunning" in request.full_url:
            return {"name": "operations/op_789", "done": False}
        return {"name": "operations/op_789", "done": False}

    provider = VeoClipProvider(config=_config(), json_transport=json_transport)
    submitted = provider.submit({"prompt": "A warehouse safety scene."})
    provider.poll(submitted.job_id)

    try:
        provider.fetch(submitted.job_id)
    except VeoError as exc:
        assert "not complete yet" in str(exc)
    else:
        raise AssertionError("Expected VeoError")


def test_fetch_raises_if_job_failed():
    def json_transport(request, _timeout):
        if ":predictLongRunning" in request.full_url:
            return {"name": "operations/op_fail", "done": False}
        return {"name": "operations/op_fail", "done": True, "error": {"message": "boom"}}

    provider = VeoClipProvider(config=_config(), json_transport=json_transport)
    submitted = provider.submit({"prompt": "A warehouse safety scene."})
    provider.poll(submitted.job_id)

    try:
        provider.fetch(submitted.job_id)
    except VeoError as exc:
        assert "not complete yet" in str(exc)
    else:
        raise AssertionError("Expected VeoError")


def test_fetch_succeeds_via_authenticated_uri_download_only_after_poll_reports_completed():
    fake_mp4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32
    captured = {}

    def json_transport(request, _timeout):
        if ":predictLongRunning" in request.full_url:
            return {"name": "operations/op_ok", "done": False}
        return {
            "name": "operations/op_ok",
            "done": True,
            "response": {
                "generateVideoResponse": {
                    "generatedSamples": [
                        {"video": {"uri": "https://generativelanguage.googleapis.com/v1beta/files/vid_ok"}}
                    ]
                }
            },
        }

    def bytes_transport(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = {k.lower(): v for k, v in request.headers.items()}
        return fake_mp4

    provider = VeoClipProvider(
        config=_config(), json_transport=json_transport, bytes_transport=bytes_transport
    )
    submitted = provider.submit({"prompt": "A warehouse safety scene."})
    polled = provider.poll(submitted.job_id)
    assert polled.status == "completed"

    fetched = provider.fetch(submitted.job_id)

    assert fetched == fake_mp4
    assert captured["url"] == "https://generativelanguage.googleapis.com/v1beta/files/vid_ok"
    # Unlike HeyGen's assumed unauthenticated pre-signed URL, the Files API download must
    # carry the API key -- proving this adapter doesn't copy HeyGen's no-auth assumption.
    assert captured["headers"]["x-goog-api-key"] == "key-123"


def test_fetch_succeeds_with_inline_base64_bytes_without_any_download_call():
    fake_mp4 = b"inline-mp4-bytes-payload"
    encoded = base64.b64encode(fake_mp4).decode("ascii")

    def json_transport(request, _timeout):
        if ":predictLongRunning" in request.full_url:
            return {"name": "operations/op_inline", "done": False}
        return {
            "name": "operations/op_inline",
            "done": True,
            "response": {
                "generateVideoResponse": {
                    "generatedSamples": [{"video": {"bytesBase64Encoded": encoded, "mimeType": "video/mp4"}}]
                }
            },
        }

    def hanging_bytes_transport(_request, _timeout):
        raise AssertionError("fetch() must not download when inline bytes were already provided")

    provider = VeoClipProvider(
        config=_config(), json_transport=json_transport, bytes_transport=hanging_bytes_transport
    )
    submitted = provider.submit({"prompt": "A warehouse safety scene."})
    provider.poll(submitted.job_id)

    fetched = provider.fetch(submitted.job_id)
    assert fetched == fake_mp4


def test_submit_fails_fast_on_401_without_retry():
    attempts = {"count": 0}

    def unauthorized_transport(_request, _timeout):
        attempts["count"] += 1
        raise HTTPError(
            url="https://generativelanguage.googleapis.com/v1beta/models/veo-3.0-generate-001:predictLongRunning",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )

    provider = VeoClipProvider(config=_config(api_key="bad-key"), json_transport=unauthorized_transport)

    try:
        provider.submit({"prompt": "A warehouse safety scene."})
    except VeoError as exc:
        assert "401" in str(exc)
    else:
        raise AssertionError("Expected VeoError")

    assert attempts["count"] == 1  # 4xx must not retry


def test_submit_retries_5xx_then_succeeds():
    attempts = {"count": 0}

    def flaky_transport(_request, _timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise HTTPError(
                url="https://generativelanguage.googleapis.com/v1beta/models/veo-3.0-generate-001:predictLongRunning",
                code=503,
                msg="Service unavailable",
                hdrs=None,
                fp=None,
            )
        return {"name": "operations/op_retry", "done": False}

    provider = VeoClipProvider(config=_config(), json_transport=flaky_transport)

    result = provider.submit({"prompt": "A warehouse safety scene."})

    assert attempts["count"] == 2
    assert result.job_id == "operations/op_retry"


def test_submit_retries_transient_url_errors():
    attempts = {"count": 0}

    def flaky_transport(_request, _timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise URLError("temporary network problem")
        return {"name": "operations/op_retry2", "done": False}

    provider = VeoClipProvider(config=_config(), json_transport=flaky_transport)

    result = provider.submit({"prompt": "A warehouse safety scene."})

    assert attempts["count"] == 2
    assert result.job_id == "operations/op_retry2"


def test_fetch_fails_fast_on_401_without_retry():
    """fetch()'s clip download uses a SEPARATE retry helper (_send_bytes_with_retries) from
    submit()/poll()'s _send_json_with_retries -- mirroring heygen.py's own test coverage gap
    that was closed for the JSON path first and the bytes path only later, this and the next
    two tests independently prove the bytes-download retry/fail-fast logic actually works for
    Veo from the start, not just that the structurally-similar JSON path does.
    """
    attempts = {"count": 0}

    def json_transport(request, _timeout):
        if ":predictLongRunning" in request.full_url:
            return {"name": "operations/op_dl", "done": False}
        return {
            "name": "operations/op_dl",
            "done": True,
            "response": {
                "generateVideoResponse": {
                    "generatedSamples": [{"video": {"uri": "https://generativelanguage.googleapis.com/v1beta/files/vid_dl"}}]
                }
            },
        }

    def unauthorized_bytes_transport(_request, _timeout):
        attempts["count"] += 1
        raise HTTPError(
            url="https://generativelanguage.googleapis.com/v1beta/files/vid_dl",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )

    provider = VeoClipProvider(
        config=_config(), json_transport=json_transport, bytes_transport=unauthorized_bytes_transport
    )
    submitted = provider.submit({"prompt": "A warehouse safety scene."})
    provider.poll(submitted.job_id)

    try:
        provider.fetch(submitted.job_id)
    except VeoError as exc:
        assert "401" in str(exc)
    else:
        raise AssertionError("Expected VeoError")
    assert attempts["count"] == 1  # 4xx must not retry


def test_fetch_retries_5xx_download_then_succeeds():
    fake_mp4 = b"\x00\x00\x00\x18ftypmp42fake-bytes"
    attempts = {"count": 0}

    def json_transport(request, _timeout):
        if ":predictLongRunning" in request.full_url:
            return {"name": "operations/op_dl2", "done": False}
        return {
            "name": "operations/op_dl2",
            "done": True,
            "response": {
                "generateVideoResponse": {
                    "generatedSamples": [{"video": {"uri": "https://generativelanguage.googleapis.com/v1beta/files/vid_dl2"}}]
                }
            },
        }

    def flaky_bytes_transport(_request, _timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise HTTPError(
                url="https://generativelanguage.googleapis.com/v1beta/files/vid_dl2",
                code=503,
                msg="Unavailable",
                hdrs=None,
                fp=None,
            )
        return fake_mp4

    provider = VeoClipProvider(
        config=_config(), json_transport=json_transport, bytes_transport=flaky_bytes_transport
    )
    submitted = provider.submit({"prompt": "A warehouse safety scene."})
    provider.poll(submitted.job_id)

    fetched = provider.fetch(submitted.job_id)

    assert fetched == fake_mp4
    assert attempts["count"] == 2


def test_fetch_retries_transient_download_url_errors():
    fake_mp4 = b"retry-url-error-bytes"
    attempts = {"count": 0}

    def json_transport(request, _timeout):
        if ":predictLongRunning" in request.full_url:
            return {"name": "operations/op_dl3", "done": False}
        return {
            "name": "operations/op_dl3",
            "done": True,
            "response": {
                "generateVideoResponse": {
                    "generatedSamples": [{"video": {"uri": "https://generativelanguage.googleapis.com/v1beta/files/vid_dl3"}}]
                }
            },
        }

    def flaky_bytes_transport(_request, _timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise URLError("temporary network problem")
        return fake_mp4

    provider = VeoClipProvider(
        config=_config(), json_transport=json_transport, bytes_transport=flaky_bytes_transport
    )
    submitted = provider.submit({"prompt": "A warehouse safety scene."})
    provider.poll(submitted.job_id)

    fetched = provider.fetch(submitted.job_id)

    assert fetched == fake_mp4
    assert attempts["count"] == 2


def test_submit_requires_prompt():
    provider = VeoClipProvider(
        config=_config(),
        json_transport=lambda request, timeout: {"name": "operations/unused", "done": False},
    )

    try:
        provider.submit({"prompt": "   "})
    except VeoError as exc:
        assert "prompt" in str(exc)
    else:
        raise AssertionError("Expected VeoError")


def test_poll_and_fetch_work_on_a_completely_fresh_provider_instance():
    """The real bug this test exists to catch (see heygen.py's own equivalent test and the
    orchestrator's fix note): a genuine two-tool-call MCP flow submits a job in one call and
    polls/fetches it in a LATER, separate call -- each call constructs its own fresh
    VeoClipProvider(), so the second call's provider has an empty self._jobs and has never
    locally seen this operation name. This proves that poll()/fetch() still work correctly
    using no shared state between the "submit" and "poll/fetch" provider objects at all, only
    the plain operation-name string, exactly as a real cross-call MCP tool boundary would.
    """
    fake_mp4 = b"cross-instance-fake-mp4-bytes"

    def submit_transport(request, _timeout):
        assert ":predictLongRunning" in request.full_url
        return {"name": "operations/op_cross_instance", "done": False}

    submitting_provider = VeoClipProvider(config=_config(), json_transport=submit_transport)
    submitted = submitting_provider.submit({"prompt": "A warehouse safety scene."})
    assert submitted.status == "processing"

    # A brand new provider instance, sharing nothing with submitting_provider except the
    # plain operation-name string -- this is the actual shape of two separate MCP tool calls.
    poll_calls = {"count": 0}

    def status_only_transport(request, _timeout):
        assert "/v1beta/operations/op_cross_instance" in request.full_url
        poll_calls["count"] += 1
        if poll_calls["count"] == 1:
            return {"name": "operations/op_cross_instance", "done": False}
        return {
            "name": "operations/op_cross_instance",
            "done": True,
            "response": {
                "generateVideoResponse": {
                    "generatedSamples": [
                        {
                            "video": {
                                "uri": "https://generativelanguage.googleapis.com/v1beta/files/op_cross_instance"
                            }
                        }
                    ]
                }
            },
        }

    def bytes_transport(request, _timeout):
        assert (
            request.full_url
            == "https://generativelanguage.googleapis.com/v1beta/files/op_cross_instance"
        )
        return fake_mp4

    fresh_provider = VeoClipProvider(
        config=_config(), json_transport=status_only_transport, bytes_transport=bytes_transport
    )

    first_poll = fresh_provider.poll(submitted.job_id)
    assert first_poll.status == "processing"

    second_poll = fresh_provider.poll(submitted.job_id)
    assert second_poll.status == "completed"

    fetched = fresh_provider.fetch(submitted.job_id)
    assert fetched == fake_mp4

    # And fetch() alone, on a THIRD fresh instance that never even called poll() itself, must
    # also self-heal via its own internal poll() rather than requiring the caller to have
    # polled on that exact instance first.
    third_provider = VeoClipProvider(
        config=_config(),
        json_transport=lambda request, timeout: {
            "name": "operations/op_cross_instance",
            "done": True,
            "response": {
                "generateVideoResponse": {
                    "generatedSamples": [
                        {
                            "video": {
                                "uri": "https://generativelanguage.googleapis.com/v1beta/files/op_cross_instance"
                            }
                        }
                    ]
                }
            },
        },
        bytes_transport=bytes_transport,
    )
    assert third_provider.fetch(submitted.job_id) == fake_mp4


def test_extract_video_ref_fallback_chain_and_error_paths():
    """Every other test in this file happens to exercise ONLY the primary response shape
    (generateVideoResponse.generatedSamples) -- _extract_video_ref has a 4-key fallback chain
    plus two distinct error paths that were otherwise completely unverified. Proves each
    candidate key and both malformed-input error paths genuinely work, not just exist in
    source unexercised.
    """
    # Top-level "generatedSamples" (no generateVideoResponse wrapper).
    uri, inline, mime = VeoClipProvider._extract_video_ref(
        {"generatedSamples": [{"video": {"uri": "https://example.com/a.mp4", "mimeType": "video/mp4"}}]}
    )
    assert uri == "https://example.com/a.mp4" and inline is None

    # "generatedVideos" fallback.
    uri, inline, mime = VeoClipProvider._extract_video_ref(
        {"generatedVideos": [{"video": {"uri": "https://example.com/b.mp4"}}]}
    )
    assert uri == "https://example.com/b.mp4"

    # "videos" fallback (least-preferred candidate).
    uri, inline, mime = VeoClipProvider._extract_video_ref({"videos": [{"video": {"uri": "https://example.com/c.mp4"}}]})
    assert uri == "https://example.com/c.mp4"

    # A sample with no nested "video" key at all -- the sample dict itself IS the video ref.
    uri, inline, mime = VeoClipProvider._extract_video_ref(
        {"generatedSamples": [{"uri": "https://example.com/d.mp4", "mimeType": "video/webm"}]}
    )
    assert uri == "https://example.com/d.mp4" and mime == "video/webm"

    # No known sample key at all -> clean VeoError, not a KeyError/crash.
    try:
        VeoClipProvider._extract_video_ref({"somethingElseEntirely": []})
    except VeoError:
        pass
    else:
        raise AssertionError("expected VeoError for a response with no known sample key")

    # A sample present but with neither uri nor inline bytes -> clean VeoError.
    try:
        VeoClipProvider._extract_video_ref({"generatedSamples": [{"video": {"mimeType": "video/mp4"}}]})
    except VeoError:
        pass
    else:
        raise AssertionError("expected VeoError for a sample with neither uri nor inline bytes")
