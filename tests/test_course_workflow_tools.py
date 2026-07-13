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
    submit_course_content,
    validate_instructional_quality,
    upload_media_asset,
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
        "list_course_templates",
        "recommend_course_templates",
        "start_course_discovery",
        "save_course_brief",
        "get_next_course_question",
        "save_course_discovery_answer",
        "propose_course_plan",
        "approve_course_plan",
        "propose_course_outline",
        "update_course_outline",
        "approve_course_outline",
        "propose_lesson_structure",
        "update_lesson_structure",
        "approve_lesson_structure",
        "select_assessment_model",
        "select_interaction_model",
        "check_generation_readiness",
        "generate_course_with_codex",
        "get_course_workflow_status",
        "generate_course_blueprint",
        "submit_course_content",
        "submit_course_module",
        "upload_media_asset",
        "get_media_briefs",
        "attach_media",
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
    monkeypatch.setenv("OBJECT_STORE_LOCAL_ROOT", str(tmp_path / "objects"))

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
    stored_sources = list((tmp_path / "objects" / "tenants" / "tenant-a" / "sources").glob("source_*/sop.txt"))
    assert len(stored_sources) == 1


def test_media_upload_is_mirrored_to_tenant_object_storage(tmp_path, monkeypatch):
    import base64

    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("COURSE_PROJECT_STORE_PATH", str(tmp_path / "projects.json"))
    monkeypatch.setenv("OBJECT_STORE_LOCAL_ROOT", str(tmp_path / "objects"))
    project = create_course_project(
        {"course_title": "Media course", "audience": "operators", "language": "English"}, _ctx()
    )
    project_id = project["data"]["project_id"]
    result = upload_media_asset(
        {
            "project_id": project_id,
            "filename": "diagram.png",
            "content_base64": base64.b64encode(b"safe-image-bytes").decode(),
        },
        _ctx(),
    )
    assert result["ok"] is True
    stored = next((tmp_path / "objects" / "tenants" / "tenant-a" / "media").glob("media_*/tenant-a--diagram.png"))
    assert stored.read_bytes() == b"safe-image-bytes"


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


def test_generate_blueprint_supports_three_minute_micro_course(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSE_PROJECT_STORE_PATH", str(tmp_path / "projects.json"))
    context = _ctx()
    project = create_course_project(
        {"course_title": "Agile Micro Course", "audience": "project managers", "language": "English"},
        context,
    )

    blueprint = generate_course_blueprint({"project_id": project["data"]["project_id"], "duration_minutes": 3}, context)

    assert blueprint["ok"] is True
    assert blueprint["data"]["project_id"] == project["data"]["project_id"]


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
    monkeypatch.setenv("OBJECT_STORE_LOCAL_ROOT", str(tmp_path / "objects"))
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
    exported = list((tmp_path / "objects" / "tenants" / "tenant-a" / "exports").glob("export_*/*.h5p"))
    assert len(exported) == 1


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
    assert "activities/content.json" not in result["data"]["files"]
    assert "h5p/course.h5p" not in result["data"]["files"]
    assert "assets/player.js" in result["data"]["files"]


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
            "answers": {"module_topics_review": "yes", "quiz_decision": "mixed"},
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


def test_submitted_course_content_drives_scorm_export(tmp_path, monkeypatch):
    import json
    from pathlib import Path

    monkeypatch.setenv("COURSE_PROJECT_STORE_PATH", str(tmp_path / "projects.json"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    context = _ctx()
    project = create_course_project(
        {"course_title": "Agile Sprint Playbook", "audience": "project managers", "language": "English"},
        context,
    )
    project_id = project["data"]["project_id"]

    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "agile_course_content.json").read_text(encoding="utf-8")
    )
    fixture["project_id"] = project_id
    submission = submit_course_content(fixture, context)
    assert submission["ok"] is True
    assert submission["data"]["module_count"] == 3
    assert submission["data"]["lesson_count"] == 6
    assert submission["data"]["quality_status"] in {"approved", "needs_review"}

    result = build_export_package({"project_id": project_id, "export_format": "scorm"}, context)
    assert result["ok"] is True, result.get("data")

    package_dir = Path(result["data"]["package_path"]).with_suffix("")
    course_json = json.loads((package_dir / "data" / "course.json").read_text(encoding="utf-8"))
    all_text = json.dumps(course_json)
    # Authored prose made it through; fabricated filler did not.
    assert "optimism can compound" in all_text
    assert "Use the source to explain" not in all_text
    assert "A learner faces a realistic decision." not in all_text
    # Activities are lesson-specific, not one global list repeated everywhere.
    lesson_activity_ids = [
        activity["activity_id"]
        for module in course_json["modules"]
        for lesson in module["lessons"]
        for activity in lesson.get("activities", [])
    ]
    assert len(lesson_activity_ids) == len(set(lesson_activity_ids))
