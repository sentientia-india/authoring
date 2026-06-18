from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


EventType = Literal[
    "lesson_started",
    "lesson_completed",
    "activity_completed",
    "question_answered",
    "scenario_completed",
    "video_checkpoint_completed",
    "course_completed",
]


class BadgeRule(BaseModel):
    badge_id: str = Field(pattern=r"^badge_[a-z0-9_\-]{2,80}$")
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=5, max_length=300)
    icon: str = Field(default="badge", max_length=16)
    condition: Literal[
        "complete_course",
        "score_at_least",
        "complete_all_activities",
        "complete_without_retry",
        "scenario_mastery",
        "daily_streak",
    ]
    threshold: int = Field(default=1, ge=0, le=100000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Achievement(BaseModel):
    badge_id: str
    title: str
    awarded_at: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class LearnerGameState(BaseModel):
    learner_id: str = Field(min_length=1, max_length=120)
    course_id: str = Field(min_length=1, max_length=120)
    xp: int = Field(default=0, ge=0)
    level: int = Field(default=1, ge=1)
    streak_days: int = Field(default=0, ge=0)
    completed_lessons: set[str] = Field(default_factory=set)
    completed_activities: set[str] = Field(default_factory=set)
    answered_questions: dict[str, bool] = Field(default_factory=dict)
    scenario_scores: dict[str, int] = Field(default_factory=dict)
    achievements: list[Achievement] = Field(default_factory=list)
    last_event_date: str | None = None


class GameEvent(BaseModel):
    learner_id: str = Field(min_length=1, max_length=120)
    course_id: str = Field(min_length=1, max_length=120)
    event_type: EventType
    object_id: str = Field(min_length=1, max_length=160)
    correct: bool | None = None
    score: int | None = Field(default=None, ge=0, le=100)
    metadata: dict[str, Any] = Field(default_factory=dict)
    occurred_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class GamificationConfig(BaseModel):
    enabled: bool = True
    xp_lesson_completed: int = Field(default=50, ge=0, le=10000)
    xp_activity_completed: int = Field(default=75, ge=0, le=10000)
    xp_correct_answer: int = Field(default=20, ge=0, le=10000)
    xp_wrong_answer: int = Field(default=2, ge=0, le=10000)
    xp_scenario_mastery: int = Field(default=100, ge=0, le=10000)
    level_curve: list[int] = Field(default_factory=lambda: [0, 100, 250, 500, 900, 1400, 2100, 3000])
    badge_rules: list[BadgeRule] = Field(default_factory=list)
    emit_xapi: bool = True
    emit_scorm_interactions: bool = True

    @model_validator(mode="after")
    def curve_must_be_sorted(self) -> "GamificationConfig":
        if self.level_curve != sorted(self.level_curve):
            raise ValueError("level_curve must be sorted ascending")
        return self


def default_badge_rules() -> list[BadgeRule]:
    return [
        BadgeRule(
            badge_id="badge_course_finisher",
            title="Course Finisher",
            description="Completed the full course.",
            icon="badge",
            condition="complete_course",
        ),
        BadgeRule(
            badge_id="badge_mastery_85",
            title="Mastery Performer",
            description="Scored at least 85% in the final assessment.",
            icon="star",
            condition="score_at_least",
            threshold=85,
        ),
        BadgeRule(
            badge_id="badge_scenario_master",
            title="Scenario Master",
            description="Completed a scenario with mastery score.",
            icon="scenario",
            condition="scenario_mastery",
            threshold=85,
        ),
    ]


def calculate_level(xp: int, curve: list[int]) -> int:
    level = 1
    for index, threshold in enumerate(curve, start=1):
        if xp >= threshold:
            level = index
    return level


def _award_once(state: LearnerGameState, rule: BadgeRule, evidence: dict[str, Any]) -> None:
    if any(a.badge_id == rule.badge_id for a in state.achievements):
        return
    state.achievements.append(
        Achievement(
            badge_id=rule.badge_id,
            title=rule.title,
            awarded_at=datetime.now(timezone.utc).isoformat(),
            evidence=evidence,
        )
    )


def _update_streak(state: LearnerGameState, event_date: str) -> None:
    today = event_date[:10]
    if state.last_event_date == today:
        return
    if state.last_event_date is None:
        state.streak_days = 1
    else:
        try:
            previous = datetime.fromisoformat(state.last_event_date + "T00:00:00+00:00")
            current = datetime.fromisoformat(today + "T00:00:00+00:00")
            delta_days = (current - previous).days
            state.streak_days = state.streak_days + 1 if delta_days == 1 else 1
        except ValueError:
            state.streak_days = 1
    state.last_event_date = today


def apply_game_event(
    state: LearnerGameState,
    event: GameEvent,
    config: GamificationConfig | None = None,
    *,
    course_totals: dict[str, int] | None = None,
) -> LearnerGameState:
    config = config or GamificationConfig(badge_rules=default_badge_rules())
    if not config.enabled:
        return state
    if state.learner_id != event.learner_id or state.course_id != event.course_id:
        raise ValueError("event learner/course does not match state")

    _update_streak(state, event.occurred_at[:10])

    if event.event_type == "lesson_completed":
        if event.object_id not in state.completed_lessons:
            state.completed_lessons.add(event.object_id)
            state.xp += config.xp_lesson_completed
    elif event.event_type == "activity_completed":
        if event.object_id not in state.completed_activities:
            state.completed_activities.add(event.object_id)
            state.xp += config.xp_activity_completed
    elif event.event_type == "question_answered":
        state.answered_questions[event.object_id] = bool(event.correct)
        state.xp += config.xp_correct_answer if event.correct else config.xp_wrong_answer
    elif event.event_type in {"scenario_completed", "video_checkpoint_completed"}:
        score = event.score or 0
        state.scenario_scores[event.object_id] = score
        if score >= 85:
            state.xp += config.xp_scenario_mastery
    elif event.event_type == "course_completed":
        state.xp += config.xp_lesson_completed

    state.level = calculate_level(state.xp, config.level_curve)

    totals = course_totals or {}
    for rule in config.badge_rules:
        if rule.condition == "complete_course" and event.event_type == "course_completed":
            _award_once(state, rule, {"event_id": event.object_id})
        elif rule.condition == "score_at_least" and (event.score or 0) >= rule.threshold:
            _award_once(state, rule, {"score": event.score, "object_id": event.object_id})
        elif rule.condition == "complete_all_activities":
            required = totals.get("activities", 0)
            if required and len(state.completed_activities) >= required:
                _award_once(state, rule, {"completed_activities": len(state.completed_activities)})
        elif rule.condition == "scenario_mastery":
            if any(score >= rule.threshold for score in state.scenario_scores.values()):
                _award_once(state, rule, {"scores": state.scenario_scores})
        elif rule.condition == "daily_streak" and state.streak_days >= rule.threshold:
            _award_once(state, rule, {"streak_days": state.streak_days})
    return state


def build_xapi_statement(event: GameEvent, state: LearnerGameState) -> dict[str, Any]:
    verb_map = {
        "lesson_started": ("experienced", "experienced"),
        "lesson_completed": ("completed", "completed"),
        "activity_completed": ("completed", "completed"),
        "question_answered": ("answered", "answered"),
        "scenario_completed": ("completed", "completed"),
        "video_checkpoint_completed": ("answered", "answered"),
        "course_completed": ("completed", "completed"),
    }
    verb_id, display = verb_map[event.event_type]
    statement_id = hashlib.sha256(
        f"{event.learner_id}|{event.course_id}|{event.event_type}|{event.object_id}|{event.occurred_at}".encode()
    ).hexdigest()
    return {
        "id": statement_id,
        "actor": {"account": {"name": event.learner_id, "homePage": "https://sentientia.local"}},
        "verb": {"id": f"https://adlnet.gov/expapi/verbs/{verb_id}", "display": {"en-US": display}},
        "object": {"id": f"urn:sentientia:{event.course_id}:{event.object_id}"},
        "result": {
            "success": event.correct,
            "score": {"scaled": (event.score / 100) if event.score is not None else None},
            "extensions": {
                "https://sentientia.local/xp": state.xp,
                "https://sentientia.local/level": state.level,
            },
        },
        "timestamp": event.occurred_at,
        "context": {"contextActivities": {"parent": [{"id": f"urn:sentientia:{event.course_id}"}]}},
    }


def build_open_badge_assertion(state: LearnerGameState, achievement: Achievement, issuer_url: str) -> dict[str, Any]:
    return {
        "@context": ["https://www.w3.org/ns/credentials/v2", "https://purl.imsglobal.org/spec/ob/v3p0/context-3.0.3.json"],
        "type": ["VerifiableCredential", "OpenBadgeCredential"],
        "issuer": {"id": issuer_url, "type": "Profile", "name": "Sentientia"},
        "name": achievement.title,
        "credentialSubject": {
            "type": "AchievementSubject",
            "identifier": [{"identityHash": hashlib.sha256(state.learner_id.encode()).hexdigest(), "type": "IdentityObject"}],
            "achievement": {
                "id": f"{issuer_url.rstrip('/')}/badges/{achievement.badge_id}",
                "type": "Achievement",
                "name": achievement.title,
                "description": achievement.evidence,
            },
        },
        "validFrom": achievement.awarded_at,
    }


__all__ = [
    "Achievement",
    "BadgeRule",
    "GameEvent",
    "GamificationConfig",
    "LearnerGameState",
    "apply_game_event",
    "build_open_badge_assertion",
    "build_xapi_statement",
    "calculate_level",
    "default_badge_rules",
]
