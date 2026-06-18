from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

GENERIC_PHRASES = [
    "requires learners to understand",
    "in this lesson you will learn",
    "apply this concept",
    "correct application",
    "realistic work situation",
    "standard procedure",
    "core concepts",
    "business value",
    "key takeaway",
]

SCENARIO_TERMS = {
    "airline": ["cabin", "crew", "passenger", "evacuation", "galley", "door", "slide", "brace", "captain", "abin"],
    "healthcare": ["patient", "clinical", "hospital", "claim", "diagnosis", "doctor", "nurse", "record"],
    "sales": ["buyer", "objection", "proposal", "stakeholder", "pipeline", "negotiation", "account"],
    "software": ["screen", "workflow", "button", "dashboard", "login", "api", "configuration"],
}


@dataclass
class QualityIssue:
    code: str
    severity: str
    message: str
    path: str
    recommendation: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
            "recommendation": self.recommendation,
        }


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9 .!?-]+", " ", text.lower())).strip()


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zA-Z]{4,}", text.lower()) if t not in {"this", "that", "with", "from", "lesson", "course", "module", "learners"}}


def _lesson_text(lesson: dict[str, Any]) -> str:
    blocks = lesson.get("content_blocks") or []
    return "\n".join(str(block.get("text", "")) for block in blocks)


def _iter_lessons(course: dict[str, Any]):
    for module_index, module in enumerate(course.get("modules", [])):
        for lesson_index, lesson in enumerate(module.get("lessons", [])):
            yield module_index, lesson_index, lesson


def lesson_similarity_matrix(course: dict[str, Any]) -> list[dict[str, Any]]:
    lessons = [(f"modules[{mi}].lessons[{li}]", lesson.get("title", ""), _plain(_lesson_text(lesson))) for mi, li, lesson in _iter_lessons(course)]
    rows: list[dict[str, Any]] = []
    for i in range(len(lessons)):
        for j in range(i + 1, len(lessons)):
            path_a, title_a, text_a = lessons[i]
            path_b, title_b, text_b = lessons[j]
            ratio = SequenceMatcher(None, text_a, text_b).ratio() if text_a and text_b else 0
            jaccard = len(_tokens(text_a) & _tokens(text_b)) / max(1, len(_tokens(text_a) | _tokens(text_b)))
            rows.append(
                {
                    "lesson_a": title_a,
                    "lesson_b": title_b,
                    "path_a": path_a,
                    "path_b": path_b,
                    "sequence_similarity": round(ratio, 3),
                    "token_similarity": round(jaccard, 3),
                }
            )
    return rows


def repeated_phrase_counts(course: dict[str, Any]) -> dict[str, int]:
    full_text = _plain("\n".join(_lesson_text(lesson) for _, _, lesson in _iter_lessons(course)))
    counts = {}
    for phrase in GENERIC_PHRASES:
        count = full_text.count(phrase)
        if count:
            counts[phrase] = count
    return counts


def source_citation_coverage(course: dict[str, Any]) -> float:
    total_blocks = 0
    cited_blocks = 0
    for _, _, lesson in _iter_lessons(course):
        for block in lesson.get("content_blocks", []):
            total_blocks += 1
            if block.get("source_refs"):
                cited_blocks += 1
    if total_blocks == 0:
        return 0.0
    return cited_blocks / total_blocks


def scenario_specificity_score(course: dict[str, Any], domain: str | None = None) -> float:
    scenario_texts: list[str] = []
    for _, _, lesson in _iter_lessons(course):
        for block in lesson.get("content_blocks", []):
            if block.get("type") == "scenario":
                scenario_texts.append(str(block.get("text", "")))
        for activity in lesson.get("activities", []):
            if activity.get("type") in {"decision_tree", "roleplay", "branching_scenario", "interactive_video_checkpoint"}:
                scenario_texts.append(str(activity.get("instructions", "")) + " " + str(activity.get("data", "")))
    if not scenario_texts:
        return 0.0
    domain_terms = SCENARIO_TERMS.get((domain or "").lower(), [])
    if not domain_terms:
        domain_terms = sorted({term for terms in SCENARIO_TERMS.values() for term in terms})
    text = _plain("\n".join(scenario_texts))
    hits = sum(1 for term in domain_terms if term.lower() in text)
    return min(1.0, hits / max(4, min(10, len(domain_terms))))


def assessment_alignment_score(course: dict[str, Any]) -> float:
    objectives = {obj.get("id") for obj in course.get("learning_objectives", []) if obj.get("id")}
    if not objectives:
        return 0.0
    assessed: set[str] = set()
    for _, _, lesson in _iter_lessons(course):
        for question in lesson.get("quiz_questions", []):
            assessed.update(question.get("objective_ids", []))
    final = course.get("final_assessment") or {}
    for question in final.get("questions", []):
        assessed.update(question.get("objective_ids", []))
    return len(objectives & assessed) / len(objectives)


