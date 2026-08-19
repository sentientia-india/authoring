from __future__ import annotations

from course_mcp_server import tools
from course_mcp_server.security import RequestContext
from course_mcp_server.tools import (
    create_course_project,
    generate_assessment_bank,
    generate_course_blueprint,
    generate_lesson_pack,
    generate_narration_audio,
    ingest_course_source,
    propose_course_plan,
    save_course_discovery_answer,
    start_course_discovery,
)
from course_mcp_server.video_providers import ElevenLabsConfig, ElevenLabsNarrationProvider
from course_mcp_server.video_providers.elevenlabs import ElevenLabsError


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
    generate_lesson_pack({"project_id": project_id, "module_id": "module_1"}, context)
    generate_assessment_bank(
        {"project_id": project_id, "question_count": 4, "question_types": ["mcq", "matching"]},
        context,
    )
    return project_id


def _project_with_video_mode(context: RequestContext, mode: str) -> str:
    project_id = _project_with_content(context)
    start_course_discovery({"project_id": project_id}, context)
    save_course_discovery_answer(
        {"project_id": project_id, "question_id": "course_brief_line", "answer": "Ramp safety basics for new ramp agents"},
        context,
    )
    save_course_discovery_answer({"project_id": project_id, "question_id": "source_mode", "answer": "topic_only"}, context)
    save_course_discovery_answer({"project_id": project_id, "question_id": "duration_preset", "answer": "standard"}, context)
    save_course_discovery_answer({"project_id": project_id, "question_id": "media_plan_mode", "answer": "agent_images"}, context)
    save_course_discovery_answer(
        {"project_id": project_id, "question_id": "video_generation_mode", "answer": mode},
        context,
    )
    save_course_discovery_answer({"project_id": project_id, "question_id": "video_links", "answer": ""}, context)
    plan = propose_course_plan({"project_id": project_id}, context)
    assert plan["ok"] is True
    assert plan["data"]["plan"]["media_plan"]["video_generation_mode"] == mode
    return project_id


def test_generate_narration_audio_success(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    context = _ctx()
    project_id = _project_with_content(context)

    fake_mp3 = b"ID3fake-mp3-bytes-for-testing"

    def fake_transport(request, timeout):
        return fake_mp3

    fake_provider = ElevenLabsNarrationProvider(
        config=ElevenLabsConfig(api_key="test-key"), transport=fake_transport
    )
    monkeypatch.setattr(tools, "ElevenLabsNarrationProvider", lambda: fake_provider)

    result = generate_narration_audio({"project_id": project_id}, context)

    assert result["ok"] is True
    assert result["data"]["status"] == "completed"
    assert result["data"]["scenes"], "expected at least one scene"
    for scene in result["data"]["scenes"]:
        assert scene["status"] == "completed"
        assert scene["object_key"]
        assert scene["object_key"].startswith("tenants/tenant-a/narration_audio/")
        assert scene["size_bytes"] == len(fake_mp3)


def test_generate_narration_audio_not_configured(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY_FILE", raising=False)
    context = _ctx()
    project_id = _project_with_content(context)

    def fail_transport(request, timeout):
        raise AssertionError("transport should not be called when the provider is not configured")

    monkeypatch.setattr(
        tools,
        "ElevenLabsNarrationProvider",
        lambda: ElevenLabsNarrationProvider(config=ElevenLabsConfig(api_key=None), transport=fail_transport),
    )

    result = generate_narration_audio({"project_id": project_id}, context)

    assert result["ok"] is False
    assert result["error"] == "provider_not_configured"


def test_generate_narration_audio_partial_failure_does_not_crash(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    context = _ctx()
    project_id = _project_with_content(context)

    fake_mp3 = b"ID3fake-mp3-bytes"
    calls = {"count": 0}

    def flaky_transport(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            return fake_mp3
        raise Exception("boom")  # noqa: TRY002 - simulate an unexpected per-scene failure

    fake_provider = ElevenLabsNarrationProvider(
        config=ElevenLabsConfig(api_key="test-key", max_retries=0), transport=flaky_transport
    )

    # Wrap submit so any raw exception is normalized into ElevenLabsError, matching what a
    # real transport failure (HTTPError/URLError) would raise -- this proves a single
    # scene's TTS failure surfaces as a per-scene "failed" entry rather than propagating and
    # corrupting the whole tool response.
    real_submit = fake_provider.submit

    def guarded_submit(brief):
        try:
            return real_submit(brief)
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, ElevenLabsError):
                raise
            raise ElevenLabsError(str(exc)) from exc

    fake_provider.submit = guarded_submit  # type: ignore[method-assign]
    monkeypatch.setattr(tools, "ElevenLabsNarrationProvider", lambda: fake_provider)

    result = generate_narration_audio({"project_id": project_id}, context)

    assert result["ok"] is True
    assert result["data"]["status"] == "partial"
    statuses = {scene["status"] for scene in result["data"]["scenes"]}
    assert statuses == {"completed", "failed"}
    failed_scenes = [scene for scene in result["data"]["scenes"] if scene["status"] == "failed"]
    assert all(scene["error"] for scene in failed_scenes)


def test_generate_narration_audio_reports_video_generation_mode_none(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    context = _ctx()
    project_id = _project_with_video_mode(context, "none")

    fake_mp3 = b"ID3fake-mp3-bytes"
    fake_provider = ElevenLabsNarrationProvider(
        config=ElevenLabsConfig(api_key="test-key"), transport=lambda request, timeout: fake_mp3
    )
    monkeypatch.setattr(tools, "ElevenLabsNarrationProvider", lambda: fake_provider)

    result = generate_narration_audio({"project_id": project_id}, context)

    # The tool does not block on video_generation_mode == "none" -- it is the calling
    # agent's own responsibility to decide whether calling this tool makes sense given the
    # discovery answer. The tool only surfaces the signal.
    assert result["ok"] is True
    assert result["data"]["video_generation_mode"] == "none"
    assert "video_generation_mode is 'none'" in result["data"]["note"]
