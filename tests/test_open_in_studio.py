from __future__ import annotations

import json
from urllib.error import URLError

from course_mcp_server import tools
from course_mcp_server.security import RequestContext
from course_mcp_server.tools import (
    create_course_project,
    generate_assessment_bank,
    generate_course_blueprint,
    generate_interactive_activity,
    generate_lesson_pack,
    ingest_course_source,
    open_in_studio,
)


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
    monkeypatch.setenv("EDITOR_INTERNAL_URL", "http://scorm-editor.internal:8788")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://learn.example.com")


def _exportable_project(context: RequestContext) -> str:
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
    generate_interactive_activity(
        {
            "project_id": project_id,
            "activity_type": "matching",
            "objective": "Match each SOP step to its control.",
        },
        context,
    )
    generate_assessment_bank(
        {"project_id": project_id, "question_count": 4, "question_types": ["mcq", "matching"]},
        context,
    )
    return project_id


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_open_in_studio_success(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    monkeypatch.setenv("EDITOR_API_TOKEN", "test-editor-token")
    monkeypatch.delenv("EDITOR_API_TOKEN_FILE", raising=False)
    context = _ctx()
    project_id = _exportable_project(context)

    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(
            {"session": "sess123abc", "course": {}, "files": [], "version": 1, "open_token": "scoped-open-token"}
        )

    monkeypatch.setattr(tools, "urlopen", fake_urlopen)

    result = open_in_studio({"project_id": project_id}, context)

    assert result["ok"] is True
    assert result["data"]["session"] == "sess123abc"
    assert result["data"]["project_id"] == project_id
    assert (
        result["data"]["editor_url"]
        == "https://learn.example.com/editor/?session=sess123abc&token=scoped-open-token"
    )
    assert result["data"]["package_path"].endswith(".zip")
    assert captured["url"] == "http://scorm-editor.internal:8788/api/import"
    assert captured["headers"]["Authorization"] == "Bearer test-editor-token"
    assert "zip" in captured["body"] and captured["body"]["zip"]


def test_open_in_studio_falls_back_to_standing_token_when_open_token_absent(tmp_path, monkeypatch):
    # Older Course Studio deployments won't return open_token yet -- open_in_studio must
    # fall back to the standing EDITOR_API_TOKEN in the deep link rather than crashing.
    _env(tmp_path, monkeypatch)
    monkeypatch.setenv("EDITOR_API_TOKEN", "test-editor-token")
    monkeypatch.delenv("EDITOR_API_TOKEN_FILE", raising=False)
    context = _ctx()
    project_id = _exportable_project(context)

    def fake_urlopen(request, timeout=None):
        return _FakeResponse({"session": "sess123abc", "course": {}, "files": [], "version": 1})

    monkeypatch.setattr(tools, "urlopen", fake_urlopen)

    result = open_in_studio({"project_id": project_id}, context)

    assert result["ok"] is True
    assert (
        result["data"]["editor_url"]
        == "https://learn.example.com/editor/?session=sess123abc&token=test-editor-token"
    )


def test_open_in_studio_editor_token_not_configured(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    monkeypatch.delenv("EDITOR_API_TOKEN", raising=False)
    monkeypatch.delenv("EDITOR_API_TOKEN_FILE", raising=False)
    context = _ctx()
    project_id = _exportable_project(context)

    def fake_urlopen(request, timeout=None):
        raise AssertionError("urlopen should not be called when the editor token is missing")

    monkeypatch.setattr(tools, "urlopen", fake_urlopen)

    result = open_in_studio({"project_id": project_id}, context)

    assert result["ok"] is False
    assert result["error"] == "editor_not_configured"


def test_open_in_studio_editor_unreachable(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    monkeypatch.setenv("EDITOR_API_TOKEN", "test-editor-token")
    monkeypatch.delenv("EDITOR_API_TOKEN_FILE", raising=False)
    context = _ctx()
    project_id = _exportable_project(context)

    def fake_urlopen(request, timeout=None):
        raise URLError("Connection refused")

    monkeypatch.setattr(tools, "urlopen", fake_urlopen)

    result = open_in_studio({"project_id": project_id}, context)

    assert result["ok"] is False
    assert result["error"] == "editor_unreachable"


def test_open_in_studio_propagates_export_failure(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    monkeypatch.setenv("EDITOR_API_TOKEN", "test-editor-token")
    monkeypatch.delenv("EDITOR_API_TOKEN_FILE", raising=False)
    context = _ctx()
    # No source/content generated -> quality gate should block export before any network call.
    project = create_course_project(
        {"course_title": "Empty Course", "audience": "crew", "language": "English"},
        context,
    )
    project_id = project["data"]["project_id"]

    def fake_urlopen(request, timeout=None):
        raise AssertionError("urlopen should not be called when export itself fails")

    monkeypatch.setattr(tools, "urlopen", fake_urlopen)

    result = open_in_studio({"project_id": project_id}, context)

    assert result["ok"] is False
