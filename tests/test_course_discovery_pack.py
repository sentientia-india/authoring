from course_mcp_server.security import ALLOWED_TOOLS, RequestContext
from course_mcp_server.tools import (
    approve_course_outline,
    approve_lesson_structure,
    check_generation_readiness,
    create_course_project,
    generate_course_with_codex,
    get_course_workflow_status,
    get_next_course_question,
    ingest_course_source,
    list_course_templates,
    propose_course_outline,
    propose_lesson_structure,
    recommend_course_templates,
    save_course_brief,
    save_course_discovery_answer,
    select_assessment_model,
    select_course_template,
    select_interaction_model,
    start_course_discovery,
)


def _ctx() -> RequestContext:
    return RequestContext(tenant_id="tenant-a", user_id="user-a", token="token", request_id="req1")


def _create_project(tmp_path, monkeypatch, title="AI for Students", audience="students", compliance_domain=None):
    monkeypatch.setenv("COURSE_PROJECT_STORE_PATH", str(tmp_path / "projects.json"))
    monkeypatch.setenv("JOB_STORE_PATH", str(tmp_path / "jobs.json"))
    context = _ctx()
    result = create_course_project(
        {
            "course_title": title,
            "audience": audience,
            "language": "English",
            "compliance_domain": compliance_domain,
        },
        context,
    )
    return context, result["data"]["project_id"]


def _brief_payload(project_id):
    return {
        "project_id": project_id,
        "course_title": "Safety Basics",
        "target_learner": "crew",
        "learner_level": "beginner",
        "course_goal": "Avoid unsafe steps",
        "industry_context": "airline operations",
        "course_type": "compliance course",
        "expected_duration": 30,
        "source_material": "uploaded SOP",
        "module_topic_mode": "suggested_modules",
        "export_targets": ["html", "scorm"],
    }


def _add_source(tmp_path, monkeypatch, context, project_id):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(exist_ok=True)
    (upload_dir / "source.txt").write_text("Always inspect equipment before work.\n\nEscalate unsafe conditions.", encoding="utf-8")
    monkeypatch.setenv("UPLOAD_DIR", str(upload_dir))
    return ingest_course_source({"project_id": project_id, "upload_id": "source.txt", "source_type": "raw_text"}, context)


def test_discovery_pack_tools_are_allowlisted():
    for tool_name in {
        "list_course_templates",
        "recommend_course_templates",
        "start_course_discovery",
        "save_course_brief",
        "get_next_course_question",
        "save_course_discovery_answer",
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
    }:
        assert tool_name in ALLOWED_TOOLS


def test_discovery_flow_uses_ai_default_when_answer_is_blank(tmp_path, monkeypatch):
    context, project_id = _create_project(tmp_path, monkeypatch)
    start_course_discovery({"project_id": project_id}, context)

    result = save_course_discovery_answer(
        {"project_id": project_id, "question_id": "course_title", "answer": ""},
        context,
    )

    assert result["ok"] is True
    assert result["data"]["answer"]["source"] == "ai_suggested"
    assert result["data"]["answer"]["value"]


def test_next_question_asks_essentials_first_then_brief_details(tmp_path, monkeypatch):
    context, project_id = _create_project(tmp_path, monkeypatch)
    start = start_course_discovery({"project_id": project_id}, context)
    assert start["data"]["next_question"]["id"] == "course_brief_line"
    assert [question["id"] for question in start["data"]["questions"][:3]] == [
        "course_brief_line",
        "duration_preset",
        "media_plan_mode",
    ]

    save_course_discovery_answer(
        {"project_id": project_id, "question_id": "course_brief_line", "answer": "Ramp safety basics for new ramp agents"},
        context,
    )
    next_question = get_next_course_question({"project_id": project_id}, context)

    # The one-liner auto-derives the detailed brief fields so they are not re-asked.
    assert next_question["data"]["next_question"]["id"] == "duration_preset"
    answered = {"course_title", "target_learner", "course_goal"}
    remaining_ids = [question["id"] for question in next_question["data"]["questions"]]
    assert not answered.intersection(remaining_ids)


