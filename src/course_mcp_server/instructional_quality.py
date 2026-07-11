from __future__ import annotations

import re
from collections import Counter
from typing import Any

MEASURABLE_VERBS = {
    "identify", "explain", "describe", "apply", "demonstrate", "analyze", "compare", "evaluate",
    "create", "select", "calculate", "classify", "diagnose", "perform", "resolve", "prioritize",
    "differentiate", "summarize", "construct", "design", "assess", "verify", "use", "follow",
}

PLACEHOLDER_PHRASES = {
    "explain the concept",
    "give one realistic example",
    "summarize the key takeaway",
    "apply the concept",
    "core lesson",
    "lorem ipsum",
    # Meta-instructions to a course writer that leaked into learner-facing text.
    "use the source to explain",
    "ask the learner to",
    "have the learner",
    "place the learner in",
    "require the learner to",
    "the learner should leave knowing",
    "present a wrong action and ask",
}

REQUIRED_LESSON_BLOCKS = {"intro", "explanation", "example", "practice", "summary"}


def _words(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z'-]+", text.lower())


def _starts_with_measurable_verb(text: str) -> bool:
    words = _words(text)
    if not words:
        return False
    if words[0] in {"to", "the", "a", "an"} and len(words) > 1:
        return words[1] in MEASURABLE_VERBS
    return words[0] in MEASURABLE_VERBS


def _flatten_text(course: dict[str, Any]) -> str:
    parts: list[str] = [str(course.get("course_title", "")), str(course.get("audience", ""))]
    for obj in course.get("learning_objectives", []):
        parts.append(str(obj.get("text", obj) if isinstance(obj, dict) else obj))
    for module in course.get("modules", []):
        parts.append(str(module.get("title", "")))
        for lesson in module.get("lessons", []):
            parts.append(str(lesson.get("title", "")))
            for block in lesson.get("content_blocks", []):
                parts.append(str(block.get("text", "")))
            for activity in lesson.get("activities", []):
                parts.append(str(activity.get("instructions", "")))
    return "\n".join(parts)


def _content_block_types(lesson: dict[str, Any]) -> set[str]:
    return {str(block.get("type", "")).lower() for block in lesson.get("content_blocks", [])}


def _lesson_word_count(lesson: dict[str, Any]) -> int:
    return sum(len(_words(str(block.get("text", "")))) for block in lesson.get("content_blocks", []))


def validate_instructional_quality(course: dict[str, Any]) -> dict[str, Any]:
    """Return a practical quality score for AI-generated e-learning courses.

    This validator is intentionally deterministic so it can run in CI and inside MCP safely.
    It does not call an LLM. Use it as a gate before SCORM export or publishing.
    """
    issues: list[dict[str, str]] = []
    recommendations: list[str] = []
    metrics: dict[str, Any] = {}
    score = 100

    title = str(course.get("course_title", "")).strip()
    modules = course.get("modules", []) or []
    objectives = course.get("learning_objectives", []) or []
    final_assessment = course.get("final_assessment") or {}

    metrics["module_count"] = len(modules)
    metrics["objective_count"] = len(objectives)

    if len(title) < 8:
        issues.append({"severity": "high", "code": "weak_title", "message": "Course title is missing or too short."})
        score -= 8

    if len(objectives) < 3:
        issues.append({"severity": "high", "code": "too_few_objectives", "message": "Course should have at least 3 learning objectives."})
        score -= 12

    non_measurable = []
    objective_ids = set()
    for obj in objectives:
        if isinstance(obj, dict):
            text = str(obj.get("text", ""))
            obj_id = obj.get("id")
            if obj_id:
                objective_ids.add(str(obj_id))
        else:
            text = str(obj)
        if not _starts_with_measurable_verb(text):
            non_measurable.append(text)
    metrics["non_measurable_objectives"] = len(non_measurable)
    if non_measurable:
        issues.append({"severity": "medium", "code": "non_measurable_objectives", "message": f"{len(non_measurable)} objectives do not start with measurable action verbs."})
        score -= min(15, 5 * len(non_measurable))
        recommendations.append("Rewrite objectives to start with measurable verbs such as identify, explain, apply, demonstrate, analyze, or evaluate.")

    if len(modules) < 3:
        issues.append({"severity": "high", "code": "too_few_modules", "message": "Course should have at least 3 modules for a serious 45-60 minute course."})
        score -= 12

    lesson_count = 0
    activity_count = 0
    quiz_count = 0
    thin_lessons = []
    missing_required_blocks = []
    unmapped_lessons = []
    unmapped_questions = []

    for module in modules:
        lessons = module.get("lessons", []) or []
        if not lessons:
            issues.append({"severity": "high", "code": "module_without_lessons", "message": f"Module '{module.get('title', 'untitled')}' has no lessons."})
            score -= 8
        for lesson in lessons:
            lesson_count += 1
            word_count = _lesson_word_count(lesson)
            if word_count < 180:
                thin_lessons.append(str(lesson.get("title", "untitled")))
            block_types = _content_block_types(lesson)
            missing = REQUIRED_LESSON_BLOCKS - block_types
            if missing:
                missing_required_blocks.append(f"{lesson.get('title', 'untitled')}: {', '.join(sorted(missing))}")
            if not lesson.get("objective_ids"):
                unmapped_lessons.append(str(lesson.get("title", "untitled")))
            activity_count += len(lesson.get("activities", []) or [])
            for question in lesson.get("quiz_questions", []) or []:
                quiz_count += 1
                if not question.get("objective_ids"):
                    unmapped_questions.append(str(question.get("id", "question")))
                if len(str(question.get("explanation", ""))) < 40:
                    issues.append({"severity": "medium", "code": "weak_question_explanation", "message": f"Question {question.get('id', '')} has weak feedback/explanation."})
                    score -= 2

    metrics["lesson_count"] = lesson_count
    metrics["activity_count"] = activity_count
    metrics["quiz_question_count"] = quiz_count + len(final_assessment.get("questions", []) or [])
    metrics["thin_lesson_count"] = len(thin_lessons)

    if lesson_count < 6:
        issues.append({"severity": "high", "code": "too_few_lessons", "message": "Course should have at least 6 lessons for a production-quality 45-60 minute course."})
        score -= 12

    if thin_lessons:
        issues.append({"severity": "high", "code": "thin_lessons", "message": f"{len(thin_lessons)} lessons have less than 180 learner-facing words."})
        score -= min(18, 3 * len(thin_lessons))
        recommendations.append("Expand thin lessons with explanation, examples, edge cases, practice, and summary.")

    if missing_required_blocks:
        issues.append({"severity": "medium", "code": "missing_lesson_blocks", "message": f"{len(missing_required_blocks)} lessons are missing required block types."})
        score -= min(15, 2 * len(missing_required_blocks))

    if activity_count < max(1, len(modules)):
        issues.append({"severity": "medium", "code": "too_few_activities", "message": "Each module should include at least one meaningful activity."})
        score -= 8

    if unmapped_lessons:
        issues.append({"severity": "high", "code": "unmapped_lessons", "message": f"{len(unmapped_lessons)} lessons are not mapped to learning objectives."})
        score -= 8

    assessment_questions = final_assessment.get("questions", []) if isinstance(final_assessment, dict) else []
    if len(assessment_questions) < 5:
        issues.append({"severity": "high", "code": "weak_final_assessment", "message": "Final assessment should have at least 5 questions for MVP and 10+ for normal courses."})
        score -= 10

    has_scenario = any(q.get("type") == "scenario" for q in assessment_questions)
    if not has_scenario:
        issues.append({"severity": "medium", "code": "missing_scenario_assessment", "message": "Final assessment should include at least one scenario-based question."})
        score -= 8

    for question in assessment_questions:
        if not question.get("objective_ids"):
            unmapped_questions.append(str(question.get("id", "assessment_question")))
        if len(str(question.get("explanation", ""))) < 40:
            issues.append({"severity": "medium", "code": "weak_assessment_feedback", "message": f"Assessment question {question.get('id', '')} has weak feedback/explanation."})
            score -= 2

    if unmapped_questions:
        issues.append({"severity": "high", "code": "unmapped_questions", "message": f"{len(unmapped_questions)} questions are not mapped to learning objectives."})
        score -= 8

    full_text = _flatten_text(course)
    lower_text = full_text.lower()
    placeholders_found = sorted(phrase for phrase in PLACEHOLDER_PHRASES if phrase in lower_text)
    if placeholders_found:
        issues.append({"severity": "high", "code": "placeholder_content", "message": f"Placeholder phrases found: {', '.join(placeholders_found)}"})
        score -= min(20, 5 * len(placeholders_found))

    word_list = _words(full_text)
    metrics["total_word_count"] = len(word_list)
    if len(word_list) < 1200:
        issues.append({"severity": "high", "code": "course_too_short", "message": "Learner-facing content is too short for a serious course."})
        score -= 12

    common = Counter(w for w in word_list if len(w) > 5).most_common(10)
    metrics["top_terms"] = common
    if common and common[0][1] > max(30, int(len(word_list) * 0.06)):
        issues.append({"severity": "low", "code": "possible_repetition", "message": "One term appears excessively often; check for repetitive AI text."})
        score -= 3

    media_blocks = [block for module in modules for lesson in module.get("lessons", []) for block in lesson.get("content_blocks", []) if block.get("type") == "media_placeholder"]
    missing_alt = [block for block in media_blocks if not block.get("alt_text")]
    metrics["media_block_count"] = len(media_blocks)
    if missing_alt:
        issues.append({"severity": "medium", "code": "missing_alt_text", "message": f"{len(missing_alt)} media blocks are missing alt text."})
        score -= min(8, len(missing_alt) * 2)

    score = max(0, min(100, score))
    if score >= 85 and not any(issue["severity"] == "high" for issue in issues):
        status = "approved"
    elif score >= 65:
        status = "needs_review"
    else:
        status = "failed"

    if status != "approved":
        recommendations.append("Run regeneration for weak lessons and assessments before SCORM export.")

    return {
        "score": score,
        "status": status,
        "issues": issues,
        "recommendations": recommendations,
        "metrics": metrics,
    }
