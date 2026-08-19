from __future__ import annotations

import copy
import json
from pathlib import Path
from urllib.error import HTTPError, URLError

from course_mcp_server import tools
from course_mcp_server.security import RequestContext
from course_mcp_server.tools import (
    _project_course_payload,
    create_course_project,
    import_studio_edits,
    submit_course_content,
)


def _ctx() -> RequestContext:
    return RequestContext(tenant_id="tenant-a", user_id="user-a", token="token", request_id="req1")


def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSE_PROJECT_STORE_PATH", str(tmp_path / "projects.json"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("OBJECT_STORE_LOCAL_ROOT", str(tmp_path / "objects"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    (tmp_path / "uploads").mkdir(exist_ok=True)
    monkeypatch.setenv("EDITOR_INTERNAL_URL", "http://scorm-editor.internal:8788")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://learn.example.com")


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _project_with_content(tmp_path, monkeypatch, context):
    _env(tmp_path, monkeypatch)
    project = create_course_project(
        {"course_title": "Agile Delivery", "audience": "engineers", "language": "English"}, context
    )
    project_id = project["data"]["project_id"]
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "agile_course_content.json").read_text(encoding="utf-8")
    )
    fixture["project_id"] = project_id
    submitted = submit_course_content(fixture, context)
    assert submitted["ok"] is True
    return project_id


