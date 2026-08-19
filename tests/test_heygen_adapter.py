from __future__ import annotations

from urllib.error import HTTPError, URLError

from course_mcp_server.video_providers import HeyGenConfig, HeyGenPresenterProvider
from course_mcp_server.video_providers.heygen import HeyGenError


def _config(**overrides):
    defaults = dict(
        api_key="key-123",
        avatar_id="avatar-abc",
        voice_id="voice-xyz",
        max_retries=1,
        retry_backoff_seconds=0,
    )
    defaults.update(overrides)
    return HeyGenConfig(**defaults)


def test_config_defaults(monkeypatch):
    monkeypatch.delenv("HEYGEN_API_KEY", raising=False)
    monkeypatch.delenv("HEYGEN_AVATAR_ID", raising=False)

    config = HeyGenConfig.from_env()

    assert config.api_key is None
    assert config.avatar_id is None
    assert config.enabled is False


def test_not_configured_raises_before_any_transport_call():
    def fail_json(_request, _timeout):
        raise AssertionError("json transport should not be called when not configured")

    def fail_bytes(_request, _timeout):
        raise AssertionError("bytes transport should not be called when not configured")

    provider = HeyGenPresenterProvider(
        config=HeyGenConfig(api_key=None),
        json_transport=fail_json,
        bytes_transport=fail_bytes,
    )

    try:
        provider.submit({"script": "Welcome to the course."})
    except HeyGenError as exc:
        assert "not configured" in str(exc)
    else:
        raise AssertionError("Expected HeyGenError")


def test_submit_does_not_block_or_call_full_generation():
    """submit() must only hit the fast start-generation endpoint and return immediately
    with status="processing" -- it must never touch a "wait for full generation" transport.
    """

    def hanging_full_generation_transport(_request, _timeout):
        raise AssertionError(
            "submit() must not perform a call that waits for full generation to finish"
        )

    calls = {"count": 0}

    def start_generation_transport(request, _timeout):
        calls["count"] += 1
        assert request.get_method() == "POST"
        assert "/v2/video/generate" in request.full_url
        return {"data": {"video_id": "vid_123"}}

    provider = HeyGenPresenterProvider(
        config=_config(),
        json_transport=start_generation_transport,
        bytes_transport=hanging_full_generation_transport,
    )

    result = provider.submit({"script": "Welcome to the course."})

    assert result.status == "processing"
    assert result.job_id == "vid_123"
    assert calls["count"] == 1


def test_poll_transitions_from_processing_to_completed_without_real_sleep():
    """Simulates HeyGen taking a few polls to finish using a call counter -- no time.sleep
    anywhere in this test, so it stays fast and deterministic.
    """
    poll_calls = {"count": 0}

    def json_transport(request, _timeout):
        if "/v2/video/generate" in request.full_url:
            return {"data": {"video_id": "vid_456"}}
        assert "/v1/video_status.get" in request.full_url
        assert "video_id=vid_456" in request.full_url
        poll_calls["count"] += 1
        if poll_calls["count"] < 3:
            return {"data": {"status": "processing"}}
        return {"data": {"status": "completed", "video_url": "https://cdn.heygen.com/vid_456.mp4"}}

    provider = HeyGenPresenterProvider(config=_config(), json_transport=json_transport)
    submitted = provider.submit({"script": "Welcome to the course."})

    first = provider.poll(submitted.job_id)
    assert first.status == "processing"
    second = provider.poll(submitted.job_id)
    assert second.status == "processing"
    third = provider.poll(submitted.job_id)
    assert third.status == "completed"
    assert third.metadata["video_url"] == "https://cdn.heygen.com/vid_456.mp4"

    assert poll_calls["count"] == 3


def test_poll_reports_failed_status():
    def json_transport(request, _timeout):
        if "/v2/video/generate" in request.full_url:
            return {"data": {"video_id": "vid_err"}}
        return {"data": {"status": "failed", "error": {"message": "avatar unavailable"}}}

    provider = HeyGenPresenterProvider(config=_config(), json_transport=json_transport)
    submitted = provider.submit({"script": "Welcome to the course."})

    polled = provider.poll(submitted.job_id)
    assert polled.status == "failed"


def test_fetch_raises_if_job_still_processing():
    def json_transport(request, _timeout):
        if "/v2/video/generate" in request.full_url:
            return {"data": {"video_id": "vid_789"}}
        return {"data": {"status": "processing"}}

    provider = HeyGenPresenterProvider(config=_config(), json_transport=json_transport)
    submitted = provider.submit({"script": "Welcome to the course."})
    provider.poll(submitted.job_id)

    try:
        provider.fetch(submitted.job_id)
    except HeyGenError as exc:
        assert "not complete yet" in str(exc)
    else:
        raise AssertionError("Expected HeyGenError")