def test_discovery_flow_uses_user_answer_over_ai_default(tmp_path, monkeypatch):
    context, project_id = _create_project(tmp_path, monkeypatch)
    start_course_discovery({"project_id": project_id}, context)

    result = save_course_discovery_answer(
        {"project_id": project_id, "question_id": "course_title", "answer": "Safety Basics"},
        context,
    )

    assert result["ok"] is True
    assert result["data"]["answer"]["source"] == "user_provided"
    assert result["data"]["answer"]["value"] == "Safety Basics"


def test_blank_boolean_question_defaults_to_yes(tmp_path, monkeypatch):
    context, project_id = _create_project(tmp_path, monkeypatch)
    start_course_discovery({"project_id": project_id}, context)
    save_course_discovery_answer({"project_id": project_id, "question_id": "course_title", "answer": "Safety Basics"}, context)
    save_course_discovery_answer({"project_id": project_id, "question_id": "target_learner", "answer": "crew"}, context)
    save_course_discovery_answer({"project_id": project_id, "question_id": "course_goal", "answer": "Avoid unsafe steps"}, context)
    save_course_discovery_answer({"project_id": project_id, "question_id": "learner_level", "answer": "beginner"}, context)

    result = save_course_discovery_answer(
        {"project_id": project_id, "question_id": "module_topics_review", "answer": ""},
        context,
    )

    assert result["ok"] is True
    assert result["data"]["answer"]["value"] is True
    assert result["data"]["answer"]["source"] == "ai_suggested"


def test_save_course_brief_approves_complete_brief(tmp_path, monkeypatch):
    context, project_id = _create_project(tmp_path, monkeypatch)
    start_course_discovery({"project_id": project_id}, context)

    result = save_course_brief(_brief_payload(project_id), context)

    assert result["ok"] is True
    assert result["data"]["status"] == "brief_approved"
    assert result["data"]["selected_value"]["approved"] is True


def test_generation_readiness_blocks_until_required_work_is_done(tmp_path, monkeypatch):
    context, project_id = _create_project(tmp_path, monkeypatch, compliance_domain="airline")
    project = select_course_template(
        {"topic": "Safety Basics", "audience": "crew", "industry": "airline", "delivery_mode": "simulation"},
        context,
    )
    assert project["ok"] is True

    readiness = check_generation_readiness({"project_id": project_id}, context)

    assert readiness["ok"] is True
    assert readiness["data"]["ready"] is False
    assert "required course brief answers" in readiness["data"]["missing"]
    assert "source chunks" in readiness["data"]["missing"]


def test_course_cannot_generate_without_approved_brief(tmp_path, monkeypatch):
    context, project_id = _create_project(tmp_path, monkeypatch, compliance_domain="airline")
    _add_source(tmp_path, monkeypatch, context, project_id)

    result = generate_course_with_codex({"project_id": project_id}, context)

    assert result["ok"] is False
    assert "brief approval" in result["data"]["missing"]


def test_course_cannot_generate_without_approved_outline(tmp_path, monkeypatch):
    context, project_id = _create_project(tmp_path, monkeypatch, compliance_domain="airline")
    _add_source(tmp_path, monkeypatch, context, project_id)
    start_course_discovery({"project_id": project_id}, context)
    save_course_brief(_brief_payload(project_id), context)

    result = generate_course_with_codex({"project_id": project_id}, context)

    assert result["ok"] is False
    assert "approved module outline" in result["data"]["missing"]


def test_course_cannot_generate_without_approved_lessons(tmp_path, monkeypatch):
    context, project_id = _create_project(tmp_path, monkeypatch, compliance_domain="airline")
    _add_source(tmp_path, monkeypatch, context, project_id)
    start_course_discovery({"project_id": project_id}, context)
    save_course_brief(_brief_payload(project_id), context)
    propose_course_outline({"project_id": project_id}, context)
    approve_course_outline({"project_id": project_id}, context)

    result = generate_course_with_codex({"project_id": project_id}, context)

    assert result["ok"] is False
    assert "approved lesson structure" in result["data"]["missing"]


