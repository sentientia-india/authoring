from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class DiscoveryAnswer:
    value: Any
    source: str
    confidence: float = 1.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AIDefaultProvider:
    def answer_question(
        self,
        question: Mapping[str, Any],
        raw_answer: Any,
        context: Mapping[str, Any] | None = None,
        template_defaults: Mapping[str, Any] | None = None,
    ) -> DiscoveryAnswer:
        context = context or {}
        template_defaults = template_defaults or {}
        qid = question["id"]
        qtype = question.get("type", "text")

        if raw_answer is not None and str(raw_answer).strip() != "":
            return DiscoveryAnswer(
                value=self._coerce_user_answer(qtype, raw_answer),
                source="user_provided",
                confidence=1.0,
                reason="User provided this answer.",
            )

        if qid in template_defaults:
            return DiscoveryAnswer(
                value=template_defaults[qid],
                source="template_default",
                confidence=0.9,
                reason="Used the selected template default because the user skipped this question.",
            )

        return self.suggest(question, context)

    def suggest(self, question: Mapping[str, Any], context: Mapping[str, Any] | None = None) -> DiscoveryAnswer:
        context = context or {}
        qid = question["id"]
        qtype = question.get("type", "text")

        if qtype == "boolean":
            default = bool(question.get("default_if_blank", True))
            return DiscoveryAnswer(
                value=default,
                source="ai_suggested",
                confidence=0.82,
                reason="Optional enhancement questions default to Yes unless the template says otherwise.",
            )

        if qtype == "number":
            value = question.get("default_if_blank", 5)
            return DiscoveryAnswer(
                value=value,
                source="ai_suggested",
                confidence=0.75,
                reason="Suggested a practical default based on standard course structure.",
            )

        if qtype == "single_select":
            options = question.get("options", [])
            value = question.get("default_if_blank") or (options[0] if options else None)
            return DiscoveryAnswer(
                value=value,
                source="ai_suggested",
                confidence=0.8,
                reason="Selected the most generally suitable option because the user skipped this question.",
            )

        if qtype == "multi_select":
            value = question.get("default_if_blank") or question.get("recommended_options") or []
            return DiscoveryAnswer(
                value=value,
                source="ai_suggested",
                confidence=0.78,
                reason="Selected recommended options because the user skipped this question.",
            )

        return DiscoveryAnswer(
            value=self._suggest_text(qid, context, question),
            source="ai_suggested",
            confidence=0.72,
            reason="Generated a draft answer from project context and available source summary. User can edit it later.",
        )

    def _coerce_user_answer(self, qtype: str, raw_answer: Any) -> Any:
        if qtype == "boolean":
            normalized = str(raw_answer).strip().lower()
            if normalized in {"y", "yes", "true", "1", "ok", "approve"}:
                return True
            if normalized in {"n", "no", "false", "0"}:
                return False
            return bool(raw_answer)
        if qtype == "number":
            try:
                return int(raw_answer)
            except (TypeError, ValueError):
                return raw_answer
        if qtype == "multi_select" and isinstance(raw_answer, str):
            return [item.strip() for item in raw_answer.split(",") if item.strip()]
        return raw_answer

    def _suggest_text(self, qid: str, context: Mapping[str, Any], question: Mapping[str, Any]) -> str:
        topic = context.get("course_topic") or context.get("detected_topic") or "the uploaded source material"
        audience = context.get("target_audience") or "the intended learners"
        defaults = {
            "course_title": f"{str(topic).title()} Training",
            "course_goal": f"Help {audience} understand, apply, and demonstrate the key procedures from {topic}.",
            "target_learner": audience,
            "target_audience": audience,
            "industry_context": context.get("detected_industry", "General corporate learning"),
            "industry": context.get("detected_industry", "General corporate learning"),
            "source_material": "Use approved uploaded source chunks.",
            "tone": "professional, practical, and scenario-based",
        }
        return defaults.get(qid, question.get("default_if_blank", f"AI-suggested answer for {qid}"))
