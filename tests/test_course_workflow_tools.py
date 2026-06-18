from course_mcp_server.security import ALLOWED_TOOLS, RequestContext
from course_mcp_server.tools import (
    build_storyline_handoff_package,
    build_export_package,
    create_material_ticket,
    create_course_project,
    generate_chapter_layout,
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
        "create_material_ticket",
        "generate_chapter_layout",
        "create_course_project",
        "ingest_course_source",
        "select_course_template",
        "generate_course_blueprint",
        "generate_module_pack",
        "generate_lesson_pack",
        "generate_interactive_activity",
        "generate_interactive_video",
        "generate_assessment_bank",
        "generate_roleplay_simulation",
        "validate_instructional_quality",
        "validate_superior_course_quality",
        "build_export_package",
        "build_storyline_handoff_package",
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
    assert set(quality["data"]) == {"score", "status", "issues", "recommendations", "metrics"}
    assert quality["data"]["status"] in {"approved", "passed", "needs_review", "failed"}
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
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    (upload_dir / "source.txt").write_text("Ramp safety source text with procedures and controls.", encoding="utf-8")
    monkeypatch.setenv("UPLOAD_DIR", str(upload_dir))
    context = _ctx()
    project = create_course_project(
        {"course_title": "Interactive SOP", "audience": "crew", "language": "English"},
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

    result = build_export_package({"project_id": project_id, "export_format": "h5p"}, context)

    assert result["ok"] is True
    assert result["data"]["export_format"] == "h5p"
    assert result["data"]["package_path"].endswith(".h5p")


def test_build_scorm_export_embeds_generated_activities(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSE_PROJECT_STORE_PATH", str(tmp_path / "projects.json"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    (upload_dir / "source.txt").write_text("Interactive SOP source text with procedures and controls.", encoding="utf-8")
    monkeypatch.setenv("UPLOAD_DIR", str(upload_dir))
    context = _ctx()
    project = create_course_project(
        {"course_title": "Interactive SOP", "audience": "crew", "language": "English"},
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

    result = build_export_package({"project_id": project_id, "export_format": "scorm"}, context)

    assert result["ok"] is True
    assert "activities/content.json" in result["data"]["files"]


def test_create_material_ticket_and_generate_chapter_layout_tools():
    ticket = create_material_ticket({"course_title": "AI for Students"}, _ctx())
    assert ticket["data"]["status"] == "needs_information"
    assert ticket["data"]["questions"]

    layout = generate_chapter_layout(
        {
            "course_title": "AI for Students",
            "audience": "students",
            "goal": "Use AI safely",
            "duration_minutes": 5,
            "materials": [{"upload_id": "notes.txt", "source_type": "raw_text"}],
            "interactive_preferences": ["matching"],
        },
        _ctx(),
    )
    assert layout["data"]["status"] == "ready_for_generation"
    assert layout["data"]["chapters"]


def test_build_storyline_handoff_package_tool(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSE_PROJECT_STORE_PATH", str(tmp_path / "projects.json"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    context = _ctx()
    project = create_course_project(
        {"course_title": "Emergency Evacuation", "audience": "cabin crew", "language": "English"},
        context,
    )
    project_id = project["data"]["project_id"]
    generate_lesson_pack({"project_id": project_id, "module_id": "module_1"}, context)
    generate_interactive_activity(
        {
            "project_id": project_id,
            "activity_type": "scenario_decision_tree",
            "objective": "Choose safe evacuation actions.",
        },
        context,
    )
    generate_assessment_bank(
        {"project_id": project_id, "question_count": 5, "question_types": ["scenario", "mcq"]},
        context,
    )

    result = build_storyline_handoff_package({"project_id": project_id}, context)

    assert result["ok"] is True
    assert result["data"]["package_path"].endswith(".zip")
    assert result["data"]["native_story_file_generated"] is False
    assert "storyboard.md" in result["data"]["files"]
