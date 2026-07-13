from __future__ import annotations

import os
import re
import shutil
import hashlib
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from typing import Any

from pydantic import ValidationError

from .advanced_quality_gates import evaluate_superior_quality
from .activities import build_activity
from .artifacts import store_artifact_metadata
from .course_generator import generate_lesson, generate_outline, generate_quiz, generate_roleplay
import base64
import copy

from .course_schema_v2 import CourseProjectV2, GameOptions, MediaAsset
from .media_briefs import build_media_briefs
from .object_store import store_path
from .provenance import sign_export
from .course_templates import TemplateRegistry
from .discovery import CourseDiscoveryState, CourseDiscoveryWorkflow
from .delivery import build_delivery_metadata
from .exporters.adapt_source import build_adapt_source_package
from .exporters.h5p import build_h5p_package
from .exporters.scorm import build_scorm_package
from .generation import CodexGenerationContractBuilder
from .html_video_engine import HtmlVideoRenderer, build_video_project_from_course
from .ingestion import extract_source
from .intake import create_ticket, generate_layout
from .job_store import get_job_status, record_job
from .licensing import License, TIER_EXPORT_QUOTAS, check_export_quota, record_export
from .project_store import add_artifact, create_project, get_project, latest_artifact, save_project
from .instructional_quality import validate_instructional_quality as validate_course_v2_quality
from .schemas import (
    ActivityRequest,
    ActivityResult,
    ArtifactListResult,
    AssessmentBankResult,
    AssessmentRequest,
    CodexGenerationContractResult,
    BlueprintRequest,
    CourseBriefSaveRequest,
    CourseOutlineRequest,
    CourseProjectRequest,
    CourseProjectResult,
    DiscoveryAnswerRequest,
    DiscoveryAnswerResult,
    DiscoveryAnswer,
    DiscoveryStartRequest,
    DiscoveryStartResult,
    ExportPackageRequest,
    ChapterLayoutResult,
    GenerationReadinessResult,
    InteractiveVideoRequest,
    InteractiveVideoResult,
    MaterialTicketResult,
    JobStatusRequest,
    LessonDraftRequest,
    LessonPackRequest,
    LessonPackResult,
    ListArtifactsRequest,
    ModulePackRequest,
    ModulePackResult,
    TemplateListResult,
    TemplateRecommendationRequest,
    TemplateRecommendationResult,
    PublishApprovalRequest,
    PublishApprovalResult,
    QualityValidationRequest,
    QualityValidationResult,
    AttachMediaRequest,
    AttachMediaResult,
    MediaBriefsRequest,
    MediaBriefsResult,
    SubmitCourseContentRequest,
    SubmitCourseContentResult,
    SubmitCourseModuleRequest,
    SubmitCourseModuleResult,
    UploadMediaAssetRequest,
    UploadMediaAssetResult,
    SuperiorQualityValidationRequest,
    SuperiorQualityValidationResult,
    WorkflowOutlineRequest,
    WorkflowOutlineResult,
    WorkflowStructureUpdateRequest,
    WorkflowModelSelectionRequest,
    WorkflowApprovalRequest,
    WorkflowSelectionResult,
    WorkflowStatusResult,
    QuizBankRequest,
    RoleplayScenarioRequest,
    ScormPackageRequest,
    SourceIngestRequest,
    SourceIngestResult,
    TemplateSelectionRequest,
    TemplateSelectionResult,
    StorylineHandoffRequest,
)
from .security import RequestContext, SecurityError, assert_tool_allowed, audit_event, redact_output
from .storyline_handoff import build_storyline_handoff_package as build_storyline_handoff_zip


def _safe_return(tool_name: str, context: RequestContext, request: Any, output: Any) -> dict[str, Any]:
    safe_output = redact_output(output)
    response = {
        "ok": True,
        "data": safe_output,
        "audit": audit_event(tool_name, context, request, safe_output),
    }
    if context.license_warning:
        response["license_warning"] = context.license_warning
    return response


def _error_return(tool_name: str, context: RequestContext, request: Any, error: str, output: Any) -> dict[str, Any]:
    safe_output = redact_output(output)
    return {
        "ok": False,
        "error": error,
        "data": safe_output,
        "audit": audit_event(tool_name, context, request, safe_output),
    }


def _project_or_raise(context: RequestContext, project_id: str) -> dict[str, Any]:
    project = get_project(tenant_id=context.tenant_id, project_id=project_id)
    if not project:
        raise SecurityError("Course project not found.")
    return project


def _template_registry() -> TemplateRegistry:
    return TemplateRegistry().load()


def _project_template(project: dict[str, Any]):
    template_id = project.get("template_id")
    registry = _template_registry()
    if template_id:
        try:
            return registry.get(template_id)
        except KeyError:
            pass
    match = registry.select_template(
        topic=project.get("course_title", ""),
        audience=project.get("audience", ""),
        industry=project.get("compliance_domain") or project.get("audience") or None,
        delivery_mode=project.get("delivery_mode") or None,
    )
    project["template_id"] = match.template.template_id
    project["template_name"] = match.template.name
    project.setdefault("workflow", {})
    project["workflow"]["selected_template_id"] = match.template.template_id
    save_project(project)
    return match.template


def _workflow_defaults(project: dict[str, Any]) -> dict[str, Any]:
    template = None
    if project.get("template_id"):
        try:
            template = _template_registry().get(project["template_id"])
        except KeyError:
            template = None
    default_answers = {}
    if template is not None:
        default_answers = dict(getattr(template, "model_extra", {}) or {}).get("default_answers", {})
    return default_answers


def _workflow_state(project: dict[str, Any]) -> CourseDiscoveryState:
    workflow = project.get("workflow") or {}
    return CourseDiscoveryState(
        project_id=project["project_id"],
        status=workflow.get("status", "discovery_started"),
        answers=workflow.get("answers", {}),
        selected_template_id=workflow.get("selected_template_id") or project.get("template_id"),
        module_outline=workflow.get("module_outline", []),
        lesson_structure=workflow.get("lesson_structure", []),
        assessment_model=workflow.get("assessment_model", {}),
        interaction_model=workflow.get("interaction_model", {}),
        approvals=workflow.get("approvals", {}),
        source_chunk_count=workflow.get("source_chunk_count") or len(_source_chunks_for_project(project)),
        course_plan=workflow.get("course_plan", {}),
    )


def _persist_workflow_state(project: dict[str, Any], state: CourseDiscoveryState) -> dict[str, Any]:
    project["workflow"] = state.to_dict()
    if state.selected_template_id:
        project["template_id"] = state.selected_template_id
    save_project(project)
    return project


def _source_chunks_for_project(project: dict[str, Any], limit: int = 12) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for source_index, source in enumerate(project.get("sources", []), start=1):
        text = str(source.get("extracted_text", "")).strip()
        if not text:
            continue
        parts = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        if not parts:
            parts = [text]
        for chunk_index, part in enumerate(parts[:3], start=1):
            chunks.append(
                {
                    "source_id": source.get("source_id", f"source_{source_index}"),
                    "chunk_id": f"{source.get('source_id', f'source_{source_index}')}_chunk_{chunk_index}",
                    "text": part[:2000],
                    "summary": part[:240],
                }
            )
            if len(chunks) >= limit:
                return chunks
    return chunks


def _proposed_topics_from_brief(brief: dict[str, Any], template_name: str | None = None) -> list[str]:
    course_title = brief.get("course_title") or "the course"
    audience = brief.get("audience") or brief.get("target_audience") or "the learners"
    goal = brief.get("goal") or brief.get("course_goal") or "the learning goal"
    template_hint = template_name or "the template"
    return [
        f"{course_title}: purpose and context",
        f"Core ideas and rules for {audience}",
        f"Applied practice using {template_hint}",
        f"Assessment and readiness for {goal}",
    ]


def _course_brief_from_state(state: CourseDiscoveryState) -> dict[str, Any]:
    brief = {}
    for key, answer in state.answers.items():
        brief[key] = answer.get("value")
    if "target_learner" in brief and "target_audience" not in brief:
        brief["target_audience"] = brief["target_learner"]
    if "course_title" not in brief and "target_audience" not in brief:
        brief.setdefault("course_title", "Generated Course")
    return brief


def _template_snapshot(template) -> dict[str, Any]:
    extra = dict(getattr(template, "model_extra", {}) or {})
    snapshot = {
        "template_id": template.template_id,
        "name": getattr(template, "name", extra.get("display_name", template.template_id)),
        "domain": getattr(template, "domain", extra.get("category", "General")),
        "recommended_interactions": list(getattr(template, "recommended_interactions", [])),
        "quality_rules": dict(getattr(template, "quality_rules", {})),
        "prompt_rules": list(getattr(template, "prompt_rules", [])),
        "lesson_blueprint": list(getattr(template, "lesson_blueprint", [])),
        "video_scene_blueprint": list(getattr(template, "video_scene_blueprint", [])),
        "default_answers": extra.get("default_answers", {}),
    }
    snapshot.update(extra)
    return snapshot


