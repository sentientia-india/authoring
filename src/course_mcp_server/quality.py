from __future__ import annotations

import re
from typing import Any

MEASURABLE_VERBS = {
    "apply",
    "identify",
    "explain",
    "demonstrate",
    "compare",
    "inspect",
    "calculate",
    "classify",
    "select",
    "perform",
    "state",
    "confirm",
    "ask",
    "surface",
    "quantify",
    "secure",
}
VAGUE_VERBS = {"understand", "know", "learn", "appreciate", "familiarize", "aware"}


def _artifact(project: dict[str, Any], kind: str) -> dict[str, Any] | None:
    for artifact in reversed(project.get("artifacts", [])):
        if artifact.get("artifact_type") == kind:
            return artifact.get("payload", {})
    return None


def _words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-zA-Z]{4,}", text.lower())}


def validate_course_quality(project: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    recommendations: list[str] = []
    blueprint = _artifact(project, "blueprint") or {}
    lessons = (_artifact(project, "lessons") or {}).get("lessons", [])
    assessments = (_artifact(project, "assessment") or {}).get("questions", [])
    source_text = "\n".join(source.get("extracted_text", "") for source in project.get("sources", []))
    objectives = blueprint.get("learning_objectives", [])

    for required, payload in {
        "blueprint": blueprint,
        "lessons": lessons,
        "assessment": assessments,
    }.items():
        if not payload:
            issues.append({"check": "completeness", "message": f"Missing {required} content."})

    for objective in objectives:
        first = objective.lower().split(" ", 1)[0].strip(".:")
        if first in VAGUE_VERBS or not (_words(objective) & MEASURABLE_VERBS):
            issues.append({"check": "objective_quality", "message": f"Objective is not measurable: {objective}"})

    objective_terms = set().union(*(_words(objective) for objective in objectives)) if objectives else set()
    lesson_terms = set().union(*(_words(str(lesson)) for lesson in lessons)) if lessons else set()
    assessment_terms = set().union(*(_words(str(question)) for question in assessments)) if assessments else set()
    if objective_terms and not objective_terms.intersection(lesson_terms):
        issues.append({"check": "objective_lesson_alignment", "message": "Lessons do not map to objectives."})
    if objective_terms and not objective_terms.intersection(assessment_terms):
        issues.append({"check": "objective_assessment_alignment", "message": "Assessment does not test objectives."})

    if not source_text:
        issues.append({"check": "source_grounding", "message": "No source material is attached."})
    elif lessons and not any(lesson.get("citations") for lesson in lessons):
        issues.append({"check": "source_grounding", "message": "Lessons are missing source citations."})

    if any(len(str(block)) < 120 for block in lessons):
        issues.append({"check": "content_depth", "message": "One or more lessons are thin."})

    if not any("accessibility" in str(artifact).lower() for artifact in project.get("artifacts", [])):
        recommendations.append("Add alt text, keyboard-friendly interactions, and readable contrast checks.")
    if project.get("compliance_domain"):
        recommendations.append("Run a human compliance review before export or publish approval.")
    recommendations.append("Use scenario-based questions for final assessment, especially for SOP/compliance courses.")

    score = max(0, 100 - len(issues) * 10)
    status = "passed" if score >= 90 else "needs_review" if score >= 60 else "failed"
    return {"score": score, "status": status, "issues": issues, "recommendations": recommendations}
