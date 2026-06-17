from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Difficulty(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class CourseOutlineRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=300)
    audience: str = Field(min_length=2, max_length=200)
    duration_minutes: int = Field(default=60, ge=10, le=480)
    difficulty: Difficulty = Difficulty.beginner
    source_text: str | None = Field(default=None, max_length=60_000)
    language: str = Field(default="English", max_length=60)


class LessonDraftRequest(BaseModel):
    course_title: str = Field(min_length=3, max_length=300)
    module_title: str = Field(min_length=3, max_length=300)
    lesson_title: str = Field(min_length=3, max_length=300)
    objective: str = Field(min_length=3, max_length=500)
    audience: str = Field(min_length=2, max_length=200)
    tone: str = Field(default="professional and simple", max_length=100)


class QuizBankRequest(BaseModel):
    course_title: str = Field(min_length=3, max_length=300)
    learning_objectives: list[str] = Field(min_length=1, max_length=20)
    question_count: int = Field(default=10, ge=1, le=50)
    difficulty: Difficulty = Difficulty.beginner
    question_types: list[Literal["mcq", "true_false", "scenario"]] = Field(default=["mcq"])


class RoleplayScenarioRequest(BaseModel):
    course_title: str = Field(min_length=3, max_length=300)
    role: str = Field(min_length=2, max_length=120)
    situation: str = Field(min_length=10, max_length=1000)
    objective: str = Field(min_length=3, max_length=500)
    difficulty: Difficulty = Difficulty.beginner


class ValidateCourseSchemaRequest(BaseModel):
    course: dict


class ScormPackageRequest(BaseModel):
    course_title: str = Field(min_length=3, max_length=300)
    course_slug: str = Field(pattern=r"^[a-z0-9-]{3,80}$")
    modules: list[dict] = Field(min_length=1)
    scorm_version: Literal["1.2", "2004"] = "1.2"


class JobStatusRequest(BaseModel):
    job_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{6,80}$")


class CourseProjectRequest(BaseModel):
    course_title: str = Field(min_length=3, max_length=300)
    audience: str = Field(min_length=2, max_length=200)
    language: str = Field(default="English", max_length=60)
    compliance_domain: str | None = Field(default=None, max_length=120)


class CourseProjectResult(BaseModel):
    project_id: str = Field(pattern=r"^course_[a-z0-9]{8,20}$")
    course_title: str
    audience: str
    language: str
    compliance_domain: str | None = None
    status: Literal["draft", "generated", "needs_review", "approved", "exported", "published", "archived"]


class SourceIngestRequest(BaseModel):
    project_id: str = Field(pattern=r"^course_[a-z0-9]{8,20}$")
    upload_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{1,120}$")
    source_type: Literal["pdf", "pptx", "ppt", "docx", "youtube", "website", "raw_text"]


class SourceIngestResult(BaseModel):
    project_id: str
    source_id: str
    source_type: str
    title: str
    extracted_text_preview: str
    page_references: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class BlueprintRequest(BaseModel):
    project_id: str = Field(pattern=r"^course_[a-z0-9]{8,20}$")
    duration_minutes: int = Field(default=60, ge=5, le=480)
    difficulty: Difficulty = Difficulty.beginner


class CourseBlueprintResult(BaseModel):
    project_id: str
    learning_objectives: list[str]
    modules: list[dict]
    assessment_strategy: str
    source_citation_policy: str


class ModulePackRequest(BaseModel):
    project_id: str = Field(pattern=r"^course_[a-z0-9]{8,20}$")
    module_count: int = Field(default=3, ge=1, le=12)


class ModulePackResult(BaseModel):
    project_id: str
    modules: list[dict]


class LessonPackRequest(BaseModel):
    project_id: str = Field(pattern=r"^course_[a-z0-9]{8,20}$")
    module_id: str = Field(pattern=r"^module_[0-9]{1,2}$")


class LessonPackResult(BaseModel):
    project_id: str
    module_id: str
    lessons: list[dict]


class ActivityRequest(BaseModel):
    project_id: str = Field(pattern=r"^course_[a-z0-9]{8,20}$")
    activity_type: Literal[
        "flashcards",
        "accordion",
        "interactive_video",
        "drag_and_drop",
        "matching",
        "scenario_decision_tree",
        "hotspot_image",
        "branching_scenario",
        "timeline",
        "fill_in_blanks",
        "reflection_prompt",
    ]
    objective: str = Field(min_length=3, max_length=500)


class ActivityResult(BaseModel):
    project_id: str
    activity_id: str
    activity_type: str
    title: str
    objective: str
    items: list[dict]


