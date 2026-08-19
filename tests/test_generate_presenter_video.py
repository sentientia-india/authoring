from __future__ import annotations

from course_mcp_server import tools
from course_mcp_server.security import RequestContext
from course_mcp_server.tools import (
    check_presenter_video_status,
    create_course_project,
    generate_course_blueprint,
    generate_presenter_video,
    ingest_course_source,
    list_course_artifacts,
)
from course_mcp_server.video_providers import HeyGenConfig, HeyGenPresenterProvider


def _ctx() -> RequestContext:
    return RequestContext(tenant_id="tenant-a", user_id="user-a", token="token", request_id="req1")


def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSE_PROJECT_STORE_PATH", str(tmp_path / "projects.json"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("OBJECT_STORE_LOCAL_ROOT", str(tmp_path / "objects"))
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(exist_ok=True)
    (upload_dir / "source.txt").write_text(
        "Ramp safety source text with procedures, cones, and controls.", encoding="utf-8"
    )
    monkeypatch.setenv("UPLOAD_DIR", str(upload_dir))


def _project_with_content(context: RequestContext) -> str:
    project = create_course_project(
        {"course_title": "Ramp Safety", "audience": "crew", "language": "English"},
        context,
    )
    project_id = project["data"]["project_id"]
    ingest_course_source(
        {"project_id": project_id, "upload_id": "source.txt", "source_type": "raw_text"},
        context,
    )
    generate_course_blueprint({"project_id": project_id, "duration_minutes": 20}, context)
    return project_id


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


def test_generate_presenter_video_success_does_not_block(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    context = _ctx()
    project_id = _project_with_content(context)

    def submit_transport(request, _timeout):
        assert "/v2/video/generate" in request.full_url
        return {"data": {"video_id": "vid_success"}}

    provider = HeyGenPresenterProvider(config=_config(), json_transport=submit_transport)
    monkeypatch.setattr(tools, "HeyGenPresenterProvider", lambda: provider)

    result = generate_presenter_video({"project_id": project_id}, context)

    assert result["ok"] is True
    assert result["data"]["job_id"] == "vid_success"
    assert result["data"]["status"] == "processing"

    project = tools._project_or_raise(context, project_id)
    artifact = tools.latest_artifact(project, "presenter_video_job")
    assert artifact is not None
    assert artifact["payload"]["job_id"] == "vid_success"
    assert artifact["payload"]["status"] == "processing"


def test_generate_presenter_video_not_configured(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    monkeypatch.delenv("HEYGEN_API_KEY", raising=False)
    monkeypatch.delenv("HEYGEN_API_KEY_FILE", raising=False)
    context = _ctx()
    project_id = _project_with_content(context)

    def fail_transport(request, _timeout):
        raise AssertionError("transport should not be called when the provider is not configured")

    monkeypatch.setattr(
        tools,
        "HeyGenPresenterProvider",
        lambda: HeyGenPresenterProvider(config=_config(api_key=None), json_transport=fail_transport),
    )

    result = generate_presenter_video({"project_id": project_id}, context)

    assert result["ok"] is False
    assert result["error"] == "provider_not_configured"


def test_check_presenter_video_status_no_job_fails_clearly(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    context = _ctx()
    project_id = _project_with_content(context)

    result = check_presenter_video_status({"project_id": project_id}, context)

    assert result["ok"] is False
    assert result["error"] == "no_presenter_video_job"


def test_check_presenter_video_status_processing_then_completed(tmp_path, monkeypatch):
    """The real end-to-end two-tool-call flow: generate_presenter_video submits a job and
    returns immediately (no blocking). A SEPARATE, later call constructs a completely fresh
    HeyGenPresenterProvider() (tools.py does this naturally per call, matching
    generate_narration_audio's existing pattern) to poll status. First poll reports
    "processing" with no error. Then the fake transport's internal state advances to
    "completed"; the next check_presenter_video_status call downloads and stores the video,
    returning a real object_key -- and that completed artifact is genuinely retrievable
    afterward via list_course_artifacts, not just present in the triggering call's response.
    """
    _env(tmp_path, monkeypatch)
    context = _ctx()
    project_id = _project_with_content(context)

    fake_mp4 = b"fake-mp4-bytes-for-two-call-flow"
    status_calls = {"count": 0}

    def submit_transport(request, _timeout):
        assert "/v2/video/generate" in request.full_url
        return {"data": {"video_id": "vid_two_call"}}

    def status_transport(request, _timeout):
        assert "/v1/video_status.get" in request.full_url
        assert "video_id=vid_two_call" in request.full_url
        status_calls["count"] += 1
        if status_calls["count"] == 1:
            return {"data": {"status": "processing"}}
        return {"data": {"status": "completed", "video_url": "https://cdn.heygen.com/vid_two_call.mp4"}}

    def bytes_transport(request, _timeout):
        assert request.full_url == "https://cdn.heygen.com/vid_two_call.mp4"
        return fake_mp4

    # --- Call 1: submit, using a fresh provider instance that only knows how to submit. ---
    submitting_provider = HeyGenPresenterProvider(config=_config(), json_transport=submit_transport)
    monkeypatch.setattr(tools, "HeyGenPresenterProvider", lambda: submitting_provider)

    submit_result = generate_presenter_video({"project_id": project_id}, context)
    assert submit_result["ok"] is True
    assert submit_result["data"]["status"] == "processing"
    assert submit_result["data"]["job_id"] == "vid_two_call"

    # --- Call 2: poll while still processing, using a DIFFERENT fresh provider instance that
    # shares no state with submitting_provider -- only the job_id persisted in the project's
    # own "presenter_video_job" artifact bridges the two calls, exactly as a real two-tool-call
    # MCP flow would work. ---
    polling_provider = HeyGenPresenterProvider(
        config=_config(), json_transport=status_transport, bytes_transport=bytes_transport
    )
    monkeypatch.setattr(tools, "HeyGenPresenterProvider", lambda: polling_provider)

    status_result = check_presenter_video_status({"project_id": project_id}, context)
    assert status_result["ok"] is True
    assert status_result["data"]["status"] == "processing"
    assert status_result["data"].get("object_key") is None

    # --- Call 3: poll again, yet another fresh provider instance, after the fake transport's
    # internal state has advanced to "completed". ---
    completing_provider = HeyGenPresenterProvider(
        config=_config(), json_transport=status_transport, bytes_transport=bytes_transport
    )
    monkeypatch.setattr(tools, "HeyGenPresenterProvider", lambda: completing_provider)

    completed_result = check_presenter_video_status({"project_id": project_id}, context)
    assert completed_result["ok"] is True
    assert completed_result["data"]["status"] == "completed"
    object_key = completed_result["data"]["object_key"]
    assert object_key
    assert object_key.startswith("tenants/tenant-a/presenter_video/")
    assert completed_result["data"]["size_bytes"] == len(fake_mp4)

    # Confirm the completed artifact is genuinely retrievable via the real
    # list_course_artifacts tool, not just present in the triggering call's own response.
    artifacts = list_course_artifacts({"project_id": project_id}, context)
    assert artifacts["ok"] is True
    presenter_artifacts = [
        artifact
        for artifact in artifacts["data"]["artifacts"]
        if artifact["artifact_type"] == "presenter_video_job"
    ]
    # One artifact from the initial submit(), one appended on completion.
    assert len(presenter_artifacts) == 2
