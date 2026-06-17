from course_mcp_server.security import ALLOWED_TOOLS, RequestContext
from course_mcp_server.tools import (
    build_export_package,
    create_course_project,
    generate_assessment_bank,
    generate_course_blueprint,
    generate_interactive_activity,
    generate_lesson_pack,
    generate_module_pack,
    ingest_course_source,
    list_course_artifacts,
    request_publish_approval,
    validate_instructional_quality,
)


def _ctx() -> RequestContext:
    return RequestContext(tenant_id="tenant-a", user_id="user-a", token="token", request_id="req1")


def test_production_tool_surface_is_narrow_and_safe():
    assert ALLOWED_TOOLS == {
        "create_course_project",
        "ingest_course_source",
        "generate_course_blueprint",
        "generate_module_pack",
        "generate_lesson_pack",
        "generate_interactive_activity",
        "generate_assessment_bank",
        "generate_roleplay_simulation",
        "validate_instructional_quality",
        "build_export_package",
        "get_course_generation_status",
        "list_course_artifacts",
        "request_publish_approval",
    }


def test_create_project_then_ingest_source_from_controlled_upload_id(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    (upload_dir / "sop.txt").write_text("# Ramp SOP\nAlways inspect cones before pushback.", encoding="utf-8")
    monkeypatch.setenv("UPLOAD_DIR", str(upload_dir))
    monkeypatch.setenv("COURSE_PROJECT_STORE_PATH", str(tmp_path / "projects.json"))

    project = create_course_project(
        {
            "course_title": "Ramp Safety",
            "audience": "ramp agents",
            "language": "English",
            "compliance_domain": "airline",
        },
        _ctx(),
    )
    project_id = project["data"]["project_id"]

    result = ingest_course_source(
        {"project_id": project_id, "upload_id": "sop.txt", "source_type": "raw_text"},
        _ctx(),
    )

    assert result["ok"] is True
    assert result["data"]["project_id"] == project_id
    assert result["data"]["source_type"] == "raw_text"
    assert result["data"]["extracted_text_preview"].startswith("Ramp SOP")
    assert str(tmp_path) not in str(result["data"])


def test_ingest_source_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("COURSE_PROJECT_STORE_PATH", str(tmp_path / "projects.json"))

    result = ingest_course_source(
        {"project_id": "course_abc12345", "upload_id": "../secret.env", "source_type": "raw_text"},
        _ctx(),
    )

    assert result["ok"] is False
    assert result["error"] == "validation_error"


def test_generate_blueprint_module_lesson_activity_assessment_and_quality(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSE_PROJECT_STORE_PATH", str(tmp_path / "projects.json"))
    context = _ctx()
    project = create_course_project(
        {"course_title": "AI for Students", "audience": "students", "language": "English"},
        context,
    )
    project_id = project["data"]["project_id"]

    blueprint = generate_course_blueprint({"project_id": project_id, "duration_minutes": 30}, context)
    modules = generate_module_pack({"project_id": project_id, "module_count": 2}, context)
    lessons = generate_lesson_pack({"project_id": project_id, "module_id": "module_1"}, context)
    activity = generate_interactive_activity(
        {"project_id": project_id, "activity_type": "flashcards", "objective": "Use AI safely"},
        context,
    )
    assessment = generate_assessment_bank(
        {"project_id": project_id, "question_count": 6, "question_types": ["mcq", "scenario", "matching"]},
        context,
    )
    quality = validate_instructional_quality({"project_id": project_id}, context)
    artifacts = list_course_artifacts({"project_id": project_id}, context)

    assert blueprint["data"]["project_id"] == project_id
    assert len(modules["data"]["modules"]) == 2
    assert lessons["data"]["lessons"][0]["citations"]
    assert activity["data"]["activity_type"] == "flashcards"
    assert {q["type"] for q in assessment["data"]["questions"]} >= {"mcq", "scenario", "matching"}
    assert set(quality["data"]) == {"score", "status", "issues", "recommendations"}
    assert quality["data"]["status"] in {"passed", "needs_review", "failed"}
    assert "blueprint" in artifacts["data"]["artifact_types"]


def test_request_publish_approval_never_publishes(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSE_PROJECT_STORE_PATH", str(tmp_path / "projects.json"))
    context = _ctx()
    project = create_course_project(
        {"course_title": "SOP Course", "audience": "crew", "language": "English"},
        context,
    )

    result = request_publish_approval(
        {"project_id": project["data"]["project_id"], "reviewer": "training-manager"},
        context,
    )

    assert result["data"]["review_status"] == "needs_review"
    assert result["data"]["published"] is False


def test_build_export_package_supports_h5p_without_new_public_tool(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSE_PROJECT_STORE_PATH", str(tmp_path / "projects.json"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    context = _ctx()
    project = create_course_project(
        {"course_title": "Interactive SOP", "audience": "crew", "language": "English"},
        context,
    )
    project_id = project["data"]["project_id"]
    generate_interactive_activity(
        {
            "project_id": project_id,
            "activity_type": "matching",
            "objective": "Match each SOP step to its control.",
        },
        context,
    )

    result = build_export_package({"project_id": project_id, "export_format": "h5p"}, context)

    assert result["ok"] is True
    assert result["data"]["export_format"] == "h5p"
    assert result["data"]["package_path"].endswith(".h5p")