def test_course_cannot_generate_without_assessment_model(tmp_path, monkeypatch):
    context, project_id = _create_project(tmp_path, monkeypatch, compliance_domain="airline")
    _add_source(tmp_path, monkeypatch, context, project_id)
    start_course_discovery({"project_id": project_id}, context)
    save_course_brief(_brief_payload(project_id), context)
    propose_course_outline({"project_id": project_id}, context)
    approve_course_outline({"project_id": project_id}, context)
    propose_lesson_structure({"project_id": project_id}, context)
    approve_lesson_structure({"project_id": project_id}, context)
    select_interaction_model({"project_id": project_id, "model": {"type": "scenario_based"}}, context)

    result = generate_course_with_codex({"project_id": project_id}, context)

    assert result["ok"] is False
    assert "assessment model" in result["data"]["missing"]


def test_course_cannot_generate_without_interaction_model(tmp_path, monkeypatch):
    context, project_id = _create_project(tmp_path, monkeypatch, compliance_domain="airline")
    _add_source(tmp_path, monkeypatch, context, project_id)
    start_course_discovery({"project_id": project_id}, context)
    save_course_brief(_brief_payload(project_id), context)
    propose_course_outline({"project_id": project_id}, context)
    approve_course_outline({"project_id": project_id}, context)
    propose_lesson_structure({"project_id": project_id}, context)
    approve_lesson_structure({"project_id": project_id}, context)
    select_assessment_model({"project_id": project_id, "model": {"type": "mixed"}}, context)

    result = generate_course_with_codex({"project_id": project_id}, context)

    assert result["ok"] is False
    assert "interaction model" in result["data"]["missing"]


def test_outline_is_proposed_before_lesson_structure_and_can_be_changed(tmp_path, monkeypatch):
    context, project_id = _create_project(tmp_path, monkeypatch, compliance_domain="airline")
    _add_source(tmp_path, monkeypatch, context, project_id)
    start_course_discovery({"project_id": project_id}, context)
    save_course_brief(_brief_payload(project_id), context)

    outline = propose_course_outline({"project_id": project_id}, context)
    assert outline["data"]["proposed_module_outline"]
    assert outline["data"]["proposed_lesson_structure"] == []

    changed = [
        {"module_id": "module_1", "title": "Renamed module", "objective": "Apply SOP safely.", "review_status": "pending"}
    ]
    from course_mcp_server.tools import update_course_outline

    update = update_course_outline({"project_id": project_id, "items": changed}, context)
    assert update["data"]["selected_value"]["module_outline"][0]["title"] == "Renamed module"

    approval = approve_course_outline({"project_id": project_id}, context)
    assert approval["data"]["status"] == "outline_approved"


def test_generation_readiness_passes_after_all_required_approvals(tmp_path, monkeypatch):
    context, project_id = _create_project(tmp_path, monkeypatch, compliance_domain="airline")
    _add_source(tmp_path, monkeypatch, context, project_id)
    start_course_discovery({"project_id": project_id}, context)
    save_course_brief(_brief_payload(project_id), context)
    propose_course_outline({"project_id": project_id}, context)
    approve_course_outline({"project_id": project_id}, context)
    propose_lesson_structure({"project_id": project_id}, context)
    approve_lesson_structure({"project_id": project_id}, context)
    select_assessment_model({"project_id": project_id, "model": {"type": "mixed", "question_types": ["mcq", "matching"]}}, context)
    select_interaction_model({"project_id": project_id, "model": {"type": "scenario_based", "html_video": True}}, context)

    readiness = check_generation_readiness({"project_id": project_id}, context)

    assert readiness["data"]["ready"] is True
    assert readiness["data"]["status"] == "ready_for_generation"


