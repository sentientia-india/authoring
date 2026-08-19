from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .html_sanitizer import sanitize_html_fragment, strip_tags_to_text


class Difficulty(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class CourseStatus(str, Enum):
    draft = "draft"
    ingested = "ingested"
    blueprint_generated = "blueprint_generated"
    content_generated = "content_generated"
    needs_review = "needs_review"
    approved = "approved"
    exported = "exported"
    published = "published"
    archived = "archived"


class SourceReference(BaseModel):
    source_id: str = Field(min_length=1, max_length=120)
    source_type: Literal["pdf", "docx", "pptx", "txt", "md", "youtube", "url", "manual"] = "manual"
    title: str | None = Field(default=None, max_length=300)
    page: int | None = Field(default=None, ge=1)
    slide: int | None = Field(default=None, ge=1)
    timestamp_seconds: int | None = Field(default=None, ge=0)
    excerpt: str | None = Field(default=None, max_length=600)


class LearningObjective(BaseModel):
    id: str = Field(pattern=r"^lo_[a-zA-Z0-9_-]{1,40}$")
    text: str = Field(min_length=8, max_length=300)
    bloom_level: Literal["remember", "understand", "apply", "analyze", "evaluate", "create"] = "understand"
    measurable: bool = True


class MediaAsset(BaseModel):
    """Media attached to a content block: an image the author supplies, a video link, or a web link.

    Exactly one of `url` (https link, YouTube embed allowed for video) or `upload_id`
    (a controlled upload packaged into the SCORM zip at export) must be provided.
    """

    kind: Literal["image", "video", "link"]
    url: str | None = Field(default=None, max_length=600)
    upload_id: str | None = Field(default=None, max_length=200)
    alt: str | None = Field(default=None, max_length=300)
    caption: str | None = Field(default=None, max_length=400)

    @model_validator(mode="after")
    def validate_source(self) -> "MediaAsset":
        if not self.url and not self.upload_id:
            raise ValueError("Media requires either url or upload_id")
        if self.url and not self.url.startswith("https://"):
            raise ValueError("Media url must use https")
        if self.upload_id and ("/" in self.upload_id or "\\" in self.upload_id or ".." in self.upload_id):
            raise ValueError("upload_id must be a bare file name")
        return self


class ContentBlock(BaseModel):
    id: str = Field(pattern=r"^cb_[a-zA-Z0-9_-]{1,40}$")
    type: Literal[
        "intro",
        "explanation",
        "example",
        "scenario",
        "practice",
        "summary",
        "callout",
        "warning",
        "checklist",
        "reflection",
        "media_placeholder",
    ]
    text: str = Field(min_length=1, max_length=6000)
    text_html: str | None = Field(
        default=None,
        max_length=9000,
        description=(
            "Optional small rich-text fragment (bold/italic/underline/links/lists only, "
            "see html_sanitizer.ALLOWED_TAGS). Sanitized server-side on every write. "
            "`text` is kept in sync as its tag-stripped plain-text equivalent so every "
            "other consumer of `text` (word counts, dedup, image prompts, Adapt export) "
            "is unaffected by rich text."
        ),
    )
    source_refs: list[SourceReference] = Field(default_factory=list, max_length=10)
    alt_text: str | None = Field(default=None, max_length=300)
    media: MediaAsset | None = None

    @model_validator(mode="after")
    def _sync_rich_text(self) -> "ContentBlock":
        if not self.text_html:
            self.text_html = None
            return self
        sanitized = sanitize_html_fragment(self.text_html)
        plain = strip_tags_to_text(sanitized)
        if not plain:
            # Sanitization stripped every allowlisted tag/text node (e.g. the
            # fragment was pure disallowed markup) — drop text_html and keep
            # the existing plain-text `text` field untouched.
            self.text_html = None
            return self
        self.text_html = sanitized
        self.text = plain[:6000]
        return self


class GameOptions(BaseModel):
    """Per-course Level 3.5/4 mechanics the authoring agent (or user) can switch on."""

    branching_scenarios: bool = True
    locked_progression: bool = True
    streaks: bool = True
    timed_challenges: bool = False
    timer_seconds: int = Field(default=20, ge=5, le=120)
    celebration: bool = True
    certificate: bool = True


class Activity(BaseModel):
    id: str = Field(pattern=r"^act_[a-zA-Z0-9_-]{1,40}$")
    type: Literal[
        "flashcards",
        "accordion",
        "tabs",
        "drag_drop_sort",
        "matching",
        "hotspot",
        "decision_tree",
        "branching_scenario",
        "roleplay",
        "timeline",
        "fill_blank",
        "interactive_video_checkpoint",
        "reflection",
    ]
    title: str = Field(min_length=3, max_length=200)
    instructions: str = Field(min_length=10, max_length=1000)
    data: dict = Field(default_factory=dict)
    objective_ids: list[str] = Field(default_factory=list, max_length=10)


class QuizQuestion(BaseModel):
    id: str = Field(pattern=r"^q_[a-zA-Z0-9_-]{1,40}$")
    type: Literal["mcq", "multi_select", "true_false", "matching", "fill_blank", "short_answer", "scenario"]
    difficulty: Difficulty = Difficulty.beginner
    objective_ids: list[str] = Field(min_length=1, max_length=10)
    question: str = Field(min_length=10, max_length=2000)
    options: list[str] = Field(default_factory=list, max_length=8)
    correct_answers: list[str] = Field(default_factory=list, max_length=8)
    explanation: str = Field(min_length=10, max_length=1200)
    feedback_correct: str | None = Field(default=None, max_length=1000)
    feedback_incorrect: str | None = Field(default=None, max_length=1000)
    rubric: list[dict] = Field(default_factory=list, max_length=10)
    source_refs: list[SourceReference] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_options_for_objective_question(self) -> "QuizQuestion":
        if self.type in {"mcq", "multi_select", "true_false"} and len(self.options) < 2:
            raise ValueError("Objective questions require at least two options")
        if self.type in {"mcq", "multi_select", "true_false", "matching", "fill_blank"} and not self.correct_answers:
            raise ValueError("Question requires at least one correct answer")
        return self


class Lesson(BaseModel):
    id: str = Field(pattern=r"^lesson_[a-zA-Z0-9_-]{1,40}$")
    title: str = Field(min_length=3, max_length=250)
    duration_minutes: int = Field(ge=1, le=240)
    objective_ids: list[str] = Field(min_length=1, max_length=10)
    content_blocks: list[ContentBlock] = Field(min_length=1, max_length=30)
    activities: list[Activity] = Field(default_factory=list, max_length=10)
    quiz_questions: list[QuizQuestion] = Field(default_factory=list, max_length=20)


class Module(BaseModel):
    id: str = Field(pattern=r"^module_[a-zA-Z0-9_-]{1,40}$")
    title: str = Field(min_length=3, max_length=250)
    duration_minutes: int = Field(ge=5, le=480)
    objective_ids: list[str] = Field(min_length=1, max_length=20)
    lessons: list[Lesson] = Field(min_length=1, max_length=20)
    activities: list[Activity] = Field(default_factory=list, max_length=20)


class Assessment(BaseModel):
    id: str = Field(default="assessment_final", max_length=80)
    title: str = Field(default="Final Assessment", max_length=250)
    passing_score: int = Field(default=70, ge=0, le=100)
    max_attempts: int = Field(default=3, ge=1, le=20)
    questions: list[QuizQuestion] = Field(min_length=1, max_length=200)


class CourseProjectV2(BaseModel):
    course_id: str = Field(pattern=r"^course_[a-zA-Z0-9_-]{1,60}$")
    course_title: str = Field(min_length=3, max_length=300)
    course_slug: str = Field(pattern=r"^[a-z0-9-]{3,100}$")
    audience: str = Field(min_length=2, max_length=250)
    difficulty: Difficulty = Difficulty.beginner
    language: str = Field(default="English", max_length=80)
    estimated_duration_minutes: int = Field(ge=10, le=1000)
    status: CourseStatus = CourseStatus.draft
    learning_objectives: list[LearningObjective] = Field(min_length=1, max_length=30)
    modules: list[Module] = Field(min_length=1, max_length=30)
    final_assessment: Assessment | None = None
    source_refs: list[SourceReference] = Field(default_factory=list, max_length=100)
    glossary: list[dict] = Field(default_factory=list, max_length=100)
    export_preferences: dict = Field(default_factory=dict)
    review_notes: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_objective_references(self) -> "CourseProjectV2":
        objective_ids = {obj.id for obj in self.learning_objectives}
        missing: list[str] = []
        for module in self.modules:
            missing.extend([obj_id for obj_id in module.objective_ids if obj_id not in objective_ids])
            for lesson in module.lessons:
                missing.extend([obj_id for obj_id in lesson.objective_ids if obj_id not in objective_ids])
                for activity in lesson.activities:
                    missing.extend([obj_id for obj_id in activity.objective_ids if obj_id not in objective_ids])
                for question in lesson.quiz_questions:
                    missing.extend([obj_id for obj_id in question.objective_ids if obj_id not in objective_ids])
        if self.final_assessment:
            for question in self.final_assessment.questions:
                missing.extend([obj_id for obj_id in question.objective_ids if obj_id not in objective_ids])
        if missing:
            raise ValueError(f"Unknown objective references: {sorted(set(missing))}")
        return self
