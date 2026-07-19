import base64
import json
from pathlib import Path

from course_mcp_server.security import RequestContext
from course_mcp_server.tools import (
    approve_course_plan,
    attach_media,
    build_export_package,
    create_course_project,
    ingest_source_text,
    propose_course_plan,
    save_course_discovery_answer,
    start_course_discovery,
    submit_course_content,
    upload_media_asset,
)


def _ctx() -> RequestContext:
    return RequestContext(tenant_id="tenant-a", user_id="user-a", token="token", request_id="req1")


def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSE_PROJECT_STORE_PATH", str(tmp_path / "projects.json"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    (tmp_path / "uploads").mkdir(exist_ok=True)


RESEARCH_TEXT = (
    "Sourced research brief on ramp safety. "
    "Cones and chocks must be verified before pushback according to ground operations manuals. "
    "Wing walkers guide all aircraft movement in congested areas; hand signals must be standard IATA. "
    "FOD walks happen before every departure; jet blast zones are marked and enforced. "
    "Sources: IATA Ground Operations Manual (IGOM) chapter 4; airline ramp SOP 2025 revision."
)


def test_agent_research_flows_in_via_ingest_source_text(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    context = _ctx()
    pid = create_course_project(
        {"course_title": "Ramp Safety", "audience": "ramp agents", "language": "English"}, context
    )["data"]["project_id"]
    start_course_discovery({"project_id": pid}, context)
    save_course_discovery_answer(
        {"project_id": pid, "question_id": "course_brief_line", "answer": "Ramp safety for new ramp agents"}, context
    )
    save_course_discovery_answer({"project_id": pid, "question_id": "source_mode", "answer": "agent_research"}, context)

    result = ingest_source_text(
        {"project_id": pid, "title": "Ramp safety research brief", "source_type": "research", "text": RESEARCH_TEXT},
        context,
    )
    assert result["ok"] is True
    assert result["data"]["source_type"] == "research"
    assert "Sourced research brief" in result["data"]["extracted_text_preview"]

    save_course_discovery_answer({"project_id": pid, "question_id": "duration_preset", "answer": "standard"}, context)
    save_course_discovery_answer({"project_id": pid, "question_id": "media_plan_mode", "answer": "agent_images"}, context)
    plan = propose_course_plan({"project_id": pid}, context)
    assert plan["ok"] is True
    approval = approve_course_plan({"project_id": pid}, context)
    # Research counted as source chunks -> ready without any file upload.
    assert approval["data"]["ready_for_generation"] is True


def test_topic_only_mode_does_not_require_sources(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    context = _ctx()
    pid = create_course_project(
        {"course_title": "Time Management", "audience": "everyone", "language": "English"}, context
    )["data"]["project_id"]
    start_course_discovery({"project_id": pid}, context)
    for question_id, answer in (
        ("course_brief_line", "Time management basics for busy professionals"),
        ("source_mode", "topic_only"),
        ("duration_preset", "micro"),
        ("media_plan_mode", "text_only"),
    ):
        save_course_discovery_answer({"project_id": pid, "question_id": question_id, "answer": answer}, context)
    propose_course_plan({"project_id": pid}, context)
    approval = approve_course_plan({"project_id": pid}, context)
    assert approval["data"]["ready_for_generation"] is True


def test_export_blocks_until_mandatory_images_are_attached(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    context = _ctx()
    pid = create_course_project(
        {"course_title": "Agile Sprint Playbook", "audience": "project managers", "language": "English"}, context
    )["data"]["project_id"]
    start_course_discovery({"project_id": pid}, context)
    for question_id, answer in (
        ("course_brief_line", "Agile sprint playbook for project managers"),
        ("source_mode", "topic_only"),
        ("duration_preset", "standard"),
        ("media_plan_mode", "agent_images"),
    ):
        save_course_discovery_answer({"project_id": pid, "question_id": question_id, "answer": answer}, context)

    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "agile_course_content.json").read_text(encoding="utf-8")
    )
    fixture["project_id"] = pid
    submitted = submit_course_content(fixture, context)
    assert submitted["ok"] is True

    blocked = build_export_package({"project_id": pid, "export_format": "scorm"}, context)
    assert blocked["ok"] is False
    assert blocked["error"] == "media_incomplete"
    briefs = blocked["data"]["image_briefs"]
    assert briefs, "expected the unfilled brief list"

    # Agent fulfils every brief: generate (fake) image, upload, attach.
    for brief in briefs:
        filename = brief["filename"].replace(".png", ".svg")
        upload_media_asset(
            {
                "project_id": pid,
                "filename": filename,
                "content_base64": base64.b64encode(b"<svg xmlns='http://www.w3.org/2000/svg'/>").decode(),
            },
            context,
        )
        attach_media(
            {"project_id": pid, "block_id": brief["block_id"], "kind": "image", "upload_id": filename},
            context,
        )

    unblocked = build_export_package({"project_id": pid, "export_format": "scorm"}, context)
    assert unblocked["ok"] is True, unblocked.get("data")

    # Waiver path also works on a fresh identical project state.
    assert build_export_package(
        {"project_id": pid, "export_format": "scorm", "allow_missing_media": True}, context
    )["ok"] is True