def test_import_studio_edits_success(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_API_TOKEN", "test-editor-token")
    monkeypatch.delenv("EDITOR_API_TOKEN_FILE", raising=False)
    context = _ctx()
    project_id = _project_with_content(tmp_path, monkeypatch, context)

    course = {
        "course_title": "Agile Delivery",
        "modules": [
            {
                "id": "module_1",
                "title": "Module 1",
                "lessons": [{"id": "lesson_1", "title": "Lesson", "objective": "Edited in studio."}],
            }
        ],
    }

    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        return _FakeResponse({"session": "sess123abc", "course": course, "version": 3})

    monkeypatch.setattr(tools, "urlopen", fake_urlopen)

    result = import_studio_edits({"project_id": project_id, "session_id": "sess123abc"}, context)

    assert result["ok"] is True
    assert result["data"]["project_id"] == project_id
    assert result["data"]["session_id"] == "sess123abc"
    assert result["data"]["version"] == 3
    assert result["data"]["module_count"] == 1
    assert result["data"]["lesson_count"] == 1
    assert captured["url"] == "http://scorm-editor.internal:8788/api/course/sess123abc"
    assert captured["headers"]["Authorization"] == "Bearer test-editor-token"


def test_import_studio_edits_editor_not_configured(tmp_path, monkeypatch):
    context = _ctx()
    project_id = _project_with_content(tmp_path, monkeypatch, context)
    monkeypatch.delenv("EDITOR_API_TOKEN", raising=False)
    monkeypatch.delenv("EDITOR_API_TOKEN_FILE", raising=False)

    def fake_urlopen(request, timeout=None):
        raise AssertionError("urlopen should not be called when the editor token is missing")

    monkeypatch.setattr(tools, "urlopen", fake_urlopen)

    result = import_studio_edits({"project_id": project_id, "session_id": "sess123abc"}, context)

    assert result["ok"] is False
    assert result["error"] == "editor_not_configured"


def test_import_studio_edits_editor_unreachable(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_API_TOKEN", "test-editor-token")
    monkeypatch.delenv("EDITOR_API_TOKEN_FILE", raising=False)
    context = _ctx()
    project_id = _project_with_content(tmp_path, monkeypatch, context)

    def fake_urlopen(request, timeout=None):
        raise URLError("Connection refused")

    monkeypatch.setattr(tools, "urlopen", fake_urlopen)

    result = import_studio_edits({"project_id": project_id, "session_id": "sess123abc"}, context)

    assert result["ok"] is False
    assert result["error"] == "editor_unreachable"


def test_import_studio_edits_session_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_API_TOKEN", "test-editor-token")
    monkeypatch.delenv("EDITOR_API_TOKEN_FILE", raising=False)
    context = _ctx()
    project_id = _project_with_content(tmp_path, monkeypatch, context)

    def fake_urlopen(request, timeout=None):
        raise HTTPError(request.full_url, 400, "Unknown session", None, None)

    monkeypatch.setattr(tools, "urlopen", fake_urlopen)

    result = import_studio_edits({"project_id": project_id, "session_id": "does-not-exist"}, context)

    assert result["ok"] is False
    assert result["error"] == "session_not_found"


def test_import_studio_edits_malformed_response(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_API_TOKEN", "test-editor-token")
    monkeypatch.delenv("EDITOR_API_TOKEN_FILE", raising=False)
    context = _ctx()
    project_id = _project_with_content(tmp_path, monkeypatch, context)

    def fake_urlopen(request, timeout=None):
        return _FakeResponse({"session": "sess123abc", "course": {"modules": "not-a-list"}, "version": 1})

    monkeypatch.setattr(tools, "urlopen", fake_urlopen)

    result = import_studio_edits({"project_id": project_id, "session_id": "sess123abc"}, context)

    assert result["ok"] is False
    assert result["error"] == "course_content_invalid"


def test_import_studio_edits_missing_course_field(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_API_TOKEN", "test-editor-token")
    monkeypatch.delenv("EDITOR_API_TOKEN_FILE", raising=False)
    context = _ctx()
    project_id = _project_with_content(tmp_path, monkeypatch, context)

    def fake_urlopen(request, timeout=None):
        return _FakeResponse({"session": "sess123abc", "version": 1})

    monkeypatch.setattr(tools, "urlopen", fake_urlopen)

    result = import_studio_edits({"project_id": project_id, "session_id": "sess123abc"}, context)

    assert result["ok"] is False
    assert result["error"] == "editor_response_invalid"


def test_import_studio_edits_fixes_objective_recompute_data_loss(tmp_path, monkeypatch):
    """Regression test for the diagnosed bug: a Course Studio edit to a lesson's
    "objective" text must survive subsequent reads of _project_course_payload, rather
    than being silently overwritten by _course_payload_from_submission recomputing it
    from objective_ids/learning_objectives on every read.
    """
    monkeypatch.setenv("EDITOR_API_TOKEN", "test-editor-token")
    monkeypatch.delenv("EDITOR_API_TOKEN_FILE", raising=False)
    context = _ctx()
    project_id = _project_with_content(tmp_path, monkeypatch, context)

    from course_mcp_server.project_store import get_project

    project = get_project(tenant_id=context.tenant_id, project_id=project_id)

    # Before any Studio edit: _project_course_payload derives lesson_1's objective from
    # objective_ids ("lo_sprint") + learning_objectives, exactly as documented.
    original_payload = _project_course_payload(project)
    lesson_1 = original_payload["modules"][0]["lessons"][0]
    assert lesson_1["id"] == "lesson_1"
    original_objective = lesson_1["objective"]
    assert original_objective == "Explain how fixed-length sprints expose delivery risk early."

    # Simulate a Course Studio edit: change ONLY lesson_1's "objective" field directly.
    # objective_ids and learning_objectives are left completely untouched -- this is
    # exactly the scenario that silently lost data before the studio_content fix.
    edited_course = copy.deepcopy(original_payload)
    edited_course["modules"][0]["lessons"][0]["objective"] = "Edited directly in Course Studio."
    assert edited_course["modules"][0]["lessons"][0]["objective_ids"] == ["lo_sprint"]

    def fake_urlopen(request, timeout=None):
        return _FakeResponse({"session": "sess123abc", "course": edited_course, "version": 2})

    monkeypatch.setattr(tools, "urlopen", fake_urlopen)

    pull_result = import_studio_edits({"project_id": project_id, "session_id": "sess123abc"}, context)
    assert pull_result["ok"] is True

    # Re-fetch the project (add_artifact persisted it) and read the payload again --
    # this is the exact call build_export_package / validate_superior_course_quality make.
    project = get_project(tenant_id=context.tenant_id, project_id=project_id)
    updated_payload = _project_course_payload(project)
    updated_lesson_1 = updated_payload["modules"][0]["lessons"][0]

    # The edited text must survive -- proving the studio_content short-circuit prevents
    # the silent recompute, not merely that the artifact got stored.
    assert updated_lesson_1["objective"] == "Edited directly in Course Studio."
    assert updated_lesson_1["objective"] != original_objective
