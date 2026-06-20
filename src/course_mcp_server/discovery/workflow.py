from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ai_defaults import AIDefaultProvider, DiscoveryAnswer
from .question_flow import COURSE_DISCOVERY_QUESTIONS, get_next_unanswered_question, get_question, get_unanswered_questions


DISCOVERY_STATUSES = [
    "discovery_started",
    "brief_pending",
    "brief_approved",
    "template_selected",
    "outline_pending_review",
    "outline_approved",
    "lessons_pending_review",
    "lessons_approved",
    "assessment_model_pending",
    "assessment_model_approved",
    "interaction_model_pending",
    "interaction_model_approved",
    "ready_for_generation",
    "generation_started",
    "generated",
    "needs_review",
    "approved_for_export",
    "exported",
]


@dataclass
class CourseDiscoveryState:
    project_id: str
    status: str = "discovery_started"
    answers: dict[str, dict[str, Any]] = field(default_factory=dict)
    selected_template_id: str | None = None
    module_outline: list[dict[str, Any]] = field(default_factory=list)
    lesson_structure: list[dict[str, Any]] = field(default_factory=list)
    assessment_model: dict[str, Any] = field(default_factory=dict)
    interaction_model: dict[str, Any] = field(default_factory=dict)
    approvals: dict[str, bool] = field(default_factory=dict)
    source_chunk_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "status": self.status,
            "answers": self.answers,
            "selected_template_id": self.selected_template_id,
            "module_outline": self.module_outline,
            "lesson_structure": self.lesson_structure,
            "assessment_model": self.assessment_model,
            "interaction_model": self.interaction_model,
            "approvals": self.approvals,
            "source_chunk_count": self.source_chunk_count,
        }


class CourseDiscoveryWorkflow:
    def __init__(self, default_provider: AIDefaultProvider | None = None) -> None:
        self.default_provider = default_provider or AIDefaultProvider()

    def start(self, project_id: str) -> CourseDiscoveryState:
        return CourseDiscoveryState(project_id=project_id, status="brief_pending")

    def get_next_question(self, state: CourseDiscoveryState) -> dict[str, Any] | None:
        return get_next_unanswered_question(state.answers)

    def get_question_batch(self, state: CourseDiscoveryState, *, limit: int = 6, stage: str | None = None) -> list[dict[str, Any]]:
        return get_unanswered_questions(state.answers, limit=limit, stage=stage)

    def save_answer(
        self,
        state: CourseDiscoveryState,
        question_id: str,
        raw_answer: Any,
        context: dict[str, Any] | None = None,
        template_defaults: dict[str, Any] | None = None,
    ) -> DiscoveryAnswer:
        question = get_question(question_id)
        answer = self.default_provider.answer_question(question, raw_answer, context, template_defaults)
        state.answers[question_id] = answer.to_dict()
        self._refresh_status(state)
        return answer

    def select_template(self, state: CourseDiscoveryState, template_id: str) -> None:
        state.selected_template_id = template_id
        state.status = "template_selected"

    def approve_brief(self, state: CourseDiscoveryState) -> None:
        missing = self._missing_required_answers_for_stages(state, {"brief"})
        if missing:
            raise ValueError(f"Cannot approve brief. Missing answers: {', '.join(missing)}")
        state.approvals["brief"] = True
        state.status = "brief_approved"

    def set_module_outline(self, state: CourseDiscoveryState, outline: list[dict[str, Any]]) -> None:
        state.module_outline = outline
        state.approvals["outline"] = False
        state.status = "outline_pending_review"

    def approve_outline(self, state: CourseDiscoveryState) -> None:
        if not state.module_outline:
            raise ValueError("Cannot approve outline without module outline.")
        state.approvals["outline"] = True
        state.status = "outline_approved"

    def set_lesson_structure(self, state: CourseDiscoveryState, lessons: list[dict[str, Any]]) -> None:
        state.lesson_structure = lessons
        state.approvals["lessons"] = False
        state.status = "lessons_pending_review"

    def approve_lessons(self, state: CourseDiscoveryState) -> None:
        if not state.lesson_structure:
            raise ValueError("Cannot approve lesson structure without lessons.")
        state.approvals["lessons"] = True
        state.status = "lessons_approved"

    def select_assessment_model(self, state: CourseDiscoveryState, model: dict[str, Any]) -> None:
        state.assessment_model = model
        state.approvals["assessment_model"] = True
        state.status = "assessment_model_approved"

    def select_interaction_model(self, state: CourseDiscoveryState, model: dict[str, Any]) -> None:
        state.interaction_model = model
        state.approvals["interaction_model"] = True
        state.status = "interaction_model_approved"

    def mark_source_chunks_available(self, state: CourseDiscoveryState, count: int) -> None:
        state.source_chunk_count = max(0, int(count))

    def check_generation_readiness(self, state: CourseDiscoveryState) -> dict[str, Any]:
        missing: list[str] = []

        if self._missing_required_answers_for_stages(state, {"brief"}):
            missing.append("required course brief answers")
        if not state.approvals.get("brief"):
            missing.append("brief approval")
        if not state.selected_template_id:
            missing.append("selected template")
        if not state.approvals.get("outline"):
            missing.append("approved module outline")
        if not state.approvals.get("lessons"):
            missing.append("approved lesson structure")
        if not state.approvals.get("assessment_model"):
            missing.append("assessment model")
        if not state.approvals.get("interaction_model"):
            missing.append("interaction model")
        if state.source_chunk_count <= 0:
            missing.append("source chunks")

        ready = not missing
        if ready:
            state.status = "ready_for_generation"
        return {"ready": ready, "missing": missing, "status": state.status}

    def _missing_required_answers_for_stages(self, state: CourseDiscoveryState, stages: set[str]) -> list[str]:
        missing = []
        for q in COURSE_DISCOVERY_QUESTIONS:
            if q.get("stage") in stages and q.get("required") and q["id"] not in state.answers:
                missing.append(q["id"])
        return missing

    def _refresh_status(self, state: CourseDiscoveryState) -> None:
        if not self._missing_required_answers_for_stages(state, {"brief"}) and state.status == "brief_pending":
            state.status = "brief_pending"