def _rank_templates(topic: str, audience: str, industry: str | None = None, delivery_mode: str | None = None, limit: int = 3) -> list[dict[str, Any]]:
    registry = _template_registry()
    haystack = f"{topic} {audience} {industry or ''} {delivery_mode or ''}".lower()
    scored: list[tuple[int, dict[str, Any], list[str]]] = []
    for template in registry._templates.values():
        snapshot = _template_snapshot(template)
        score = 0
        reasons: list[str] = []
        for phrase in snapshot.get("use_when", []) or []:
            if str(phrase).lower() in haystack:
                score += 3
                reasons.append(f"Matches: {phrase}")
        for phrase in snapshot.get("best_for", []) or []:
            if str(phrase).lower() in haystack:
                score += 3
                reasons.append(f"Best for: {phrase}")
        if delivery_mode and delivery_mode in (snapshot.get("supported_delivery_modes") or []):
            score += 2
            reasons.append("Delivery mode supported")
        if industry and str(industry).lower() in f"{snapshot.get('domain', '')} {snapshot.get('category', '')}".lower():
            score += 2
            reasons.append("Industry matched")
        if not reasons:
            reasons.append("General fit based on available course brief.")
        scored.append((score, snapshot, reasons))
    scored.sort(key=lambda item: item[0], reverse=True)
    output = []
    for score, snapshot, reasons in scored[:limit]:
        output.append(
            {
                "template_id": snapshot["template_id"],
                "name": snapshot["name"],
                "display_name": snapshot.get("display_name", snapshot["name"]),
                "category": snapshot.get("category", "General"),
                "score": score,
                "reasons": reasons,
                "recommended_interactions": snapshot.get("recommended_interactions", []),
                "quality_rules": snapshot.get("quality_rules", {}),
                "default_answers": snapshot.get("default_answers", {}),
            }
        )
    return output


def _discovery_context(project: dict[str, Any]) -> dict[str, Any]:
    return {
        "course_topic": project.get("course_title"),
        "target_audience": project.get("audience"),
        "detected_industry": project.get("compliance_domain"),
    }


def _question_with_suggestion(workflow: CourseDiscoveryWorkflow, project: dict[str, Any], question: dict[str, Any]) -> dict[str, Any]:
    defaults = _workflow_defaults(project)
    suggestion = workflow.default_provider.suggest(question, _discovery_context(project))
    return {
        **question,
        "suggested_answer": suggestion.to_dict(),
        "template_default": defaults.get(question["id"]),
    }


def _question_batch(workflow: CourseDiscoveryWorkflow, project: dict[str, Any], state: CourseDiscoveryState, *, limit: int = 6) -> list[dict[str, Any]]:
    return [_question_with_suggestion(workflow, project, question) for question in workflow.get_question_batch(state, limit=limit)]


def _record(context: RequestContext, tool_name: str, project_id: str, message: str) -> None:
    record_job(
        job_id=f"{tool_name}_{context.request_id or project_id[-8:]}",
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        tool_name=tool_name,
        status="completed",
        message=message,
    )