def test_generate_course_with_codex_uses_only_approved_inputs_and_source_chunks(tmp_path, monkeypatch):
    context, project_id = _create_project(tmp_path, monkeypatch, compliance_domain="airline")
    _add_source(tmp_path, monkeypatch, context, project_id)
    start_course_discovery({"project_id": project_id}, context)
    save_course_brief(_brief_payload(project_id), context)
    propose_course_outline({"project_id": project_id}, context)
    approve_course_outline({"project_id": project_id}, context)
    propose_lesson_structure({"project_id": project_id}, context)
    approve_lesson_structure({"project_id": project_id}, context)
    select_assessment_model({"project_id": project_id, "model": {"type": "mixed", "question_types": ["mcq", "matching"]}}, context)
    select_interaction_model({"project_id": project_id, "model": {"type": "scenario_based", "html_video": True}}, context)

    result = generate_course_with_codex({"project_id": project_id}, context)
    payload = result["data"]["codex_payload"]

    assert result["ok"] is True
    assert payload["course_brief"]["course_title"] == "Safety Basics"
    assert payload["approved_module_outline"]
    assert payload["approved_lesson_structure"]
    assert payload["selected_template"]
    assert payload["source_chunks"]
    assert payload["assessment_model"]["type"] == "mixed"
    assert payload["interaction_model"]["type"] == "scenario_based"
    assert not {"raw_logs", "internal_prompts", "source_code", "secrets", "env", "database_query", "shell", "docker"}.intersection(payload)


def test_codex_contract_requires_project_workflow_artifacts(tmp_path, monkeypatch):
    context, project_id = _create_project(tmp_path, monkeypatch, compliance_domain="airline")
    start_course_discovery({"project_id": project_id}, context)
    save_course_discovery_answer({"project_id": project_id, "question_id": "course_title", "answer": "Safety Basics"}, context)
    save_course_discovery_answer({"project_id": project_id, "question_id": "target_learner", "answer": "crew"}, context)
    save_course_discovery_answer({"project_id": project_id, "question_id": "course_goal", "answer": "Avoid unsafe steps"}, context)
    save_course_discovery_answer({"project_id": project_id, "question_id": "learner_level", "answer": "beginner"}, context)
    save_course_discovery_answer({"project_id": project_id, "question_id": "module_count_preference", "answer": 4}, context)
    save_course_discovery_answer({"project_id": project_id, "question_id": "module_topics_review", "answer": True}, context)
    save_course_discovery_answer({"project_id": project_id, "question_id": "assessment_preference", "answer": "mixed"}, context)
    save_course_discovery_answer({"project_id": project_id, "question_id": "interaction_preference", "answer": "scenario_based"}, context)
    save_course_discovery_answer({"project_id": project_id, "question_id": "html_video_enabled", "answer": True}, context)
    save_course_discovery_answer({"project_id": project_id, "question_id": "gamification_enabled", "answer": True}, context)
    save_course_discovery_answer({"project_id": project_id, "question_id": "question_types", "answer": "mcq,matching"}, context)
    save_course_discovery_answer({"project_id": project_id, "question_id": "export_targets", "answer": "html,scorm"}, context)

    propose_course_outline({"project_id": project_id}, context)
    select_assessment_model({"project_id": project_id, "model": {"type": "mixed", "passing_score": 80}}, context)
    select_interaction_model({"project_id": project_id, "model": {"type": "scenario_based", "html_video": True}}, context)

    readiness = check_generation_readiness({"project_id": project_id}, context)
    assert readiness["data"]["ready"] is False

    status = get_course_workflow_status({"project_id": project_id}, context)
    assert status["ok"] is True
    assert status["data"]["selected_template_id"] is None

    contract = generate_course_with_codex({"project_id": project_id}, context)
    assert contract["ok"] is False
    assert contract["error"] == "not_ready"


def test_template_catalog_and_recommendation_surface(tmp_path, monkeypatch):
    context, project_id = _create_project(tmp_path, monkeypatch, title="Customer Support", audience="support agents")
    template_catalog = list_course_templates({}, context)
    recommendations = recommend_course_templates({"project_id": project_id, "source_summary": "customer support escalation"}, context)

    assert template_catalog["ok"] is True
    assert template_catalog["data"]["templates"]
    assert recommendations["ok"] is True
    assert recommendations["data"]["recommendations"]
