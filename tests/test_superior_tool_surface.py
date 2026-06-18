from course_mcp_server.security import ALLOWED_TOOLS, RequestContext
from course_mcp_server.tools import (
    build_export_package,
    create_course_project,
    generate_course_blueprint,
    generate_assessment_bank,
    generate_lesson_pack,
    generate_module_pack,
    generate_interactive_video,
    select_course_template,
    validate_superior_course_quality,
)


def _ctx() -> RequestContext:
    return RequestContext(tenant_id="tenant-a", user_id="user-a", token="token", request_id="req1")


def test_superior_tools_are_allowlisted():
    assert "select_course_template" in ALLOWED_TOOLS
    assert "generate_interactive_video" in ALLOWED_TOOLS
    assert "validate_superior_course_quality" in ALLOWED_TOOLS


def test_select_template_and_generate_video(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSE_PROJECT_STORE_PATH", str(tmp_path / "projects.json"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    context = _ctx()
    project = create_course_project(
        {"course_title": "Emergency Evacuation", "audience": "cabin crew", "language": "English", "compliance_domain": "airline"},
        context,
    )
    project_id = project["data"]["project_id"]
    selection = select_course_template(
        {"topic": "Emergency evacuation", "audience": "cabin crew", "industry": "airline", "delivery_mode": "simulation"},
        context,
    )
    assert selection["data"]["template_id"] == "airline_safety_simulation"

    generate_course_blueprint({"project_id": project_id, "duration_minutes": 30, "difficulty": "intermediate"}, context)
    quality = validate_superior_course_quality({"project_id": project_id}, context)
    assert "status" in quality["data"]

    video = generate_interactive_video({"project_id": project_id, "module_id": "module_1"}, context)
    assert video["ok"] is True
    assert video["data"]["files"]
    assert video["data"]["package_path"].endswith(".zip")


def test_export_blocks_when_superior_quality_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSE_PROJECT_STORE_PATH", str(tmp_path / "projects.json"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    context = _ctx()
    project = create_course_project(
        {"course_title": "Weak Safety Course", "audience": "crew", "language": "English", "compliance_domain": "airline"},
        context,
    )
    project_id = project["data"]["project_id"]
    generate_course_blueprint({"project_id": project_id, "duration_minutes": 30, "difficulty": "intermediate"}, context)
    generate_module_pack({"project_id": project_id, "module_count": 1}, context)
    generate_lesson_pack({"project_id": project_id, "module_id": "module_1"}, context)
    generate_assessment_bank({"project_id": project_id, "question_count": 2, "question_types": ["mcq"]}, context)

    result = build_export_package({"project_id": project_id, "export_format": "scorm"}, context)

    assert result["ok"] is False
    assert result["error"] == "quality_failed"
    assert result["data"]["status"] == "fail"
