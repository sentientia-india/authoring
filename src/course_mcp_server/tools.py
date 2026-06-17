from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .course_generator import generate_lesson, generate_outline, generate_quiz, generate_roleplay
from .exporters.scorm import build_scorm_scaffold
from .job_store import get_job_status, record_job
from .project_store import add_artifact, create_project, get_project, latest_artifact, save_project
from .schemas import (
    ActivityRequest,
    ActivityResult,
    ArtifactListResult,
    AssessmentBankResult,
    AssessmentRequest,
    BlueprintRequest,
    CourseOutlineRequest,
    CourseProjectRequest,
    CourseProjectResult,
    ExportPackageRequest,
    JobStatusRequest,
    LessonDraftRequest,
    LessonPackRequest,
    LessonPackResult,
    ListArtifactsRequest,
    ModulePackRequest,
    ModulePackResult,
    PublishApprovalRequest,
    PublishApprovalResult,
    QualityValidationRequest,
    QualityValidationResult,
    QuizBankRequest,
    RoleplayScenarioRequest,
    ScormPackageRequest,
    SourceIngestRequest,
    SourceIngestResult,
)
from .security import RequestContext, SecurityError, assert_tool_allowed, audit_event, redact_output


def _safe_return(tool_name: str, context: RequestContext, request: Any, output: Any) -> dict[str, Any]:
    safe_output = redact_output(output)
    return {
        "ok": True,
        "data": safe_output,
        "audit": audit_event(tool_name, context, request, safe_output),
    }


def _project_or_raise(context: RequestContext, project_id: str) -> dict[str, Any]:
    project = get_project(tenant_id=context.tenant_id, project_id=project_id)
    if not project:
        raise SecurityError("Course project not found.")
    return project


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


def _upload_path(upload_id: str) -> Path:
    upload_root = Path(os.getenv("UPLOAD_DIR", "course_mcp_output/uploads")).resolve()
    path = (upload_root / upload_id).resolve()
    path.relative_to(upload_root)
    return path


def _extract_source_text(path: Path, source_type: str) -> tuple[str, list[str], list[str]]:
    if not path.exists():
        return "", [], ["Upload ID was not found in the controlled upload directory."]
    suffix = path.suffix.lower()
    if source_type == "raw_text" or suffix in {".txt", ".md", ".csv"}:
        text = path.read_text(encoding="utf-8", errors="ignore")
        return text, ["line:1"], []
    return (
        path.stem,
        [],
        [
            f"{source_type} ingestion placeholder: controlled upload accepted, "
            "deep extraction worker not configured yet."
        ],
    )


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
    source = {
        "source_id": f"source_{len(project.get('sources', [])) + 1}",
        "source_type": req.source_type,
        "title": Path(req.upload_id).stem,
        "extracted_text": text[:60_000],
        "page_references": refs,
        "warnings": warnings,
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


def generate_course_blueprint(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "generate_course_blueprint"
    assert_tool_allowed(tool_name)
    req = BlueprintRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
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
        "learning_objectives": outline["learning_objectives"],
        "modules": [module for module in outline["modules"]],
        "assessment_strategy": outline["assessment_plan"],
        "source_citation_policy": "Every lesson should cite source_id and page/line references when available.",
    }
    add_artifact(project, "blueprint", output)
    _record(context, tool_name, req.project_id, "Course blueprint generated.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def generate_module_pack(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "generate_module_pack"
    assert_tool_allowed(tool_name)
    req = ModulePackRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    blueprint = latest_artifact(project, "blueprint")
    source_modules = (blueprint or {}).get("payload", {}).get("modules", [])
    modules = []
    for index in range(req.module_count):
        source = source_modules[index % len(source_modules)] if source_modules else {}
        modules.append(
            {
                "module_id": f"module_{index + 1}",
                "title": source.get("title", f"Module {index + 1}: {project['course_title']}"),
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
    _project_or_raise(context, req.project_id)
    items = [
        {"front": "Key idea", "back": req.objective},
        {"front": "Practice", "back": "Apply the idea to a realistic workplace or study scenario."},
    ]
    output = ActivityResult(
        project_id=req.project_id,
        activity_id="activity_1",
        activity_type=req.activity_type,
        title=f"{req.activity_type.replace('_', ' ').title()} Practice",
        objective=req.objective,
        items=items,
    ).model_dump(mode="json")
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
    for index in range(req.question_count):
        question_type = req.question_types[index % len(req.question_types)]
        base = quiz["questions"][index]
        questions.append(
            {
                **base,
                "type": question_type,
                "difficulty": base.get("difficulty", "beginner"),
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
    artifact_types = {artifact["artifact_type"] for artifact in project.get("artifacts", [])}
    issues: list[dict[str, str]] = []
    for required in ("blueprint", "modules", "lessons", "assessment"):
        if required not in artifact_types:
            issues.append({"check": "completeness", "message": f"Missing {required} artifact."})
    if not project.get("sources"):
        issues.append({"check": "source_grounding", "message": "No source document has been ingested."})
    score = max(0, 100 - len(issues) * 12)
    status = "passed" if score >= 90 else "needs_review" if score >= 60 else "failed"
    output = QualityValidationResult(
        score=score,
        status=status,
        issues=issues,
        recommendations=[
            "Review measurable objectives, Bloom level, source citations, accessibility, and compliance language.",
            "Lock approved modules before export or LMS publishing.",
        ],
    ).model_dump(mode="json")
    add_artifact(project, "quality_report", output)
    _record(context, tool_name, req.project_id, "Instructional quality validated.")
    return _safe_return(tool_name, context, req.model_dump(), output)


def build_export_package(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "build_export_package"
    assert_tool_allowed(tool_name)
    req = ExportPackageRequest.model_validate(payload)
    project = _project_or_raise(context, req.project_id)
    lessons_artifact = latest_artifact(project, "lessons")
    lesson_payload = (lessons_artifact or {}).get("payload", {})
    modules = [
        {
            "title": project["course_title"],
            "lessons": [
                {
                    "title": lesson.get("lesson_title", "Lesson"),
                    "objective": lesson.get("objective", "Complete the lesson objective."),
                    "duration_minutes": 10,
                }
                for lesson in lesson_payload.get("lessons", [])
            ],
        }
    ]
    output = build_scorm_scaffold(
        ScormPackageRequest(
            course_title=project["course_title"],
            course_slug=req.project_id.replace("_", "-"),
            modules=modules,
            scorm_version=req.scorm_version,
        ),
        os.getenv("OUTPUT_DIR", "/app/output"),
    )
    project["status"] = "exported"
    add_artifact(project, "export", output)
    _record(context, tool_name, req.project_id, "Export package generated.")
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
    "create_course_project": create_course_project,
    "ingest_course_source": ingest_course_source,
    "generate_course_blueprint": generate_course_blueprint,
    "generate_module_pack": generate_module_pack,
    "generate_lesson_pack": generate_lesson_pack,
    "generate_interactive_activity": generate_interactive_activity,
    "generate_assessment_bank": generate_assessment_bank,
    "generate_roleplay_simulation": generate_roleplay_simulation,
    "validate_instructional_quality": validate_instructional_quality,
    "build_export_package": build_export_package,
    "get_course_generation_status": get_course_generation_status,
    "list_course_artifacts": list_course_artifacts,
    "request_publish_approval": request_publish_approval,
}


def safe_error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ValidationError):
        return {"ok": False, "error": "validation_error", "details": exc.errors()}
    return {"ok": False, "error": exc.__class__.__name__, "message": str(exc)}
