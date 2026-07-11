from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import re

from .ai_defaults import AIDefaultProvider, DiscoveryAnswer
from .question_flow import (
    COURSE_DISCOVERY_QUESTIONS,
    DURATION_PRESETS,
    get_next_unanswered_question,
    get_question,
    get_unanswered_questions,
)


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
    course_plan: dict[str, Any] = field(default_factory=dict)

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
            "course_plan": self.course_plan,
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
        self._expand_essentials(state, question_id, answer.value)
        self._refresh_status(state)
        return answer

    def _expand_essentials(self, state: CourseDiscoveryState, question_id: str, value: Any) -> None:
        """Derive the detailed brief fields from the three essential answers so the
        user never has to answer them individually."""

        def derive(field_id: str, derived_value: Any) -> None:
            if field_id not in state.answers and derived_value not in (None, ""):
                state.answers[field_id] = DiscoveryAnswer(
                    value=derived_value, source="derived", confidence=0.7,
                    reason=f"Derived from {question_id}.",
                ).to_dict()

        if question_id == "course_brief_line" and isinstance(value, str) and value.strip():
            line = value.strip()
            match = re.search(r"(.+?)\s+for\s+(.+)", line, re.IGNORECASE)
            title = (match.group(1) if match else line).strip(" .")
            learner = (match.group(2) if match else "professional learners").strip(" .")
            derive("course_title", title[:120].title() if title.islower() else title[:120])
            derive("target_learner", learner[:120])
            derive("course_goal", f"Apply {title[:90]} confidently in real work situations.")
        elif question_id == "duration_preset":
            preset = DURATION_PRESETS.get(str(value), DURATION_PRESETS["standard"])
            derive("expected_duration", preset["expected_duration"])
            derive("module_count_preference", preset["module_count_preference"])

    def select_template(self, state: CourseDiscoveryState, template_id: str) -> None:
        state.selected_template_id = template_id
        state.status = "template_selected"

    def _backfill_essentials(self, state: CourseDiscoveryState) -> None:
        """Legacy compatibility: callers that answered the detailed brief questions
        directly satisfy the essentials without being re-asked."""
        answers = state.answers
        legacy_keys = ("course_title", "target_learner", "course_goal")
        if "course_brief_line" not in answers and all(key in answers for key in legacy_keys):
            title = answers["course_title"].get("value", "Course")
            learner = answers["target_learner"].get("value", "learners")
            answers["course_brief_line"] = DiscoveryAnswer(
                value=f"{title} for {learner}",
                source="derived",
                confidence=0.6,
                reason="Backfilled from detailed brief answers.",
            ).to_dict()
        if "course_brief_line" in answers:
            for field_id, default in (("duration_preset", "standard"), ("media_plan_mode", "agent_images")):
                if field_id not in answers:
                    answers[field_id] = DiscoveryAnswer(
                        value=default,
                        source="ai_default",
                        confidence=0.5,
                        reason="Default applied at brief approval.",
                    ).to_dict()

    def approve_brief(self, state: CourseDiscoveryState) -> None:
        self._backfill_essentials(state)
        missing = self._missing_required_answers_for_stages(state, {"essentials", "brief"})
        if missing:
            raise ValueError(f"Cannot approve brief. Missing answers: {', '.join(missing)}")
        state.approvals["brief"] = True
        state.status = "brief_approved"

    def build_course_plan(
        self,
        state: CourseDiscoveryState,
        *,
        template_name: str | None = None,
        proposed_modules: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Compose the single confirmation card shown to the user instead of 14 questions."""

        def answer(field_id: str, fallback: Any = None) -> Any:
            entry = state.answers.get(field_id) or {}
            value = entry.get("value")
            return value if value not in (None, "") else fallback

        preset = str(answer("duration_preset", "standard"))
        preset_numbers = DURATION_PRESETS.get(preset, DURATION_PRESETS["standard"])
        modules = proposed_modules or state.module_outline or []
        media_mode = str(answer("media_plan_mode", "agent_images"))
        video_links = [link.strip() for link in str(answer("video_links", "")).split(",") if link.strip()]
        plan = {
            "course_title": answer("course_title", "Generated Course"),
            "audience": answer("target_learner", "professional learners"),
            "goal": answer("course_goal", ""),
            "level": answer("learner_level", "beginner"),
            "duration_minutes": int(answer("expected_duration", preset_numbers["expected_duration"])),
            "module_count": int(answer("module_count_preference", preset_numbers["module_count_preference"])),
            "modules": modules,
            "template": template_name or state.selected_template_id or "auto-selected",
            "assessment": answer("assessment_preference", "mixed"),
            "interactions": answer("interaction_preference", "scenario_based"),
            "media_plan": {
                "images_mode": media_mode,
                "image_briefs_planned": media_mode != "text_only",
                "video_links": video_links,
                "video_slots_planned": media_mode != "text_only",
            },
            "gamification": bool(answer("gamification_enabled", True)),
            "confirmation_prompt": (
                "Here is the full course plan. Reply 'go' to build it exactly like this, "
                "or tell me anything to change (modules, length, media, interactions)."
            ),
        }
        state.course_plan = plan
        return plan

    def approve_course_plan(self, state: CourseDiscoveryState) -> None:
        """One-shot approval: collapses brief, outline, lessons, assessment, and interaction sign-off."""
        if not state.course_plan:
            raise ValueError("No course plan proposed yet. Call propose_course_plan first.")
        missing = self._missing_required_answers_for_stages(state, {"essentials"})
        if missing:
            raise ValueError(f"Cannot approve plan. Missing essentials: {', '.join(missing)}")
        if not state.module_outline and state.course_plan.get("modules"):
            state.module_outline = list(state.course_plan["modules"])
        if not state.lesson_structure:
            state.lesson_structure = [
                {
                    "module_id": module.get("module_id", f"module_{index}"),
                    "lesson_title": module.get("title", f"Module {index}"),
                    "objective": module.get("objective", state.course_plan.get("goal", "")),
                }
                for index, module in enumerate(state.module_outline, start=1)
            ]
        if not state.assessment_model:
            state.assessment_model = {"preference": state.course_plan.get("assessment", "mixed")}
        if not state.interaction_model:
            state.interaction_model = {"preference": state.course_plan.get("interactions", "scenario_based")}
        for key in ("brief", "outline", "lessons", "assessment_model", "interaction_model", "course_plan"):
            state.approvals[key] = True
        state.status = "lessons_approved"

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

        self._backfill_essentials(state)
        if self._missing_required_answers_for_stages(state, {"essentials", "brief"}):
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