def test_fetch_raises_if_job_failed():
    def json_transport(request, _timeout):
        if "/v2/video/generate" in request.full_url:
            return {"data": {"video_id": "vid_fail"}}
        return {"data": {"status": "failed", "error": {"message": "boom"}}}

    provider = HeyGenPresenterProvider(config=_config(), json_transport=json_transport)
    submitted = provider.submit({"script": "Welcome to the course."})
    provider.poll(submitted.job_id)

    try:
        provider.fetch(submitted.job_id)
    except HeyGenError as exc:
        assert "not complete yet" in str(exc)
    else:
        raise AssertionError("Expected HeyGenError")


def test_fetch_succeeds_only_after_poll_reports_completed():
    fake_mp4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32
    captured = {}

    def json_transport(request, _timeout):
        if "/v2/video/generate" in request.full_url:
            return {"data": {"video_id": "vid_ok"}}
        return {"data": {"status": "completed", "video_url": "https://cdn.heygen.com/vid_ok.mp4"}}

    def bytes_transport(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return fake_mp4

    provider = HeyGenPresenterProvider(
        config=_config(), json_transport=json_transport, bytes_transport=bytes_transport
    )
    submitted = provider.submit({"script": "Welcome to the course."})
    polled = provider.poll(submitted.job_id)
    assert polled.status == "completed"

    fetched = provider.fetch(submitted.job_id)

    assert fetched == fake_mp4
    assert captured["url"] == "https://cdn.heygen.com/vid_ok.mp4"


def test_submit_fails_fast_on_401_without_retry():
    attempts = {"count": 0}

    def unauthorized_transport(_request, _timeout):
        attempts["count"] += 1
        raise HTTPError(
            url="https://api.heygen.com/v2/video/generate",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )

    provider = HeyGenPresenterProvider(
        config=_config(api_key="bad-key"), json_transport=unauthorized_transport
    )

    try:
        provider.submit({"script": "Welcome to the course."})
    except HeyGenError as exc:
        assert "401" in str(exc)
    else:
        raise AssertionError("Expected HeyGenError")

    assert attempts["count"] == 1  # 4xx must not retry


def test_submit_retries_5xx_then_succeeds():
    attempts = {"count": 0}

    def flaky_transport(_request, _timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise HTTPError(
                url="https://api.heygen.com/v2/video/generate",
                code=503,
                msg="Service unavailable",
                hdrs=None,
                fp=None,
            )
        return {"data": {"video_id": "vid_retry"}}

    provider = HeyGenPresenterProvider(config=_config(), json_transport=flaky_transport)

    result = provider.submit({"script": "Welcome to the course."})

    assert attempts["count"] == 2
    assert result.job_id == "vid_retry"


def test_submit_retries_transient_url_errors():
    attempts = {"count": 0}

    def flaky_transport(_request, _timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise URLError("temporary network problem")
        return {"data": {"video_id": "vid_retry2"}}

    provider = HeyGenPresenterProvider(config=_config(), json_transport=flaky_transport)

    result = provider.submit({"script": "Welcome to the course."})

    assert attempts["count"] == 2
    assert result.job_id == "vid_retry2"


def test_fetch_fails_fast_on_401_without_retry():
    """fetch()'s video download uses a SEPARATE retry helper (_send_bytes_with_retries) from
    submit()/poll()'s _send_json_with_retries -- this was not exercised by any existing test
    (every prior fetch test's bytes_transport succeeds on the first call), so this and the
    next two tests independently prove the bytes-download retry/fail-fast logic actually
    works, not just that the structurally-similar JSON path does.
    """
    attempts = {"count": 0}

    def json_transport(request, _timeout):
        if "/v2/video/generate" in request.full_url:
            return {"data": {"video_id": "vid_dl"}}
        return {"data": {"status": "completed", "video_url": "https://cdn.heygen.com/vid_dl.mp4"}}

    def unauthorized_bytes_transport(_request, _timeout):
        attempts["count"] += 1
        raise HTTPError(
            url="https://cdn.heygen.com/vid_dl.mp4", code=401, msg="Unauthorized", hdrs=None, fp=None
        )

    provider = HeyGenPresenterProvider(
        config=_config(), json_transport=json_transport, bytes_transport=unauthorized_bytes_transport
    )
    submitted = provider.submit({"script": "Welcome to the course."})
    provider.poll(submitted.job_id)

    try:
        provider.fetch(submitted.job_id)
    except HeyGenError as exc:
        assert "401" in str(exc)
    else:
        raise AssertionError("Expected HeyGenError")
    assert attempts["count"] == 1  # 4xx must not retry


def test_fetch_retries_5xx_download_then_succeeds():
    fake_mp4 = b"\x00\x00\x00\x18ftypmp42fake-bytes"
    attempts = {"count": 0}

    def json_transport(request, _timeout):
        if "/v2/video/generate" in request.full_url:
            return {"data": {"video_id": "vid_dl2"}}
        return {"data": {"status": "completed", "video_url": "https://cdn.heygen.com/vid_dl2.mp4"}}

    def flaky_bytes_transport(_request, _timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise HTTPError(
                url="https://cdn.heygen.com/vid_dl2.mp4", code=503, msg="Unavailable", hdrs=None, fp=None
            )
        return fake_mp4

    provider = HeyGenPresenterProvider(
        config=_config(), json_transport=json_transport, bytes_transport=flaky_bytes_transport
    )
    submitted = provider.submit({"script": "Welcome to the course."})
    provider.poll(submitted.job_id)

    fetched = provider.fetch(submitted.job_id)

    assert fetched == fake_mp4
    assert attempts["count"] == 2


def test_fetch_retries_transient_download_url_errors():
    fake_mp4 = b"retry-url-error-bytes"
    attempts = {"count": 0}

    def json_transport(request, _timeout):
        if "/v2/video/generate" in request.full_url:
            return {"data": {"video_id": "vid_dl3"}}
        return {"data": {"status": "completed", "video_url": "https://cdn.heygen.com/vid_dl3.mp4"}}

    def flaky_bytes_transport(_request, _timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise URLError("temporary network problem")
        return fake_mp4

    provider = HeyGenPresenterProvider(
        config=_config(), json_transport=json_transport, bytes_transport=flaky_bytes_transport
    )
    submitted = provider.submit({"script": "Welcome to the course."})
    provider.poll(submitted.job_id)

    fetched = provider.fetch(submitted.job_id)

    assert fetched == fake_mp4
    assert attempts["count"] == 2


def test_submit_requires_script_and_avatar_id():
    provider = HeyGenPresenterProvider(
        config=_config(avatar_id=None),
        json_transport=lambda request, timeout: {"data": {"video_id": "unused"}},
    )

    try:
        provider.submit({"script": "Welcome."})
    except HeyGenError as exc:
        assert "avatar_id" in str(exc)
    else:
        raise AssertionError("Expected HeyGenError")

    provider2 = HeyGenPresenterProvider(
        config=_config(),
        json_transport=lambda request, timeout: {"data": {"video_id": "unused"}},
    )
    try:
        provider2.submit({"script": "   "})
    except HeyGenError as exc:
        assert "script" in str(exc)
    else:
        raise AssertionError("Expected HeyGenError")


def test_poll_and_fetch_work_on_a_completely_fresh_provider_instance():
    """The real bug this test exists to catch: a genuine two-tool-call MCP flow submits a
    job in one call and polls/fetches it in a LATER, separate call -- each call constructs
    its own fresh HeyGenPresenterProvider() (the same per-call-fresh-instance pattern
    generate_narration_audio already uses for ElevenLabsNarrationProvider), so the second
    call's provider has an empty self._jobs and has never locally seen this job_id. Before
    the orchestrator's fix, poll()/fetch() raised "Unknown HeyGen job id" here even though
    the job is genuinely progressing/complete on HeyGen's side -- this proves that no longer
    happens, using no shared state between the "submit" and "poll/fetch" provider objects at
    all, only the plain job_id string, exactly as a real cross-call MCP tool boundary would.
    """
    fake_mp4 = b"cross-instance-fake-mp4-bytes"

    def submit_transport(request, _timeout):
        assert "/v2/video/generate" in request.full_url
        return {"data": {"video_id": "vid_cross_instance"}}

    submitting_provider = HeyGenPresenterProvider(config=_config(), json_transport=submit_transport)
    submitted = submitting_provider.submit({"script": "Welcome to the course."})
    assert submitted.status == "processing"

    # A brand new provider instance, sharing nothing with submitting_provider except the
    # plain job_id string -- this is the actual shape of two separate MCP tool calls.
    poll_calls = {"count": 0}

    def status_only_transport(request, _timeout):
        assert "/v1/video_status.get" in request.full_url
        assert "video_id=vid_cross_instance" in request.full_url
        poll_calls["count"] += 1
        if poll_calls["count"] == 1:
            return {"data": {"status": "processing"}}
        return {"data": {"status": "completed", "video_url": "https://cdn.heygen.com/vid_cross_instance.mp4"}}

    def bytes_transport(request, _timeout):
        assert request.full_url == "https://cdn.heygen.com/vid_cross_instance.mp4"
        return fake_mp4

    fresh_provider = HeyGenPresenterProvider(
        config=_config(), json_transport=status_only_transport, bytes_transport=bytes_transport
    )

    first_poll = fresh_provider.poll(submitted.job_id)
    assert first_poll.status == "processing"

    second_poll = fresh_provider.poll(submitted.job_id)
    assert second_poll.status == "completed"

    fetched = fresh_provider.fetch(submitted.job_id)
    assert fetched == fake_mp4

    # And fetch() alone, on a THIRD fresh instance that never even called poll() itself,
    # must also self-heal via its own internal poll() rather than requiring the caller to
    # have polled on that exact instance first.
    third_provider = HeyGenPresenterProvider(
        config=_config(),
        json_transport=lambda request, timeout: {
            "data": {"status": "completed", "video_url": "https://cdn.heygen.com/vid_cross_instance.mp4"}
        },
        bytes_transport=bytes_transport,
    )
    assert third_provider.fetch(submitted.job_id) == fake_mp4