class AssessmentRequest(BaseModel):
    project_id: str = Field(pattern=r"^course_[a-z0-9]{8,20}$")
    question_count: int = Field(default=10, ge=1, le=50)
    question_types: list[
        Literal["mcq", "true_false", "scenario", "matching", "fill_blank", "case_study", "rubric"]
    ] = Field(default=["mcq", "scenario"])
    passing_score: int = Field(default=80, ge=1, le=100)
    retake_rule: str = Field(default="Allow two retakes after review.", max_length=300)


class AssessmentBankResult(BaseModel):
    project_id: str
    passing_score: int
    retake_rule: str
    questions: list[dict]


class QualityValidationRequest(BaseModel):
    project_id: str = Field(pattern=r"^course_[a-z0-9]{8,20}$")


class QualityValidationResult(BaseModel):
    score: int = Field(ge=0, le=100)
    status: Literal["passed", "needs_review", "failed"]
    issues: list[dict] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class ExportPackageRequest(BaseModel):
    project_id: str = Field(pattern=r"^course_[a-z0-9]{8,20}$")
    export_format: Literal["scorm"] = "scorm"
    scorm_version: Literal["1.2", "2004"] = "1.2"


class ListArtifactsRequest(BaseModel):
    project_id: str = Field(pattern=r"^course_[a-z0-9]{8,20}$")


class ArtifactListResult(BaseModel):
    project_id: str
    artifact_types: list[str]
    artifacts: list[dict]


class PublishApprovalRequest(BaseModel):
    project_id: str = Field(pattern=r"^course_[a-z0-9]{8,20}$")
    reviewer: str = Field(min_length=2, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)


class PublishApprovalResult(BaseModel):
    project_id: str
    review_status: Literal["needs_review"]
    published: bool
    next_action: str


class LessonOutline(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    objective: str = Field(min_length=1, max_length=500)
    duration_minutes: int = Field(ge=1, le=480)


class CourseModule(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    lessons: list[LessonOutline] = Field(default_factory=list)


class CourseOutline(BaseModel):
    course_title: str = Field(min_length=1, max_length=300)
    audience: str = Field(min_length=1, max_length=200)
    difficulty: Difficulty
    language: str = Field(min_length=1, max_length=60)
    learning_objectives: list[str] = Field(min_length=1, max_length=20)
    modules: list[CourseModule] = Field(min_length=1, max_length=20)
    assessment_plan: str = Field(min_length=1, max_length=1000)
    source_used: bool = False
    source_risk_flags: list[str] = Field(default_factory=list, max_length=20)
    instructional_design_notes: list[str] = Field(default_factory=list, max_length=20)
    generation_provider: str = Field(default="deterministic", max_length=80)


class ContentBlock(BaseModel):
    type: str = Field(min_length=1, max_length=60)
    text: str = Field(min_length=1, max_length=2000)


class LessonDraft(BaseModel):
    course_title: str = Field(min_length=1, max_length=300)
    module_title: str = Field(min_length=1, max_length=300)
    lesson_title: str = Field(min_length=1, max_length=300)
    objective: str = Field(min_length=1, max_length=500)
    audience: str = Field(min_length=1, max_length=200)
    content_blocks: list[ContentBlock] = Field(min_length=1, max_length=20)


class QuizQuestion(BaseModel):
    id: str = Field(pattern=r"^q[0-9]+$")
    type: Literal["mcq", "true_false", "scenario"]
    difficulty: Difficulty
    objective: str = Field(min_length=1, max_length=500)
    question: str = Field(min_length=1, max_length=1000)
    options: list[str] = Field(min_length=2, max_length=6)
    answer: str = Field(min_length=1, max_length=500)
    explanation: str = Field(min_length=1, max_length=1000)


class QuizBank(BaseModel):
    course_title: str = Field(min_length=1, max_length=300)
    questions: list[QuizQuestion] = Field(min_length=1, max_length=50)


class RubricCriterion(BaseModel):
    criterion: str = Field(min_length=1, max_length=200)
    points: int = Field(ge=0, le=100)


class RoleplayScenario(BaseModel):
    course_title: str = Field(min_length=1, max_length=300)
    role: str = Field(min_length=1, max_length=120)
    situation: str = Field(min_length=1, max_length=1000)
    objective: str = Field(min_length=1, max_length=500)
    difficulty: Difficulty
    roles: list[str] = Field(min_length=2, max_length=10)
    setup: str = Field(min_length=1, max_length=1500)
    expected_behaviors: list[str] = Field(min_length=1, max_length=20)
    rubric: list[RubricCriterion] = Field(min_length=1, max_length=10)


class CourseValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)


class ScormPackageResult(BaseModel):
    course_title: str
    course_slug: str
    scorm_version: Literal["1.2", "2004"]
    artifact_path: str
    package_path: str
    files: list[str]
    note: str


class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed", "not_found"]
    tool_name: str | None = None
    message: str
