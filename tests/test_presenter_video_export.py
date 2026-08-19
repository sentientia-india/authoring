from __future__ import annotations

from zipfile import ZipFile

from course_mcp_server import tools
from course_mcp_server.exporters.scorm import MAX_PRESENTER_VIDEO_BYTES
from course_mcp_server.security import RequestContext
from course_mcp_server.tools import (
    build_export_package,
    check_presenter_video_status,
    create_course_project,
    generate_assessment_bank,
    generate_course_blueprint,
    generate_lesson_pack,
    generate_presenter_video,
    ingest_course_source,
)
from course_mcp_server.video_providers import HeyGenConfig, HeyGenPresenterProvider


def _ctx() -> RequestContext:
    return RequestContext(tenant_id="tenant-a", user_id="user-a", token="token", request_id="req1")


def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSE_PROJECT_STORE_PATH", str(tmp_path / "projects.json"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("OBJECT_STORE_LOCAL_ROOT", str(tmp_path / "objects"))
    monkeypatch.delenv("OBJECT_STORE_BUCKET", raising=False)
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


def _fake_heygen_provider(fake_video_bytes: bytes) -> HeyGenPresenterProvider:
    def json_transport(request, _timeout):
        url = request.full_url
        if "video/generate" in url:
            return {"data": {"video_id": "job-1"}}
        return {"data": {"status": "completed", "video_url": "https://cdn.heygen.example/job-1.mp4"}}

    def bytes_transport(_request, _timeout):
        return fake_video_bytes

    return HeyGenPresenterProvider(
        config=HeyGenConfig(api_key="test-key", avatar_id="avatar-1", voice_id="voice-1"),
        json_transport=json_transport,
        bytes_transport=bytes_transport,
    )


def _submit_and_complete_presenter_video(context, project_id, monkeypatch, fake_video_bytes: bytes) -> dict:
    fake_provider = _fake_heygen_provider(fake_video_bytes)
    monkeypatch.setattr(tools, "HeyGenPresenterProvider", lambda: fake_provider)

    submit_result = generate_presenter_video({"project_id": project_id, "script": "Welcome!"}, context)
    assert submit_result["ok"] is True

    status_result = check_presenter_video_status({"project_id": project_id}, context)
    assert status_result["ok"] is True
    assert status_result["data"]["status"] == "completed"
    return status_result["data"]


# ---------------------------------------------------------------------------
# End-to-end: presenter video actually lands in the exported SCORM zip.
# ---------------------------------------------------------------------------


def test_export_with_presenter_video_bundles_real_video_into_zip(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    context = _ctx()
    project_id = _project_with_content(context)

    fake_video = b"\x00\x00\x00\x18ftypmp42fake-presenter-video-bytes-for-testing"
    _submit_and_complete_presenter_video(context, project_id, monkeypatch, fake_video)

    export_result = build_export_package({"project_id": project_id, "export_format": "scorm"}, context)
    assert export_result["ok"] is True
    package_path = export_result["data"]["package_path"]

    with ZipFile(package_path) as package:
        names = set(package.namelist())
        assert "assets/presenter-video.mp4" in names
        assert package.read("assets/presenter-video.mp4") == fake_video

        manifest_text = package.read("imsmanifest.xml").decode("utf-8")
        assert "assets/presenter-video.mp4" in manifest_text

        index_html = package.read("index.html").decode("utf-8")
        assert '<video controls preload="none" src="assets/presenter-video.mp4">' in index_html
        # Must land on the main course landing page, not the interactive-video slideshow.
        interactive_video_html = package.read("interactive-video/index.html").decode("utf-8")
        assert "presenter-video.mp4" not in interactive_video_html


def test_export_without_presenter_video_artifact_is_unaffected(tmp_path, monkeypatch):
    """The common case today: no presenter_video_job artifact at all. Export must proceed
    exactly as before -- no presenter video file, no <video> reference anywhere."""
    _env(tmp_path, monkeypatch)
    context = _ctx()
    project_id = _project_with_content(context)

    export_result = build_export_package({"project_id": project_id, "export_format": "scorm"}, context)
    assert export_result["ok"] is True
    package_path = export_result["data"]["package_path"]

    with ZipFile(package_path) as package:
        names = set(package.namelist())
        assert "assets/presenter-video.mp4" not in names

        index_html = package.read("index.html").decode("utf-8")
        assert "<video" not in index_html
        assert "presenter-video.mp4" not in index_html


def test_export_fails_cleanly_when_presenter_video_exceeds_size_budget(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    context = _ctx()
    project_id = _project_with_content(context)

    fake_video = b"small-fake-bytes"
    _submit_and_complete_presenter_video(context, project_id, monkeypatch, fake_video)

    # Simulate the object store having reported (and having stored) a video whose recorded
    # size_bytes exceeds the budget -- mutate the stored artifact directly rather than
    # constructing an actual 150MB+ blob, which is unnecessary to prove the size gate works.
    from course_mcp_server.project_store import get_project, latest_artifact, save_project

    project = get_project(tenant_id=context.tenant_id, project_id=project_id)
    job_artifact = latest_artifact(project, "presenter_video_job")
    job_artifact["payload"]["size_bytes"] = MAX_PRESENTER_VIDEO_BYTES + 1
    save_project(project)

    def _fail_if_called(_key):
        raise AssertionError("fetch_object_bytes must not be called when the video exceeds the size budget")

    monkeypatch.setattr(tools, "fetch_object_bytes", _fail_if_called, raising=False)
    from course_mcp_server.exporters import scorm as scorm_module

    monkeypatch.setattr(scorm_module, "fetch_object_bytes", _fail_if_called)

    export_result = build_export_package({"project_id": project_id, "export_format": "scorm"}, context)
    assert export_result["ok"] is False
    assert export_result["error"] == "presenter_video_too_large"