def create_course_project(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "create_course_project"
    assert_tool_allowed(tool_name)
    req = CourseProjectRequest.model_validate(payload)
    project = create_project(
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        course_title=req.course_title,
        audience=req.audience,
        language=req.language,
        compliance_domain=req.compliance_domain,
    )
    output = CourseProjectResult.model_validate(project).model_dump(mode="json")
    _record(context, tool_name, output["project_id"], "Course project created.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def create_material_ticket(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "create_material_ticket"
    assert_tool_allowed(tool_name)
    output = MaterialTicketResult.model_validate(create_ticket(payload)).model_dump(mode="json")
    _record(context, tool_name, output["ticket_id"], "Material ticket prepared.")
    return _safe_return(tool_name, context, payload, output)


def generate_chapter_layout(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "generate_chapter_layout"
    assert_tool_allowed(tool_name)
    output = ChapterLayoutResult.model_validate(generate_layout(payload)).model_dump(mode="json")
    _record(context, tool_name, context.request_id or "layout", "Chapter layout generated.")
    return _safe_return(tool_name, context, payload, output)


def select_course_template(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "select_course_template"
    assert_tool_allowed(tool_name)
    req = TemplateSelectionRequest.model_validate(payload)
    registry = _template_registry()
    match = registry.select_template(
        topic=req.topic,
        audience=req.audience,
        industry=req.industry,
        delivery_mode=req.delivery_mode,  # type: ignore[arg-type]
    )
    output = TemplateSelectionResult(
        template_id=match.template.template_id,
        name=match.template.name,
        recommended_interactions=list(match.template.recommended_interactions),
        quality_rules=match.template.quality_rules,
        theme=match.template.theme.model_dump(mode="json"),
        reason="; ".join(match.reasons),
    ).model_dump(mode="json")
    _record(context, tool_name, req.topic.replace(" ", "_")[:20], "Course template selected.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def list_course_templates(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "list_course_templates"
    assert_tool_allowed(tool_name)
    templates = [_template_snapshot(template) for template in _template_registry()._templates.values()]
    output = TemplateListResult(templates=templates).model_dump(mode="json")
    _record(context, tool_name, context.request_id or "templates", "Template catalog listed.")
    return _safe_return(tool_name, context, payload, output)


def recommend_course_templates(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "recommend_course_templates"
    assert_tool_allowed(tool_name)
    req = TemplateRecommendationRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    recommendations = _rank_templates(
        project.get("course_title", ""),
        project.get("audience", ""),
        project.get("compliance_domain"),
        project.get("delivery_mode"),
    )
    if req.source_summary:
        summary_recs = _rank_templates(
            project.get("course_title", ""),
            project.get("audience", ""),
            req.source_summary,
            project.get("delivery_mode"),
        )
        if summary_recs:
            recommendations = summary_recs
    output = TemplateRecommendationResult(recommendations=recommendations).model_dump(mode="json")
    _record(context, tool_name, req.project_id, "Template recommendations generated.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def start_course_discovery(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "start_course_discovery"
    assert_tool_allowed(tool_name)
    req = DiscoveryStartRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    workflow = CourseDiscoveryWorkflow()
    state = workflow.start(req.project_id)
    _persist_workflow_state(project, state)
    questions = _question_batch(workflow, project, state)
    next_question = questions[0] if questions else None
    output = DiscoveryStartResult(
        project_id=req.project_id,
        status=state.status,
        next_question=next_question,
        questions=questions,
        answers={k: DiscoveryAnswer.model_validate(v) for k, v in state.answers.items()},
        proposed_topics=_proposed_topics_from_brief(project),
        selected_template_id=state.selected_template_id,
    ).model_dump(mode="json")
    _record(context, tool_name, req.project_id, "Course discovery started.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def get_next_course_question(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "get_next_course_question"
    assert_tool_allowed(tool_name)
    req = DiscoveryStartRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    workflow = CourseDiscoveryWorkflow()
    state = _workflow_state(project)
    questions = _question_batch(workflow, project, state)
    next_question = questions[0] if questions else None
    output = DiscoveryStartResult(
        project_id=req.project_id,
        status=state.status,
        next_question=next_question,
        questions=questions,
        answers={k: DiscoveryAnswer.model_validate(v) for k, v in state.answers.items()},
        proposed_topics=_proposed_topics_from_brief(_course_brief_from_state(state), project.get("template_name")),
        selected_template_id=state.selected_template_id,
    ).model_dump(mode="json")
    _record(context, tool_name, req.project_id, "Next course question returned.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def save_course_discovery_answer(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "save_course_discovery_answer"
    assert_tool_allowed(tool_name)
    req = DiscoveryAnswerRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    workflow = CourseDiscoveryWorkflow()
    state = _workflow_state(project)
    answer = workflow.save_answer(
        state,
        req.question_id,
        req.answer,
        {
            "course_topic": project.get("course_title"),
            "target_audience": project.get("audience"),
            "detected_industry": project.get("compliance_domain"),
        },
        _workflow_defaults(project),
    )
    _persist_workflow_state(project, state)
    next_question = workflow.get_next_question(state)
    output = DiscoveryAnswerResult(
        project_id=req.project_id,
        question_id=req.question_id,
        answer=DiscoveryAnswer.model_validate(answer.to_dict()),
        next_question=next_question,
        status=state.status,
    ).model_dump(mode="json")
    _record(context, tool_name, req.project_id, f"Saved discovery answer for {req.question_id}.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def save_course_brief(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "save_course_brief"
    assert_tool_allowed(tool_name)
    req = CourseBriefSaveRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    workflow = CourseDiscoveryWorkflow()
    state = _workflow_state(project)
    values = req.model_dump(exclude={"project_id"}, exclude_none=True)
    answer_context = {
        "course_topic": project.get("course_title"),
        "target_audience": project.get("audience"),
        "detected_industry": project.get("compliance_domain"),
    }
    for question_id, answer in values.items():
        workflow.save_answer(state, question_id, answer, answer_context, _workflow_defaults(project))

    missing = workflow._missing_required_answers_for_stages(state, {"brief"})
    approved = not missing
    if approved:
        workflow.approve_brief(state)
        brief = _course_brief_from_state(state)
        project["course_title"] = str(brief.get("course_title") or project.get("course_title"))
        project["audience"] = str(brief.get("target_learner") or brief.get("target_audience") or project.get("audience"))
        project["compliance_domain"] = str(brief.get("industry_context") or project.get("compliance_domain") or "")
    else:
        state.status = "brief_pending"
    _persist_workflow_state(project, state)
    output = WorkflowSelectionResult(
        project_id=req.project_id,
        status=state.status,
        selected_value={
            "approved": approved,
            "missing": missing,
            "course_brief": _course_brief_from_state(state),
        },
    ).model_dump(mode="json")
    _record(context, tool_name, req.project_id, "Course brief saved.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def propose_course_outline(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "propose_course_outline"
    assert_tool_allowed(tool_name)
    req = WorkflowOutlineRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    state = _workflow_state(project)
    if not state.approvals.get("brief"):
        readiness = CourseDiscoveryWorkflow().check_generation_readiness(state)
        return _error_return(tool_name, context, req.model_dump(), "brief_not_approved", readiness)
    if not _source_chunks_for_project(project):
        return _error_return(
            tool_name,
            context,
            req.model_dump(),
            "source_chunks_required",
            {"ready": False, "missing": ["source chunks"], "status": state.status},
        )
    workflow = CourseDiscoveryWorkflow()
    template = _project_template(project)
    state.selected_template_id = template.template_id
    brief = _course_brief_from_state(state) or project
    proposed_topics = _proposed_topics_from_brief(brief, template.name)
    module_outline = [
        {
            "module_id": f"module_{index + 1}",
            "title": title,
            "objective": f"Help learners apply {brief.get('course_goal') or project['course_title']} in module {index + 1}.",
            "review_status": "pending",
        }
        for index, title in enumerate(proposed_topics[:4])
    ]
    workflow.set_module_outline(state, module_outline)
    _persist_workflow_state(project, state)
    output = WorkflowOutlineResult(
        project_id=req.project_id,
        proposed_module_outline=module_outline,
        proposed_lesson_structure=[],
        selected_template_id=state.selected_template_id,
    ).model_dump(mode="json")
    _record(context, tool_name, req.project_id, "Course outline proposed.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def update_course_outline(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "update_course_outline"
    assert_tool_allowed(tool_name)
    req = WorkflowStructureUpdateRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    state = _workflow_state(project)
    state.module_outline = req.items
    state.approvals["outline"] = False
    state.status = "outline_pending_review"
    _persist_workflow_state(project, state)
    output = WorkflowSelectionResult(project_id=req.project_id, status=state.status, selected_value={"module_outline": req.items}).model_dump(mode="json")
    _record(context, tool_name, req.project_id, "Course outline updated.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def approve_course_outline(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "approve_course_outline"
    assert_tool_allowed(tool_name)
    req = WorkflowApprovalRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    state = _workflow_state(project)
    if not state.module_outline:
        raise SecurityError("Cannot approve course outline without proposed outline.")
    state.approvals["outline"] = True
    state.status = "outline_approved"
    _persist_workflow_state(project, state)
    output = WorkflowSelectionResult(project_id=req.project_id, status=state.status, selected_value={"approved": True}).model_dump(mode="json")
    _record(context, tool_name, req.project_id, "Course outline approved.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def propose_course_plan(payload: dict, context: RequestContext) -> dict[str, Any]:
    """Build the single confirmation card: everything AI-suggested, shown once."""
    tool_name = "propose_course_plan"
    assert_tool_allowed(tool_name)
    req = WorkflowApprovalRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    state = _workflow_state(project)
    workflow = CourseDiscoveryWorkflow()
    missing = [
        q["id"]
        for q in workflow.get_question_batch(state, limit=10, stage="essentials")
        if q.get("required")
    ]
    if missing:
        return _error_return(
            tool_name,
            context,
            req.model_dump(),
            "essentials_missing",
            {"missing": missing, "message": "Answer the essential questions first."},
        )
    if not state.selected_template_id:
        brief = _course_brief_from_state(state)
        ranked = _rank_templates(
            topic=str(brief.get("course_title", "")),
            audience=str(brief.get("target_learner", "")),
            industry=str(brief.get("industry_context", "")) or None,
            limit=1,
        )
        if ranked:
            state.selected_template_id = ranked[0]["template_id"]
    template = _project_template(project) if state.selected_template_id else None
    proposed_modules = state.module_outline
    if not proposed_modules:
        brief = _course_brief_from_state(state)
        plan_defaults = state.answers.get("module_count_preference", {}).get("value", 5)
        topics = _proposed_topics_from_brief(brief, getattr(template, "name", None))
        count = max(2, min(int(plan_defaults or 5), 12))
        proposed_modules = [
            {"module_id": f"module_{index + 1}", "title": topics[index % len(topics)], "status": "proposed"}
            for index in range(count)
        ]
        state.module_outline = proposed_modules
    plan = workflow.build_course_plan(
        state,
        template_name=getattr(template, "name", None),
        proposed_modules=proposed_modules,
    )
    _persist_workflow_state(project, state)
    output = {"project_id": req.project_id, "status": state.status, "plan": plan}
    _record(context, tool_name, req.project_id, "Course plan proposed for one-shot confirmation.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def approve_course_plan(payload: dict, context: RequestContext) -> dict[str, Any]:
    """One user 'go' collapses brief, outline, lessons, assessment, and interaction approvals."""
    tool_name = "approve_course_plan"
    assert_tool_allowed(tool_name)
    req = WorkflowApprovalRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    state = _workflow_state(project)
    try:
        CourseDiscoveryWorkflow().approve_course_plan(state)
    except ValueError as exc:
        return _error_return(tool_name, context, req.model_dump(), "plan_not_ready", {"message": str(exc)})
    _persist_workflow_state(project, state)
    readiness = CourseDiscoveryWorkflow().check_generation_readiness(state)
    _persist_workflow_state(project, state)
    output = {
        "project_id": req.project_id,
        "status": state.status,
        "approved": True,
        "ready_for_generation": readiness["ready"],
        "missing": readiness["missing"],
    }
    _record(context, tool_name, req.project_id, "Course plan approved in one step.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def propose_lesson_structure(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "propose_lesson_structure"
    assert_tool_allowed(tool_name)
    req = WorkflowOutlineRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    state = _workflow_state(project)
    if not state.approvals.get("outline"):
        return _error_return(
            tool_name,
            context,
            req.model_dump(),
            "outline_not_approved",
            {"ready": False, "missing": ["approved module outline"], "status": state.status},
        )
    template = _project_template(project)
    lesson_structure = [
        {
            "lesson_id": f"lesson_{index + 1}",
            "module_id": f"module_{min(index // 2 + 1, max(1, len(state.module_outline) or 1))}",
            "title": title,
            "objective": f"Teach learners {title.lower()} using approved source chunks.",
            "review_status": "pending",
        }
        for index, title in enumerate(template.lesson_blueprint)
    ]
    state.lesson_structure = lesson_structure
    state.approvals["lessons"] = False
    state.status = "lessons_pending_review"
    _persist_workflow_state(project, state)
    output = WorkflowOutlineResult(
        project_id=req.project_id,
        proposed_module_outline=state.module_outline,
        proposed_lesson_structure=lesson_structure,
        selected_template_id=state.selected_template_id,
    ).model_dump(mode="json")
    _record(context, tool_name, req.project_id, "Lesson structure proposed.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def update_lesson_structure(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "update_lesson_structure"
    assert_tool_allowed(tool_name)
    req = WorkflowStructureUpdateRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    state = _workflow_state(project)
    state.lesson_structure = req.items
    state.approvals["lessons"] = False
    state.status = "lessons_pending_review"
    _persist_workflow_state(project, state)
    output = WorkflowSelectionResult(project_id=req.project_id, status=state.status, selected_value={"lesson_structure": req.items}).model_dump(mode="json")
    _record(context, tool_name, req.project_id, "Lesson structure updated.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def approve_lesson_structure(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "approve_lesson_structure"
    assert_tool_allowed(tool_name)
    req = WorkflowApprovalRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    state = _workflow_state(project)
    if not state.lesson_structure:
        raise SecurityError("Cannot approve lesson structure without proposed lessons.")
    state.approvals["lessons"] = True
    state.status = "lessons_approved"
    _persist_workflow_state(project, state)
    output = WorkflowSelectionResult(project_id=req.project_id, status=state.status, selected_value={"approved": True}).model_dump(mode="json")
    _record(context, tool_name, req.project_id, "Lesson structure approved.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def select_assessment_model(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "select_assessment_model"
    assert_tool_allowed(tool_name)
    req = WorkflowModelSelectionRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    state = _workflow_state(project)
    state.assessment_model = req.model
    state.approvals["assessment_model"] = True
    state.status = "assessment_model_approved"
    _persist_workflow_state(project, state)
    output = WorkflowSelectionResult(project_id=req.project_id, status=state.status, selected_value=req.model).model_dump(mode="json")
    _record(context, tool_name, req.project_id, "Assessment model selected.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def select_interaction_model(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "select_interaction_model"
    assert_tool_allowed(tool_name)
    req = WorkflowModelSelectionRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    state = _workflow_state(project)
    state.interaction_model = req.model
    state.approvals["interaction_model"] = True
    state.status = "interaction_model_approved"
    _persist_workflow_state(project, state)
    output = WorkflowSelectionResult(project_id=req.project_id, status=state.status, selected_value=req.model).model_dump(mode="json")
    _record(context, tool_name, req.project_id, "Interaction model selected.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def check_generation_readiness(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "check_generation_readiness"
    assert_tool_allowed(tool_name)
    req = WorkflowApprovalRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    state = _workflow_state(project)
    state.source_chunk_count = max(state.source_chunk_count, len(_source_chunks_for_project(project)))
    readiness = CourseDiscoveryWorkflow().check_generation_readiness(state)
    _persist_workflow_state(project, state)
    output = GenerationReadinessResult(
        project_id=req.project_id,
        ready=readiness["ready"],
        missing=readiness["missing"],
        status=readiness["status"],
    ).model_dump(mode="json")
    _record(context, tool_name, req.project_id, "Generation readiness checked.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def generate_course_with_codex(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "generate_course_with_codex"
    assert_tool_allowed(tool_name)
    req = WorkflowApprovalRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    template = _project_template(project)
    state = _workflow_state(project)
    state.selected_template_id = template.template_id
    state.source_chunk_count = max(state.source_chunk_count, len(_source_chunks_for_project(project)))
    readiness = CourseDiscoveryWorkflow().check_generation_readiness(state)
    if not readiness["ready"]:
        _persist_workflow_state(project, state)
        return _error_return(tool_name, context, req.model_dump(), "not_ready", readiness)
    state.status = "generation_started"
    _persist_workflow_state(project, state)
    contract = CodexGenerationContractBuilder().build(
        project_id=req.project_id,
        course_brief=_course_brief_from_state(state),
        selected_template=_template_snapshot(template),
        approved_module_outline=state.module_outline,
        approved_lesson_structure=state.lesson_structure,
        assessment_model=state.assessment_model,
        interaction_model=state.interaction_model,
        source_chunks=_source_chunks_for_project(project),
        export_targets=state.answers.get("export_targets", {}).get("value", ["html", "scorm"]),
    )
    state.status = "generated"
    _persist_workflow_state(project, state)
    output = CodexGenerationContractResult(project_id=req.project_id, codex_payload=contract).model_dump(mode="json")
    _record(context, tool_name, req.project_id, "Codex generation contract prepared.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def get_course_workflow_status(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "get_course_workflow_status"
    assert_tool_allowed(tool_name)
    req = WorkflowApprovalRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    state = _workflow_state(project)
    output = WorkflowStatusResult(
        project_id=req.project_id,
        status=state.status,
        answers={k: DiscoveryAnswer.model_validate(v) for k, v in state.answers.items()},
        selected_template_id=state.selected_template_id,
        module_outline=state.module_outline,
        lesson_structure=state.lesson_structure,
        assessment_model=state.assessment_model,
        interaction_model=state.interaction_model,
        approvals=state.approvals,
        source_chunk_count=state.source_chunk_count,
    ).model_dump(mode="json")
    _record(context, tool_name, req.project_id, "Course workflow status returned.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def _upload_path(upload_id: str) -> Path:
    upload_root = Path(os.getenv("UPLOAD_DIR", "course_mcp_output/uploads")).resolve()
    path = (upload_root / upload_id).resolve()
    path.relative_to(upload_root)
    return path


def _extract_source_text(path: Path, source_type: str) -> tuple[str, list[str], list[str]]:
    if not path.exists():
        return "", [], ["Upload ID was not found in the controlled upload directory."]
    extracted = extract_source(path, source_type)
    return extracted.text, extracted.references, extracted.warnings


def ingest_course_source(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "ingest_course_source"
    assert_tool_allowed(tool_name)
    try:
        req = SourceIngestRequest.model_validate(payload)
    except ValidationError as exc:
        return safe_error(exc)
    project = _project_or_raise(context, req.project_id)
    path = _upload_path(req.upload_id)
    text, refs, warnings = _extract_source_text(path, req.source_type)
    stored_source = (
        store_path(
            path,
            tenant_id=context.tenant_id,
            kind="sources",
            object_id=f"source_{hashlib.sha256(path.read_bytes()).hexdigest()[:16]}",
            filename=path.name,
        )
        if path.is_file()
        else None
    )
    source = {
        "source_id": f"source_{len(project.get('sources', [])) + 1}",
        "source_type": req.source_type,
        "title": Path(req.upload_id).stem,
        "extracted_text": text[:60_000],
        "page_references": refs,
        "warnings": warnings,
        "object_storage": stored_source,
    }
    project.setdefault("sources", []).append(source)
    save_project(project)
    output = SourceIngestResult(
        project_id=req.project_id,
        source_id=source["source_id"],
        source_type=req.source_type,
        title=source["title"],
        extracted_text_preview=text[:240].strip().lstrip("#").strip(),
        page_references=refs,
        warnings=warnings,
    ).model_dump(mode="json")
    _record(context, tool_name, req.project_id, "Course source ingested.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def _source_text(project: dict[str, Any]) -> str:
    return "\n\n".join(source.get("extracted_text", "") for source in project.get("sources", []))[:60_000]


def _source_refs_for_project(project: dict[str, Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for source in project.get("sources", []):
        source_id = str(source.get("source_id", "source_1"))
        for reference in (source.get("page_references") or ["line:1"])[:3]:
            refs.append({"source_id": source_id, "reference": str(reference)})
    return refs


def _inject_source_refs(blocks: list[dict[str, Any]], source_refs: list[dict[str, str]]) -> list[dict[str, Any]]:
    if not source_refs:
        return blocks
    first_ref = source_refs[0]
    enriched = []
    for block in blocks:
        copy = dict(block)
        copy.setdefault("source_refs", [first_ref])
        enriched.append(copy)
    return enriched


_ACTIVITY_TYPE_TO_PLAYER = {
    "decision_tree": "scenario_decision_tree",
    "drag_drop_sort": "drag_and_drop",
    "hotspot": "hotspot_image",
    "interactive_video_checkpoint": "interactive_video",
}


def _player_activity(activity: dict[str, Any]) -> dict[str, Any]:
    """Map a course_schema_v2 Activity onto the shape the SCORM player renders."""
    data = dict(activity.get("data") or {})
    items = data.pop("items", None) or data.pop("cards", None) or data.pop("steps", None) or []
    raw_type = activity.get("type", "reflection")
    mapped = dict(data)
    mapped.update(
        {
            "activity_id": activity.get("id"),
            "activity_type": _ACTIVITY_TYPE_TO_PLAYER.get(raw_type, raw_type),
            "title": activity.get("title"),
            "objective": activity.get("instructions"),
            "objective_ids": activity.get("objective_ids", []),
            "items": items,
        }
    )
    return mapped


def _player_media(media: dict[str, Any] | None) -> dict[str, Any] | None:
    """Map an authored MediaAsset onto the src the packaged player loads."""
    if not media:
        return None
    src = media.get("url")
    if media.get("upload_id"):
        src = f"assets/media/{media['upload_id']}"
    return {
        "kind": media.get("kind", "image"),
        "src": src,
        "alt": media.get("alt") or media.get("caption") or "",
        "caption": media.get("caption") or "",
    }


def _course_payload_from_submission(project: dict[str, Any], content: dict[str, Any]) -> dict[str, Any]:
    """Convert validated agent-authored course content into the exporter/player payload."""
    objective_text = {
        obj.get("id", ""): obj.get("text", "") for obj in content.get("learning_objectives", [])
    }
    modules = []
    for module in content.get("modules", []):
        lessons = []
        for lesson in module.get("lessons", []):
            first_objective = next(iter(lesson.get("objective_ids", [])), "")
            blocks = []
            for block in lesson.get("content_blocks", []):
                block = dict(block)
                media = _player_media(block.get("media"))
                if media:
                    block["media"] = media
                else:
                    block.pop("media", None)
                blocks.append(block)
            lessons.append(
                {
                    "id": lesson.get("id"),
                    "title": lesson.get("title"),
                    "duration_minutes": lesson.get("duration_minutes", 10),
                    "objective_ids": lesson.get("objective_ids", []),
                    "objective": objective_text.get(first_objective) or lesson.get("title", ""),
                    "content_blocks": blocks,
                    "activities": [_player_activity(act) for act in lesson.get("activities", [])],
                    "quiz_questions": lesson.get("quiz_questions", []),
                }
            )
        modules.append(
            {
                "id": module.get("id"),
                "title": module.get("title"),
                "duration_minutes": module.get("duration_minutes", 15),
                "objective_ids": module.get("objective_ids", []),
                "lessons": lessons,
                "activities": [_player_activity(act) for act in module.get("activities", [])],
            }
        )
    payload = {
        "course_title": content.get("course_title", project["course_title"]),
        "course_slug": content.get("course_slug", project["project_id"].replace("_", "-")),
        "audience": content.get("audience", project["audience"]),
        "difficulty": content.get("difficulty", "beginner"),
        "language": content.get("language", project["language"]),
        "estimated_duration_minutes": content.get("estimated_duration_minutes", 45),
        "learning_objectives": content.get("learning_objectives", []),
        "modules": modules,
        "final_assessment": content.get("final_assessment"),
        "source_refs": content.get("source_refs", []),
    }
    if content.get("theme"):
        payload["theme"] = content["theme"]
    if content.get("game_options"):
        payload["game_options"] = content["game_options"]
    return payload


def _media_requests_for_content(content: dict[str, Any]) -> list[dict[str, Any]]:
    """List the places where the course wants an image/video the author has not supplied yet."""
    requests: list[dict[str, Any]] = []
    upload_dir = Path(os.getenv("UPLOAD_DIR", "/app/output/uploads"))
    for module in content.get("modules", []):
        for lesson in module.get("lessons", []):
            for block in lesson.get("content_blocks", []):
                media = block.get("media")
                if block.get("type") == "media_placeholder" and not media:
                    requests.append(
                        {
                            "lesson_id": lesson.get("id"),
                            "block_id": block.get("id"),
                            "request": f"Supply an image or video for '{lesson.get('title')}': {block.get('text', '')[:140]}",
                        }
                    )
                elif media and media.get("upload_id") and not (upload_dir / media["upload_id"]).exists():
                    requests.append(
                        {
                            "lesson_id": lesson.get("id"),
                            "block_id": block.get("id"),
                            "request": f"Upload '{media['upload_id']}' so it can be packaged into the course zip.",
                        }
                    )
    return requests


def submit_course_content(payload: dict, context: RequestContext) -> dict[str, Any]:
    """Store the full course authored by the calling agent (Claude Code / Codex).

    The MCP server validates structure and quality but never writes the lesson
    prose itself: the calling agent's subscription does the authoring work.
    """
    tool_name = "submit_course_content"
    assert_tool_allowed(tool_name)
    req = SubmitCourseContentRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    duration = sum(int(module.get("duration_minutes", 10) or 10) for module in req.modules)
    course = CourseProjectV2.model_validate(
        {
            "course_id": req.project_id,
            "course_title": project["course_title"],
            "course_slug": req.project_id.replace("_", "-"),
            "audience": project["audience"],
            "difficulty": req.difficulty,
            "language": project.get("language", "English"),
            "estimated_duration_minutes": max(10, duration),
            "status": "content_generated",
            "learning_objectives": req.learning_objectives,
            "modules": req.modules,
            "final_assessment": req.final_assessment,
        }
    )
    content = course.model_dump(mode="json")
    if req.theme:
        content["theme"] = req.theme
    content["game_options"] = GameOptions.model_validate(req.game_options or {}).model_dump(mode="json")
    add_artifact(project, "course_content", content)
    quality = validate_course_v2_quality(_course_payload_from_submission(project, content))
    lesson_count = sum(len(module.lessons) for module in course.modules)
    activity_count = sum(
        len(lesson.activities) for module in course.modules for lesson in module.lessons
    ) + sum(len(module.activities) for module in course.modules)
    quiz_count = sum(len(lesson.quiz_questions) for module in course.modules for lesson in module.lessons)
    if course.final_assessment:
        quiz_count += len(course.final_assessment.questions)
    output = SubmitCourseContentResult(
        project_id=req.project_id,
        module_count=len(course.modules),
        lesson_count=lesson_count,
        activity_count=activity_count,
        quiz_question_count=quiz_count,
        quality_score=quality["score"],
        quality_status=quality["status"],
        quality_issues=quality["issues"],
        media_requests=_media_requests_for_content(content),
    ).model_dump(mode="json")
    _record(context, tool_name, req.project_id, "Agent-authored course content submitted and validated.")
    return _safe_return(tool_name, context, {"project_id": req.project_id}, output)


def submit_course_module(payload: dict, context: RequestContext) -> dict[str, Any]:
    """Accept one authored module at a time so the calling agent can parallelise.

    Modules accumulate in a draft artifact (idempotent by module id). Once every
    planned module has arrived, the full course is assembled and validated through
    the same path as submit_course_content.
    """
    tool_name = "submit_course_module"
    assert_tool_allowed(tool_name)
    req = SubmitCourseModuleRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    from .course_schema_v2 import Module as ModuleModel

    module = ModuleModel.model_validate(req.module).model_dump(mode="json")

    draft_artifact = latest_artifact(project, "course_module_draft")
    draft = copy.deepcopy((draft_artifact or {}).get("payload")) or {
        "modules": {},
        "learning_objectives": {},
        "final_assessment": None,
        "difficulty": None,
        "theme": None,
        "game_options": None,
        "expected_module_count": None,
    }
    draft["modules"][module["id"]] = module
    for objective in req.learning_objectives:
        if isinstance(objective, dict) and objective.get("id"):
            draft["learning_objectives"][objective["id"]] = objective
    if req.final_assessment is not None:
        draft["final_assessment"] = req.final_assessment
    for field_name in ("difficulty", "theme", "game_options"):
        value = getattr(req, field_name)
        if value is not None:
            draft[field_name] = value
    if req.expected_module_count:
        draft["expected_module_count"] = req.expected_module_count

    state = _workflow_state(project)
    expected = draft.get("expected_module_count") or (
        len(state.module_outline) if state.module_outline else None
    )
    planned_ids = [
        item.get("module_id") or f"module_{index + 1}"
        for index, item in enumerate(state.module_outline or [])
    ]
    submitted_ids = sorted(draft["modules"])
    missing = [module_id for module_id in planned_ids if module_id not in submitted_ids]
    complete = bool(expected) and len(submitted_ids) >= int(expected)
    add_artifact(project, "course_module_draft", draft)

    if complete:
        modules_sorted = [draft["modules"][module_id] for module_id in sorted(draft["modules"])]
        full_payload = {
            "project_id": req.project_id,
            "learning_objectives": list(draft["learning_objectives"].values()),
            "modules": modules_sorted,
            "final_assessment": draft.get("final_assessment"),
            "difficulty": draft.get("difficulty") or "beginner",
            "theme": draft.get("theme"),
            "game_options": draft.get("game_options") or {},
        }
        if not full_payload["theme"]:
            full_payload.pop("theme")
        final_result = submit_course_content(full_payload, context)
        if not final_result.get("ok"):
            return final_result
        merged = dict(final_result["data"])
        merged.update(
            {
                "module_id": module["id"],
                "modules_submitted": len(submitted_ids),
                "expected_module_count": expected,
                "complete": True,
                "missing_module_ids": [],
            }
        )
        _record(context, tool_name, req.project_id, f"Final module {module['id']} submitted; course assembled.")
        return _safe_return(tool_name, context, {"project_id": req.project_id, "module_id": module["id"]}, merged)

    output = SubmitCourseModuleResult(
        project_id=req.project_id,
        module_id=module["id"],
        modules_submitted=len(submitted_ids),
        expected_module_count=expected,
        complete=False,
        missing_module_ids=missing or [f"{expected - len(submitted_ids)} more module(s)"] if expected else missing,
    ).model_dump(mode="json")
    _record(context, tool_name, req.project_id, f"Module {module['id']} submitted ({len(submitted_ids)}/{expected or '?'}).")
    return _safe_return(tool_name, context, {"project_id": req.project_id, "module_id": module["id"]}, output)


MEDIA_UPLOAD_MAX_BYTES = 8 * 1024 * 1024
_VIDEO_EXTENSIONS = {".mp4", ".webm"}


def upload_media_asset(payload: dict, context: RequestContext) -> dict[str, Any]:
    """Receive a generated image/video from the calling agent into the controlled upload dir.

    The agent's own subscription generated the asset; the MCP only stores and
    packages it, so no generation cost lands on the server.
    """
    tool_name = "upload_media_asset"
    assert_tool_allowed(tool_name)
    req = UploadMediaAssetRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    raw = req.content_base64
    if "," in raw[:80]:
        raw = raw.split(",", 1)[1]
    try:
        blob = base64.b64decode(raw, validate=True)
    except Exception as exc:  # noqa: BLE001
        return _error_return(tool_name, context, {"project_id": req.project_id}, "invalid_base64", {"message": str(exc)})
    if len(blob) > MEDIA_UPLOAD_MAX_BYTES:
        return _error_return(
            tool_name,
            context,
            {"project_id": req.project_id},
            "file_too_large",
            {"max_bytes": MEDIA_UPLOAD_MAX_BYTES, "got_bytes": len(blob)},
        )
    upload_dir = Path(os.getenv("UPLOAD_DIR", "/app/output/uploads"))
    upload_dir.mkdir(parents=True, exist_ok=True)
    tenant_prefix = re.sub(r"[^a-zA-Z0-9_-]", "-", context.tenant_id)[:40] or "tenant"
    tenant_files = list(upload_dir.glob(f"{tenant_prefix}--*"))
    used_bytes = sum(path.stat().st_size for path in tenant_files if path.is_file())
    quota_bytes = int(os.getenv("TENANT_UPLOAD_QUOTA_BYTES", str(100 * 1024 * 1024)))
    if used_bytes + len(blob) > quota_bytes:
        return _error_return(
            tool_name,
            context,
            {"project_id": req.project_id},
            "tenant_upload_quota_exceeded",
            {"quota_bytes": quota_bytes, "used_bytes": used_bytes, "requested_bytes": len(blob)},
        )
    stored_name = f"{tenant_prefix}--{req.filename}"
    target = (upload_dir / stored_name).resolve()
    if not str(target).startswith(str(upload_dir.resolve())):
        raise SecurityError("Upload escapes the controlled upload directory")
    target.write_bytes(blob)
    stored_media = store_path(
        target,
        tenant_id=context.tenant_id,
        kind="media",
        object_id=f"media_{hashlib.sha256(blob).hexdigest()[:16]}",
        filename=stored_name,
    )
    suffix = target.suffix.lower()
    output = UploadMediaAssetResult(
        project_id=req.project_id,
        upload_id=stored_name,
        size_bytes=len(blob),
        kind="video" if suffix in _VIDEO_EXTENSIONS else "image",
    ).model_dump(mode="json")
    add_artifact(project, "media_upload", stored_media)
    _record(context, tool_name, req.project_id, f"Media asset uploaded: {req.filename}")
    return _safe_return(tool_name, context, {"project_id": req.project_id, "filename": req.filename}, output)


def get_media_briefs(payload: dict, context: RequestContext) -> dict[str, Any]:
    """Return deterministic image briefs + video slots for the calling agent to fulfil."""
    tool_name = "get_media_briefs"
    assert_tool_allowed(tool_name)
    req = MediaBriefsRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    content_artifact = latest_artifact(project, "course_content")
    if not content_artifact:
        return _error_return(
            tool_name,
            context,
            req.model_dump(),
            "content_not_submitted",
            {"message": "Submit course content first; briefs are composed from the authored lessons."},
        )
    briefs = build_media_briefs(content_artifact.get("payload", {}))
    output = MediaBriefsResult(
        project_id=req.project_id,
        image_briefs=briefs["image_briefs"],
        video_slots=briefs["video_slots"],
    ).model_dump(mode="json")
    _record(context, tool_name, req.project_id, "Media briefs composed.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def attach_media(payload: dict, context: RequestContext) -> dict[str, Any]:
    """Attach an uploaded/linked media asset to one content block without resubmitting the course."""
    tool_name = "attach_media"
    assert_tool_allowed(tool_name)
    req = AttachMediaRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    content_artifact = latest_artifact(project, "course_content")
    if not content_artifact:
        return _error_return(tool_name, context, req.model_dump(), "content_not_submitted", {})
    media = MediaAsset.model_validate(
        {"kind": req.kind, "upload_id": req.upload_id, "url": req.url, "alt": req.alt, "caption": req.caption}
    ).model_dump(mode="json")
    content = copy.deepcopy(content_artifact.get("payload", {}))
    attached = False
    for module in content.get("modules", []):
        for lesson in module.get("lessons", []):
            for block in lesson.get("content_blocks", []):
                if isinstance(block, dict) and block.get("id") == req.block_id:
                    block["media"] = media
                    attached = True
    if not attached:
        return _error_return(tool_name, context, req.model_dump(), "block_not_found", {"block_id": req.block_id})
    add_artifact(project, "course_content", content)
    output = AttachMediaResult(
        project_id=req.project_id, block_id=req.block_id, attached=True, media=media
    ).model_dump(mode="json")
    _record(context, tool_name, req.project_id, f"Media attached to block {req.block_id}.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def _project_course_payload(project: dict[str, Any]) -> dict[str, Any]:
    content_artifact = latest_artifact(project, "course_content")
    if content_artifact:
        return _course_payload_from_submission(project, content_artifact.get("payload", {}))
    lessons_artifact = latest_artifact(project, "lessons")
    assessment_artifact = latest_artifact(project, "assessment")
    activities = [
        artifact.get("payload", {})
        for artifact in project.get("artifacts", [])
        if artifact.get("artifact_type") == "activity"
    ]
    lesson_payload = (lessons_artifact or {}).get("payload", {})
    lessons = lesson_payload.get("lessons", [])
    source_refs = _source_refs_for_project(project)
    lesson_rows = [
        {
            "id": lesson.get("lesson_id", f"lesson_{index}"),
            "title": lesson.get("lesson_title", "Lesson"),
            "duration_minutes": lesson.get("duration_minutes", 10),
            "objective_ids": ["lo_apply"],
            "objective": lesson.get("objective", "Complete the lesson objective."),
            "content_blocks": _inject_source_refs(
                lesson.get(
                    "content_blocks",
                    [
                        {"id": "cb_intro", "type": "intro", "text": lesson.get("objective", "Start the lesson.")},
                        {
                            "id": "cb_explanation",
                            "type": "explanation",
                            "text": "Review the standard, connect it to the learner's work, and identify the decision points.",
                        },
                        {
                            "id": "cb_example",
                            "type": "example",
                            "text": "Use a realistic workplace example to show what good performance looks like.",
                        },
                        {
                            "id": "cb_practice",
                            "type": "practice",
                            "text": "Complete a short practice activity before moving to the assessment.",
                        },
                        {"id": "cb_summary", "type": "summary", "text": "Summarize the action learners should take."},
                    ],
                ),
                source_refs,
            ),
            "activities": activities,
            "quiz_questions": [],
        }
        for index, lesson in enumerate(lessons, start=1)
    ]
    objective_ids = ["lo_identify", "lo_apply", "lo_evaluate"]
    if len(lesson_rows) < 6:
        source_hint = _source_text(project)[:600] or (
            f"{project['course_title']} requires learners to understand the standard, "
            "apply it in realistic situations, and make safe decisions under review."
        )
        lesson_specs = [
            {
                "title": "Purpose and risk context",
                "objective": "Identify the purpose, risks, and expected learner decisions.",
                "intro": f"Use the source to explain why this topic matters in the learner's job. {source_hint}",
                "explanation": "Map the business, safety, or compliance risk to the learner action that prevents it.",
                "example": "A minor shortcut creates a larger operational problem if no one verifies the standard first.",
                "practice": "Ask the learner to name the risk and the consequence before choosing an action.",
                "summary": "The learner should leave knowing why the rule exists and when it matters.",
            },
            {
                "title": "Key standards and terms",
                "objective": "Explain the core standards, terms, and evidence learners must use.",
                "intro": "Define the critical terms in plain language and tie each one to the source evidence.",
                "explanation": "Separate required evidence from optional context so the learner knows what to look for.",
                "example": "Show how a document, checklist, or system record proves the standard was followed.",
                "practice": "Have the learner match each term to the correct evidence artifact.",
                "summary": "The learner should be able to recognize the exact terms used in the source.",
            },
            {
                "title": "Step-by-step workflow",
                "objective": "Apply the workflow in the correct sequence.",
                "intro": "Break the task into ordered steps that can be followed under pressure.",
                "explanation": "Highlight the first, second, and final action so the learner does not improvise the sequence.",
                "example": "A step is skipped, the process drifts, and the output no longer meets the standard.",
                "practice": "Ask the learner to reorder the workflow and explain why each step happens in that order.",
                "summary": "The learner should remember the sequence and the reason behind it.",
            },
            {
                "title": "Common mistakes",
                "objective": "Differentiate safe actions from risky shortcuts.",
                "intro": "Focus on the most likely errors and why they happen in day-to-day work.",
                "explanation": "Show the difference between a safe correction and a shortcut that creates hidden risk.",
                "example": "A rushed worker ignores a verification step and creates an avoidable incident.",
                "practice": "Present a wrong action and ask the learner to correct it using the standard.",
                "summary": "The learner should be able to spot unsafe shortcuts before they spread.",
            },
            {
                "title": "Scenario practice",
                "objective": "Evaluate a realistic scenario and choose the best response.",
                "intro": "Place the learner in a realistic situation with competing pressures and incomplete information.",
                "explanation": "Require the learner to choose, justify, and defend the response using the source.",
                "example": "A customer, passenger, or colleague wants a faster answer that conflicts with the rule.",
                "practice": "Ask the learner to choose the best response and explain the tradeoff.",
                "summary": "The learner should be ready to act in a real-world scenario.",
            },
            {
                "title": "Readiness check",
                "objective": "Demonstrate readiness through practice and assessment review.",
                "intro": "Use a short checkpoint to confirm the learner can explain and apply the standard independently.",
                "explanation": "Review the strongest signals that the learner is ready to proceed.",
                "example": "The learner compares a correct answer against a near miss and explains the difference.",
                "practice": "Ask for a final decision, a reason, and a short confidence statement.",
                "summary": "The learner should finish with a concise readiness checklist and a next step.",
            },
        ]
        detailed_rows = []
        for index, spec in enumerate(lesson_specs, start=1):
            objective_id = objective_ids[(index - 1) % len(objective_ids)]
            detailed_rows.append(
                {
                    "id": f"lesson_{index}",
                    "title": spec["title"],
                    "duration_minutes": 8,
                    "objective_ids": [objective_id],
                    "objective": spec["objective"],
                    "content_blocks": [
                        {
                            "id": f"cb_{index}_intro",
                            "type": "intro",
                            "text": spec["intro"],
                        },
                        {
                            "id": f"cb_{index}_explanation",
                            "type": "explanation",
                            "text": spec["explanation"],
                        },
                        {
                            "id": f"cb_{index}_example",
                            "type": "example",
                            "text": spec["example"],
                        },
                        {
                            "id": f"cb_{index}_practice",
                            "type": "practice",
                            "text": spec["practice"],
                        },
                        {
                            "id": f"cb_{index}_summary",
                            "type": "summary",
                            "text": spec["summary"],
                        },
                    ],
                    "activities": activities,
                    "quiz_questions": [],
                }
            )
            detailed_rows[-1]["content_blocks"] = _inject_source_refs(detailed_rows[-1]["content_blocks"], source_refs)
        lesson_rows = detailed_rows
    questions = (assessment_artifact or {}).get("payload", {}).get("questions", [])
    return {
        "course_title": project["course_title"],
        "course_slug": project["project_id"].replace("_", "-"),
        "audience": project["audience"],
        "difficulty": "beginner",
        "language": project["language"],
        "estimated_duration_minutes": sum(lesson.get("duration_minutes", 10) for lesson in lesson_rows),
        "learning_objectives": [
            {
                "id": "lo_identify",
                "text": f"Identify the key risks and standards in {project['course_title']}.",
                "bloom_level": "remember",
            },
            {
                "id": "lo_apply",
                "text": f"Apply {project['course_title']} correctly in realistic situations.",
                "bloom_level": "apply",
            },
            {
                "id": "lo_evaluate",
                "text": f"Evaluate learner decisions against the expected {project['course_title']} standard.",
                "bloom_level": "evaluate",
            },
        ],
        "modules": [
            {
                "id": f"module_{module_index}",
                "title": module_title,
                "duration_minutes": sum(lesson.get("duration_minutes", 10) for lesson in module_lessons),
                "objective_ids": objective_ids,
                "lessons": module_lessons,
                "activities": activities,
            }
            for module_index, (module_title, module_lessons) in enumerate(
                [
                    ("Foundation", lesson_rows[0:2]),
                    ("Guided Practice", lesson_rows[2:4]),
                    ("Scenario and Assessment", lesson_rows[4:6]),
                ],
                start=1,
            )
        ],
        "final_assessment": {
            "id": "assessment_final",
            "title": "Final Assessment",
            "passing_score": 80,
            "questions": [
                {
                    "id": question.get("id", f"q_{index}").replace("q", "q_")
                    if question.get("id", "").startswith("q")
                    else question.get("id", f"q_{index}"),
                    "type": question.get("type", "mcq"),
                    "objective_ids": question.get("objective_ids", ["lo_apply"]),
                    "question": question.get("question", "What is the best action?"),
                    "options": question.get("options", ["Correct action", "Risky action"]),
                    "correct_answers": [question.get("answer", question.get("options", ["Correct action"])[0])],
                    "explanation": question.get("explanation", "This answer aligns with the learning objective."),
                }
                for index, question in enumerate(questions, start=1)
            ],
        },
    }


def generate_course_blueprint(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "generate_course_blueprint"
    assert_tool_allowed(tool_name)
    req = BlueprintRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    template = _project_template(project)
    outline = generate_outline(
        CourseOutlineRequest(
            topic=project["course_title"],
            audience=project["audience"],
            duration_minutes=req.duration_minutes,
            difficulty=req.difficulty,
            language=project["language"],
            source_text=_source_text(project) or None,
        )
    )
    output = {
        "project_id": req.project_id,
        "template_id": template.template_id,
        "template_name": template.name,
        "learning_objectives": outline["learning_objectives"],
        "modules": [module for module in outline["modules"]],
        "assessment_strategy": outline["assessment_plan"],
        "source_citation_policy": "Every lesson should cite source_id and page/line references when available.",
        "recommended_interactions": list(template.recommended_interactions),
        "quality_rules": template.quality_rules,
    }
    add_artifact(project, "blueprint", output)
    _record(context, tool_name, req.project_id, "Course blueprint generated.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def generate_module_pack(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "generate_module_pack"
    assert_tool_allowed(tool_name)
    req = ModulePackRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    template = _project_template(project)
    blueprint = latest_artifact(project, "blueprint")
    source_modules = (blueprint or {}).get("payload", {}).get("modules", [])
    modules = []
    for index in range(req.module_count):
        source = source_modules[index % len(source_modules)] if source_modules else {}
        modules.append(
            {
                "module_id": f"module_{index + 1}",
                "title": source.get("title", f"Module {index + 1}: {project['course_title']}"),
                "template_id": template.template_id,
                "status": "generated",
                "review_status": "draft",
                "estimated_minutes": 10,
            }
        )
    output = ModulePackResult(project_id=req.project_id, modules=modules).model_dump(mode="json")
    add_artifact(project, "modules", output)
    _record(context, tool_name, req.project_id, "Module pack generated.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def generate_lesson_pack(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "generate_lesson_pack"
    assert_tool_allowed(tool_name)
    req = LessonPackRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    template = _project_template(project)
    module_title = f"{project['course_title']} {req.module_id.replace('_', ' ').title()}"
    lesson = generate_lesson(
        LessonDraftRequest(
            course_title=project["course_title"],
            module_title=module_title,
            lesson_title="Core lesson",
            objective=f"Apply {project['course_title']} correctly.",
            audience=project["audience"],
        )
    )
    lessons = [
        {
            **lesson,
            "lesson_id": "lesson_1",
            "template_id": template.template_id,
            "citations": [{"source_id": "source_1", "reference": "line:1"}],
            "review_status": "draft",
        }
    ]
    output = LessonPackResult(project_id=req.project_id, module_id=req.module_id, lessons=lessons).model_dump(
        mode="json"
    )
    add_artifact(project, "lessons", output)
    _record(context, tool_name, req.project_id, "Lesson pack generated.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def generate_interactive_activity(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "generate_interactive_activity"
    assert_tool_allowed(tool_name)
    req = ActivityRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    template = _project_template(project)
    items = [
        {"front": "Key idea", "back": req.objective},
        {"front": "Practice", "back": "Apply the idea to a realistic workplace or study scenario."},
    ]
    output = build_activity(
        project_id=req.project_id,
        activity_type=req.activity_type,
        objective=req.objective,
    )
    output.setdefault("items", items)
    output["template_id"] = template.template_id
    ActivityResult.model_validate(output)
    project = _project_or_raise(context, req.project_id)
    add_artifact(project, "activity", output)
    _record(context, tool_name, req.project_id, "Interactive activity generated.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def generate_assessment_bank(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "generate_assessment_bank"
    assert_tool_allowed(tool_name)
    req = AssessmentRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    quiz = generate_quiz(
        QuizBankRequest(
            course_title=project["course_title"],
            learning_objectives=[f"Apply {project['course_title']} safely."],
            question_count=req.question_count,
            difficulty="beginner",
            question_types=["mcq"],
        )
    )
    questions = []
    objective_ids = ["lo_identify", "lo_apply", "lo_evaluate"]
    for index in range(req.question_count):
        question_type = req.question_types[index % len(req.question_types)]
        base = quiz["questions"][index]
        questions.append(
            {
                **base,
                "type": question_type,
                "difficulty": base.get("difficulty", "beginner"),
                "objective_ids": [objective_ids[index % len(objective_ids)]],
                "passing_score": req.passing_score,
                "rubric": [{"criterion": "Objective alignment", "points": 50}],
            }
        )
    output = AssessmentBankResult(
        project_id=req.project_id,
        passing_score=req.passing_score,
        retake_rule=req.retake_rule,
        questions=questions,
    ).model_dump(mode="json")
    add_artifact(project, "assessment", output)
    _record(context, tool_name, req.project_id, "Assessment bank generated.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def generate_roleplay_simulation(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "generate_roleplay_simulation"
    assert_tool_allowed(tool_name)
    req = RoleplayScenarioRequest.model_validate(payload)
    output = generate_roleplay(req)
    _record(context, tool_name, context.request_id or "roleplay", "Role-play simulation generated.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def validate_instructional_quality(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "validate_instructional_quality"
    assert_tool_allowed(tool_name)
    req = QualityValidationRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    output = QualityValidationResult.model_validate(
        validate_course_v2_quality(_project_course_payload(project))
    ).model_dump(mode="json")
    add_artifact(project, "quality_report", output)
    _record(context, tool_name, req.project_id, "Instructional quality validated.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def validate_superior_course_quality(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "validate_superior_course_quality"
    assert_tool_allowed(tool_name)
    req = SuperiorQualityValidationRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    template = _project_template(project)
    report = evaluate_superior_quality(
        _project_course_payload(project),
        domain=template.domain,
        min_source_coverage=float(template.quality_rules.get("min_source_coverage", 0.7)),
    )
    output = SuperiorQualityValidationResult.model_validate(report).model_dump(mode="json")
    add_artifact(project, "superior_quality_report", output)
    _record(context, tool_name, req.project_id, "Superior course quality validated.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def _write_interactive_video_package(project_payload: dict[str, Any], output_dir: Path) -> tuple[Path, list[str]]:
    project = build_video_project_from_course(project_payload)
    renderer = HtmlVideoRenderer()
    package_dir = output_dir / project.video_id
    package_dir.mkdir(parents=True, exist_ok=True)
    rendered = renderer.write_package(project, package_dir)
    static_dir = Path(__file__).with_name("exporters") / "static"
    assets_dir = package_dir / "assets"
    assets_dir.mkdir(exist_ok=True)
    for file_name in ("sentientia_video_engine.js", "sentientia_video_engine.css", "gamification_engine.js"):
        source = static_dir / file_name
        if source.exists():
            shutil.copy2(source, assets_dir / file_name)
    zip_path = package_dir.with_suffix(".zip")
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zf:
        for file_path in [package_dir / "interactive-video.html", package_dir / "captions.vtt", package_dir / "video-project.json"]:
            zf.write(file_path, file_path.name)
        for asset_name in ("sentientia_video_engine.js", "sentientia_video_engine.css", "gamification_engine.js"):
            asset_path = assets_dir / asset_name
            if asset_path.exists():
                zf.write(asset_path, f"assets/{asset_name}")
    return zip_path, list(rendered.values()) + [str(assets_dir / name) for name in ("sentientia_video_engine.js", "sentientia_video_engine.css", "gamification_engine.js") if (assets_dir / name).exists()]


def generate_interactive_video(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "generate_interactive_video"
    assert_tool_allowed(tool_name)
    req = InteractiveVideoRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    if req.template_id:
        project["template_id"] = req.template_id
        save_project(project)
    course_payload = _project_course_payload(project)
    if req.module_id:
        course_payload = {
            **course_payload,
            "modules": [module for module in course_payload.get("modules", []) if module.get("id") == req.module_id or module.get("module_id") == req.module_id],
        } or course_payload
    output_dir = Path(os.getenv("OUTPUT_DIR", "/app/output")).resolve()
    zip_path, file_list = _write_interactive_video_package(course_payload, output_dir)
    output = InteractiveVideoResult(
        project_id=req.project_id,
        video_id=build_video_project_from_course(course_payload).video_id,
        package_path=str(zip_path),
        files=[Path(path).name if Path(path).is_file() else path for path in file_list],
        note="Interactive HTML video package created.",
    ).model_dump(mode="json")
    output["artifact_metadata"] = store_artifact_metadata(
        project_id=req.project_id,
        artifact_type="interactive_video",
        package_path=output["package_path"],
    )
    output["object_storage"] = store_path(
        output["package_path"],
        tenant_id=context.tenant_id,
        kind="exports",
        object_id=f"export_{hashlib.sha256(Path(output['package_path']).read_bytes()).hexdigest()[:16]}",
    )
    output["delivery"] = build_delivery_metadata(
        project_id=req.project_id,
        artifact_type="interactive_video",
        package_path=output["package_path"],
    )
    add_artifact(project, "interactive_video", output)
    _record(context, tool_name, req.project_id, "Interactive video package generated.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def build_export_package(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "build_export_package"
    assert_tool_allowed(tool_name)
    req = ExportPackageRequest.model_validate(payload)
    license_ = License(
        tenant=context.tenant_id,
        tier=context.tier,
        monthly_export_quota=TIER_EXPORT_QUOTAS.get(context.tier, 2),
    )
    quota = check_export_quota(license_)
    if not quota["allowed"]:
        return _error_return(tool_name, context, req.model_dump(), "quota_exceeded", quota)
    branding = dict(req.branding or {}) if license_.white_label else {}
    if context.tier == "free":
        branding = {"footer_text": "Created with Samrat Course MCP — Free plan"}
    project = _project_or_raise(context, req.project_id)
    template = _project_template(project)
    course_payload = _project_course_payload(project)
    quality_report = evaluate_superior_quality(
        course_payload,
        domain=template.domain,
        min_source_coverage=float(template.quality_rules.get("min_source_coverage", 0.7)),
    )
    if quality_report["status"] == "fail":
        project["status"] = "quality_failed"
        save_project(project)
        add_artifact(project, "quality_report", quality_report)
        _record(context, tool_name, req.project_id, "Export blocked by superior quality gate.")
        return _error_return(tool_name, context, req.model_dump(), "quality_failed", quality_report)
    modules = [
        {
            "title": module.get("title", project["course_title"]),
            "lessons": module.get("lessons", []),
            "activities": module.get("activities", []),
            "course_payload": course_payload,
        }
        for module in course_payload.get("modules", [])
    ]
    if req.export_format == "adapt":
        course_payload.setdefault("course_slug", req.project_id.replace("_", "-"))
        output = build_adapt_source_package(
            course_payload,
            os.getenv("OUTPUT_DIR", "/app/output"),
            upload_dir=os.getenv("UPLOAD_DIR", "/app/output/uploads"),
        )
        output["artifact_path"] = output["package_path"]
    elif req.export_format == "h5p":
        output = build_h5p_package(
            {
                "course_title": project["course_title"],
                "course_slug": req.project_id.replace("_", "-"),
                "activities": [
                    activity
                    for module in course_payload.get("modules", [])
                    for activity in module.get("activities", [])
                ],
            },
            os.getenv("OUTPUT_DIR", "/app/output"),
        )
    else:
        media_files = sorted(
            {
                media["src"].removeprefix("assets/media/")
                for module in course_payload.get("modules", [])
                for lesson in module.get("lessons", [])
                for block in lesson.get("content_blocks", [])
                if isinstance(block, dict)
                and (media := block.get("media"))
                and str(media.get("src", "")).startswith("assets/media/")
            }
        )
        output = build_scorm_package(
            ScormPackageRequest(
                course_title=project["course_title"],
                course_slug=req.project_id.replace("_", "-"),
                modules=modules,
                scorm_version=req.scorm_version,
                media_files=media_files,
                branding=branding,
                export_stamp=sign_export(req.project_id, context.tenant_id, context.tier),
            ),
            os.getenv("OUTPUT_DIR", "/app/output"),
        )
    project["status"] = "exported"
    if context.tier != "admin":
        record_export(license_)
    output["quality_report"] = quality_report
    output["artifact_metadata"] = store_artifact_metadata(
        project_id=req.project_id,
        artifact_type=req.export_format,
        package_path=output["package_path"],
    )
    output["object_storage"] = store_path(
        output["package_path"],
        tenant_id=context.tenant_id,
        kind="exports",
        object_id=f"export_{hashlib.sha256(Path(output['package_path']).read_bytes()).hexdigest()[:16]}",
    )
    output["delivery"] = build_delivery_metadata(
        project_id=req.project_id,
        artifact_type=req.export_format,
        package_path=output["package_path"],
    )
    add_artifact(project, "export", output)
    _record(context, tool_name, req.project_id, "Export package generated.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def build_storyline_handoff_package(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "build_storyline_handoff_package"
    assert_tool_allowed(tool_name)
    req = StorylineHandoffRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    course_payload = _project_course_payload(project)
    output = build_storyline_handoff_zip(
        course_payload,
        os.getenv("OUTPUT_DIR", "/app/output"),
        course_slug=req.project_id.replace("_", "-"),
    )
    output["artifact_metadata"] = store_artifact_metadata(
        project_id=req.project_id,
        artifact_type="storyline_handoff",
        package_path=output["package_path"],
    )
    output["delivery"] = build_delivery_metadata(
        project_id=req.project_id,
        artifact_type="storyline_handoff",
        package_path=output["package_path"],
    )
    add_artifact(project, "storyline_handoff", output)
    _record(context, tool_name, req.project_id, "Storyline handoff package generated.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def get_course_generation_status(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "get_course_generation_status"
    assert_tool_allowed(tool_name)
    req = JobStatusRequest.model_validate(payload)
    output = get_job_status(job_id=req.job_id, tenant_id=context.tenant_id)
    return _safe_return(tool_name, context, req.model_dump(), output)


def list_course_artifacts(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "list_course_artifacts"
    assert_tool_allowed(tool_name)
    req = ListArtifactsRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    artifacts = [
        {
            "artifact_id": artifact["artifact_id"],
            "artifact_type": artifact["artifact_type"],
            "created_at": artifact["created_at"],
        }
        for artifact in project.get("artifacts", [])
    ]
    output = ArtifactListResult(
        project_id=req.project_id,
        artifact_types=sorted({artifact["artifact_type"] for artifact in artifacts}),
        artifacts=artifacts,
    ).model_dump(mode="json")
    return _safe_return(tool_name, context, req.model_dump(), output)


def request_publish_approval(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "request_publish_approval"
    assert_tool_allowed(tool_name)
    req = PublishApprovalRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    project["status"] = "needs_review"
    project["reviewer"] = req.reviewer
    project["review_notes"] = req.notes
    save_project(project)
    output = PublishApprovalResult(
        project_id=req.project_id,
        review_status="needs_review",
        published=False,
        next_action="Reviewer must approve outline, lessons, assessment, and export before publishing.",
    ).model_dump(mode="json")
    _record(context, tool_name, req.project_id, "Publish approval requested.")
    return _safe_return(tool_name, context, req.model_dump(), output)


TOOL_REGISTRY = {
    "create_material_ticket": create_material_ticket,
    "generate_chapter_layout": generate_chapter_layout,
    "create_course_project": create_course_project,
    "select_course_template": select_course_template,
    "list_course_templates": list_course_templates,
    "recommend_course_templates": recommend_course_templates,
    "start_course_discovery": start_course_discovery,
    "save_course_brief": save_course_brief,
    "get_next_course_question": get_next_course_question,
    "save_course_discovery_answer": save_course_discovery_answer,
    "propose_course_plan": propose_course_plan,
    "approve_course_plan": approve_course_plan,
    "propose_course_outline": propose_course_outline,
    "update_course_outline": update_course_outline,
    "approve_course_outline": approve_course_outline,
    "propose_lesson_structure": propose_lesson_structure,
    "update_lesson_structure": update_lesson_structure,
    "approve_lesson_structure": approve_lesson_structure,
    "select_assessment_model": select_assessment_model,
    "select_interaction_model": select_interaction_model,
    "check_generation_readiness": check_generation_readiness,
    "generate_course_with_codex": generate_course_with_codex,
    "get_course_workflow_status": get_course_workflow_status,
    "ingest_course_source": ingest_course_source,
    "generate_course_blueprint": generate_course_blueprint,
    "submit_course_content": submit_course_content,
    "submit_course_module": submit_course_module,
    "upload_media_asset": upload_media_asset,
    "get_media_briefs": get_media_briefs,
    "attach_media": attach_media,
    "generate_module_pack": generate_module_pack,
    "generate_lesson_pack": generate_lesson_pack,
    "generate_interactive_activity": generate_interactive_activity,
    "generate_interactive_video": generate_interactive_video,
    "generate_assessment_bank": generate_assessment_bank,
    "generate_roleplay_simulation": generate_roleplay_simulation,
    "validate_instructional_quality": validate_instructional_quality,
    "validate_superior_course_quality": validate_superior_course_quality,
    "build_export_package": build_export_package,
    "build_storyline_handoff_package": build_storyline_handoff_package,
    "get_course_generation_status": get_course_generation_status,
    "list_course_artifacts": list_course_artifacts,
    "request_publish_approval": request_publish_approval,
}


def safe_error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ValidationError):
        return {"ok": False, "error": "validation_error", "details": exc.errors()}
    return {"ok": False, "error": exc.__class__.__name__, "message": str(exc)}
