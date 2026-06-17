from __future__ import annotations

import os
from typing import Any

from pydantic import ValidationError

from .course_generator import generate_lesson, generate_outline, generate_quiz, generate_roleplay
from .exporters.scorm import build_scorm_scaffold
from .schemas import (
    CourseOutlineRequest,
    JobStatusRequest,
    LessonDraftRequest,
    QuizBankRequest,
    RoleplayScenarioRequest,
    ScormPackageRequest,
    ValidateCourseSchemaRequest,
)
from .security import RequestContext, assert_tool_allowed, audit_event, redact_output


def _safe_return(tool_name: str, context: RequestContext, request: Any, output: Any) -> dict[str, Any]:
    safe_output = redact_output(output)
    return {
        "ok": True,
        "data": safe_output,
        "audit": audit_event(tool_name, context, request, safe_output),
    }


def generate_course_outline(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "generate_course_outline"
    assert_tool_allowed(tool_name)
    req = CourseOutlineRequest.model_validate(payload)
    output = generate_outline(req)
    return _safe_return(tool_name, context, req.model_dump(), output)


def generate_lesson_draft(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "generate_lesson_draft"
    assert_tool_allowed(tool_name)
    req = LessonDraftRequest.model_validate(payload)
    output = generate_lesson(req)
    return _safe_return(tool_name, context, req.model_dump(), output)


def generate_quiz_bank(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "generate_quiz_bank"
    assert_tool_allowed(tool_name)
    req = QuizBankRequest.model_validate(payload)
    output = generate_quiz(req)
    return _safe_return(tool_name, context, req.model_dump(), output)


def generate_roleplay_scenario(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "generate_roleplay_scenario"
    assert_tool_allowed(tool_name)
    req = RoleplayScenarioRequest.model_validate(payload)
    output = generate_roleplay(req)
    return _safe_return(tool_name, context, req.model_dump(), output)


def validate_course_schema(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "validate_course_schema"
    assert_tool_allowed(tool_name)
    req = ValidateCourseSchemaRequest.model_validate(payload)
    errors: list[str] = []
    course = req.course
    for key in ("course_title", "modules", "learning_objectives"):
        if key not in course:
            errors.append(f"Missing required key: {key}")
    output = {"valid": not errors, "errors": errors}
    return _safe_return(tool_name, context, req.model_dump(), output)


def build_scorm_package_scaffold(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "build_scorm_package_scaffold"
    assert_tool_allowed(tool_name)
    req = ScormPackageRequest.model_validate(payload)
    output_dir = os.getenv("OUTPUT_DIR", "/app/output")
    output = build_scorm_scaffold(req, output_dir)
    return _safe_return(tool_name, context, req.model_dump(), output)


def get_course_generation_status(payload: dict, context: RequestContext) -> dict[str, Any]:
    tool_name = "get_course_generation_status"
    assert_tool_allowed(tool_name)
    req = JobStatusRequest.model_validate(payload)
    output = {"job_id": req.job_id, "status": "not_found", "message": "Persistent job queue not enabled in MVP skeleton."}
    return _safe_return(tool_name, context, req.model_dump(), output)


TOOL_REGISTRY = {
    "generate_course_outline": generate_course_outline,
    "generate_lesson_draft": generate_lesson_draft,
    "generate_quiz_bank": generate_quiz_bank,
    "generate_roleplay_scenario": generate_roleplay_scenario,
    "validate_course_schema": validate_course_schema,
    "build_scorm_package_scaffold": build_scorm_package_scaffold,
    "get_course_generation_status": get_course_generation_status,
}


def safe_error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ValidationError):
        return {"ok": False, "error": "validation_error", "details": exc.errors()}
    return {"ok": False, "error": exc.__class__.__name__, "message": str(exc)}
