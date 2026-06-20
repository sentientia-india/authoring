from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator
from pydantic import ConfigDict

Difficulty = Literal["beginner", "intermediate", "advanced"]
DeliveryMode = Literal["microlearning", "standard", "simulation", "assessment_first", "refresher"]
InteractionType = Literal[
    "flashcards",
    "accordion",
    "tabs",
    "timeline",
    "hotspot",
    "drag_drop_sort",
    "matching",
    "decision_tree",
    "roleplay",
    "interactive_video",
    "branching_scenario",
    "simulation_stepper",
    "reflection",
]


class ThemeTokens(BaseModel):
    primary: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    secondary: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    accent: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    background: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    surface: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    text: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    danger: str = Field(default="#B42318", pattern=r"^#[0-9a-fA-F]{6}$")
    success: str = Field(default="#067647", pattern=r"^#[0-9a-fA-F]{6}$")
    font_family: str = Field(default="Inter, system-ui, -apple-system, Segoe UI, sans-serif")


class TemplateLayout(BaseModel):
    navigation: Literal["side_rail", "top_tabs", "mission_map", "card_stack"] = "side_rail"
    lesson_shell: Literal["article", "slides", "scenario", "video_scene"] = "article"
    card_density: Literal["compact", "comfortable", "immersive"] = "comfortable"
    mobile_pattern: Literal["bottom_nav", "stepper", "accordion"] = "stepper"


class AssessmentMix(BaseModel):
    mcq: int = Field(default=30, ge=0, le=100)
    multi_select: int = Field(default=10, ge=0, le=100)
    scenario: int = Field(default=30, ge=0, le=100)
    matching: int = Field(default=10, ge=0, le=100)
    short_answer: int = Field(default=20, ge=0, le=100)

    @model_validator(mode="after")
    def total_is_100(self) -> "AssessmentMix":
        total = self.mcq + self.multi_select + self.scenario + self.matching + self.short_answer
        if total != 100:
            raise ValueError(f"assessment mix must equal 100, got {total}")
        return self


class GamificationRules(BaseModel):
    enabled: bool = True
    xp_per_lesson: int = Field(default=50, ge=0, le=10000)
    xp_per_activity: int = Field(default=75, ge=0, le=10000)
    xp_per_correct_answer: int = Field(default=20, ge=0, le=10000)
    streak_bonus: int = Field(default=30, ge=0, le=10000)
    mastery_badge_threshold: int = Field(default=85, ge=0, le=100)
    unlock_mode: Literal["linear", "score_gated", "mission_map"] = "linear"
    leaderboard: Literal["off", "anonymous", "team", "individual"] = "off"


class TemplatePack(BaseModel):
    model_config = ConfigDict(extra="allow")

    template_id: str = Field(pattern=r"^[a-z0-9_\-]{3,80}$")
    name: str = Field(min_length=3, max_length=120)
    domain: str = Field(min_length=3, max_length=120)
    use_when: list[str] = Field(min_length=1, max_length=20)
    avoid_when: list[str] = Field(default_factory=list, max_length=20)
    default_difficulty: Difficulty = "beginner"
    supported_delivery_modes: list[DeliveryMode] = Field(min_length=1, max_length=8)
    recommended_interactions: list[InteractionType] = Field(min_length=2, max_length=12)
    layout: TemplateLayout
    theme: ThemeTokens
    assessment_mix: AssessmentMix = Field(default_factory=AssessmentMix)
    gamification: GamificationRules = Field(default_factory=GamificationRules)
    lesson_blueprint: list[str] = Field(min_length=5, max_length=20)
    video_scene_blueprint: list[str] = Field(min_length=3, max_length=20)
    quality_rules: dict[str, Any] = Field(default_factory=dict)
    prompt_rules: list[str] = Field(min_length=3, max_length=30)

    @model_validator(mode="after")
    def validate_template_consistency(self) -> "TemplatePack":
        if self.layout.lesson_shell == "video_scene" and "interactive_video" not in self.recommended_interactions:
            raise ValueError("video_scene templates must recommend interactive_video")
        if self.gamification.unlock_mode == "mission_map" and self.layout.navigation != "mission_map":
            raise ValueError("mission_map unlock mode requires mission_map navigation")
        return self


@dataclass(frozen=True)
class TemplateMatch:
    template: TemplatePack
    score: int
    reasons: list[str]


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


class TemplateRegistry:
    """Loads and selects course templates without exposing project files through MCP."""

    def __init__(self, template_dir: str | Path | None = None) -> None:
        self.template_dir = Path(template_dir) if template_dir else Path(__file__).parent / "templates"
        self._templates: dict[str, TemplatePack] = {}

    def load(self) -> "TemplateRegistry":
        self._templates.clear()
        if not self.template_dir.exists():
            return self
        for path in sorted(self.template_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                template = TemplatePack.model_validate(data)
            except (json.JSONDecodeError, ValidationError) as exc:
                raise ValueError(f"Invalid template file {path.name}: {exc}") from exc
            self._templates[template.template_id] = template
        return self

    def list_templates(self) -> list[dict[str, Any]]:
        return [
            {
                "template_id": t.template_id,
                "name": t.name,
                "domain": t.domain,
                "delivery_modes": t.supported_delivery_modes,
                "interactions": t.recommended_interactions,
            }
            for t in self._templates.values()
        ]

    def get(self, template_id: str) -> TemplatePack:
        if not self._templates:
            self.load()
        if template_id not in self._templates:
            raise KeyError(f"Unknown template_id: {template_id}")
        return self._templates[template_id]

    def select_template(
        self,
        *,
        topic: str,
        audience: str,
        industry: str | None = None,
        delivery_mode: DeliveryMode | None = None,
    ) -> TemplateMatch:
        if not self._templates:
            self.load()
        haystack = _normalise(" ".join([topic, audience, industry or "", delivery_mode or ""]))
        best: TemplateMatch | None = None
        for template in self._templates.values():
            score = 0
            reasons: list[str] = []
            domain_tokens = set(_normalise(template.domain).split())
            if domain_tokens and domain_tokens.intersection(haystack.split()):
                score += 20
                reasons.append("domain keyword matched")
            for phrase in template.use_when:
                phrase_norm = _normalise(phrase)
                if phrase_norm and any(token in haystack for token in phrase_norm.split()[:4]):
                    score += 12
                    reasons.append(f"use_when matched: {phrase[:50]}")
            if delivery_mode and delivery_mode in template.supported_delivery_modes:
                score += 25
                reasons.append("delivery mode supported")
            if industry and _normalise(industry) in _normalise(template.domain + " " + template.name):
                score += 18
                reasons.append("industry matched")
            if not reasons:
                score += 1
                reasons.append("fallback candidate")
            match = TemplateMatch(template=template, score=score, reasons=reasons)
            if best is None or match.score > best.score:
                best = match
        if best is None:
            raise ValueError("No templates loaded")
        return best


__all__ = [
    "AssessmentMix",
    "GamificationRules",
    "TemplateLayout",
    "TemplateMatch",
    "TemplatePack",
    "TemplateRegistry",
    "ThemeTokens",
]