def interaction_variety_score(course: dict[str, Any]) -> float:
    interactions: list[str] = []
    for _, _, lesson in _iter_lessons(course):
        interactions.extend(activity.get("type", "") for activity in lesson.get("activities", []))
    if not interactions:
        return 0.0
    unique = len(set(interactions))
    return min(1.0, unique / 5)


def evaluate_superior_quality(
    course: dict[str, Any],
    *,
    domain: str | None = None,
    max_lesson_similarity: float = 0.45,
    min_source_coverage: float = 0.7,
) -> dict[str, Any]:
    issues: list[QualityIssue] = []
    similarities = lesson_similarity_matrix(course)
    for row in similarities:
        if row["sequence_similarity"] > max_lesson_similarity or row["token_similarity"] > max_lesson_similarity:
            issues.append(
                QualityIssue(
                    code="LESSON_TOO_SIMILAR",
                    severity="fail",
                    message=f"'{row['lesson_a']}' and '{row['lesson_b']}' are too similar.",
                    path=f"{row['path_a']} <-> {row['path_b']}",
                    recommendation="Regenerate one lesson with a different objective, scenario, example, and activity pattern.",
                )
            )
    repeats = repeated_phrase_counts(course)
    for phrase, count in repeats.items():
        if count > 3:
            issues.append(
                QualityIssue(
                    code="GENERIC_REPEATED_PHRASE",
                    severity="fail" if count > 5 else "warn",
                    message=f"Generic phrase repeated {count} times: {phrase}",
                    path="course.content_blocks",
                    recommendation="Replace template phrasing with source-specific, role-specific language.",
                )
            )
    coverage = source_citation_coverage(course)
    if coverage < min_source_coverage:
        issues.append(
            QualityIssue(
                code="LOW_SOURCE_COVERAGE",
                severity="fail",
                message=f"Only {coverage:.0%} of content blocks include source references.",
                path="course.modules.lessons.content_blocks",
                recommendation="Ground every explanation, scenario, and quiz in source chunks where possible.",
            )
        )
    scenario_score = scenario_specificity_score(course, domain=domain)
    if scenario_score < 0.45:
        issues.append(
            QualityIssue(
                code="WEAK_SCENARIO_SPECIFICITY",
                severity="warn",
                message=f"Scenario specificity is low ({scenario_score:.0%}).",
                path="course.activities/scenarios",
                recommendation="Add role, environment, constraint, consequence, and realistic decision pressure.",
            )
        )
    align = assessment_alignment_score(course)
    if align < 0.8:
        issues.append(
            QualityIssue(
                code="ASSESSMENT_NOT_ALIGNED",
                severity="fail",
                message=f"Assessment covers only {align:.0%} of learning objectives.",
                path="course.final_assessment.questions",
                recommendation="Add questions and scenarios for uncovered objectives.",
            )
        )
    variety = interaction_variety_score(course)
    if variety < 0.5:
        issues.append(
            QualityIssue(
                code="LOW_INTERACTION_VARIETY",
                severity="warn",
                message=f"Interaction variety is low ({variety:.0%}).",
                path="course.modules.lessons.activities",
                recommendation="Mix video checkpoint, decision tree, hotspot, matching, and roleplay activities.",
            )
        )

    penalties = sum(25 if i.severity == "fail" else 8 for i in issues)
    component_scores = {
        "source_grounding": round(coverage * 100),
        "scenario_specificity": round(scenario_score * 100),
        "assessment_alignment": round(align * 100),
        "interaction_variety": round(variety * 100),
        "non_repetition": max(0, 100 - len([i for i in issues if i.code in {"LESSON_TOO_SIMILAR", "GENERIC_REPEATED_PHRASE"}]) * 20),
    }
    score = max(0, min(100, round(sum(component_scores.values()) / len(component_scores) - penalties / 4)))
    status = "fail" if any(i.severity == "fail" for i in issues) else ("needs_review" if issues else "pass")
    return {
        "score": score,
        "status": status,
        "component_scores": component_scores,
        "issues": [issue.to_dict() for issue in issues],
        "similarity_matrix": similarities,
        "repeated_phrases": repeats,
    }


__all__ = [
    "evaluate_superior_quality",
    "lesson_similarity_matrix",
    "repeated_phrase_counts",
    "source_citation_coverage",
    "scenario_specificity_score",
    "assessment_alignment_score",
    "interaction_variety_score",
]
