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
    duration_minutes: int = Field(default=60, ge=3, le=480)
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
    reference_style: Literal["rise_block", "interaction_game", "course_example"] = "rise_block"


class CourseMaterial(BaseModel):
    upload_id: str | None = Field(default=None, max_length=120)
    source_type: Literal["pdf", "pptx", "ppt", "docx", "youtube", "website", "raw_text"] | None = None
    title: str | None = Field(default=None, max_length=200)
    summary: str | None = Field(default=None, max_length=1000)


class CourseMedia(BaseModel):
    type: Literal["youtube", "mp4", "link"]
    url: str = Field(min_length=8, max_length=1000)
    title: str | None = Field(default=None, max_length=200)
    duration_seconds: int | None = Field(default=None, ge=1, le=7200)


class MaterialTicketRequest(BaseModel):
    course_title: str | None = Field(default=None, min_length=3, max_length=300)
    audience: str | None = Field(default=None, min_length=2, max_length=200)
    goal: str | None = Field(default=None, min_length=3, max_length=500)
    duration_minutes: int | None = Field(default=None, ge=3, le=480)
    difficulty: Difficulty | None = None
    language: str = Field(default="English", max_length=60)
    materials: list[CourseMaterial] = Field(default_factory=list, max_length=20)
    media: list[CourseMedia] = Field(default_factory=list, max_length=20)
    interactive_preferences: list[
        Literal[
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
    ] = Field(default_factory=list, max_length=10)


class MaterialTicketResult(BaseModel):
    ticket_id: str
    status: Literal["needs_information", "ready_for_layout"]
    missing_fields: list[str]
    questions: list[str]
    question_flow: list[dict] = Field(default_factory=list)
    proposed_topics: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    normalized_ticket: dict


class DiscoveryAnswer(BaseModel):
    value: str | int | float | bool | list[str] | dict | None = None
    source: Literal["user_provided", "ai_suggested", "template_default"]
    confidence: float = Field(ge=0, le=1)
    reason: str


class DiscoveryStartRequest(BaseModel):
    project_id: str = Field(pattern=r"^course_[a-z0-9]{8,20}$")


class DiscoveryStartResult(BaseModel):
    project_id: str
    status: str
    next_question: dict | None = None
    questions: list[dict] = Field(default_factory=list)
    answers: dict[str, DiscoveryAnswer] = Field(default_factory=dict)
    proposed_topics: list[str] = Field(default_factory=list)
    selected_template_id: str | None = None


class DiscoveryAnswerRequest(BaseModel):
    project_id: str = Field(pattern=r"^course_[a-z0-9]{8,20}$")
    question_id: str = Field(min_length=2, max_length=80)
    answer: str | int | float | bool | list[str] | dict | None = None


class CourseBriefSaveRequest(BaseModel):
    project_id: str = Field(pattern=r"^course_[a-z0-9]{8,20}$")
    course_title: str | None = Field(default=None, min_length=3, max_length=300)
    target_learner: str | None = Field(default=None, min_length=2, max_length=200)
    learner_level: Literal["beginner", "intermediate", "advanced", "mixed"] | None = None
    course_goal: str | None = Field(default=None, min_length=3, max_length=500)
    industry_context: str | None = Field(default=None, min_length=2, max_length=200)
    course_type: str | None = Field(default=None, min_length=2, max_length=120)
    expected_duration: int | None = Field(default=None, ge=3, le=480)
    source_material: str | None = Field(default=None, min_length=2, max_length=1000)
    module_topic_mode: Literal["suggested_modules", "user_topics"] | None = None
    export_targets: list[str] | str | None = None


class DiscoveryAnswerResult(BaseModel):
    project_id: str
    question_id: str
    answer: DiscoveryAnswer
    next_question: dict | None = None
    status: str


class TemplateListResult(BaseModel):
    templates: list[dict]


class TemplateRecommendationRequest(BaseModel):
    project_id: str = Field(pattern=r"^course_[a-z0-9]{8,20}$")
    source_summary: str = Field(default="", max_length=5000)


class TemplateRecommendationResult(BaseModel):
    recommendations: list[dict]


class WorkflowOutlineRequest(BaseModel):
    project_id: str = Field(pattern=r"^course_[a-z0-9]{8,20}$")


class WorkflowOutlineResult(BaseModel):
    project_id: str
    proposed_module_outline: list[dict]
    proposed_lesson_structure: list[dict]
    selected_template_id: str | None = None


class WorkflowStructureUpdateRequest(BaseModel):
    project_id: str = Field(pattern=r"^course_[a-z0-9]{8,20}$")
    items: list[dict] = Field(default_factory=list)


class WorkflowModelSelectionRequest(BaseModel):
    project_id: str = Field(pattern=r"^course_[a-z0-9]{8,20}$")
    model: dict = Field(default_factory=dict)


class WorkflowApprovalRequest(BaseModel):
    project_id: str = Field(pattern=r"^course_[a-z0-9]{8,20}$")


class WorkflowSelectionResult(BaseModel):
    project_id: str
    status: str
    selected_value: dict | None = None


class GenerationReadinessResult(BaseModel):
    project_id: str
    ready: bool
    missing: list[str]
    status: str


class CodexGenerationContractResult(BaseModel):
    project_id: str
    codex_payload: dict


class WorkflowStatusResult(BaseModel):
    project_id: str
    status: str
    answers: dict[str, DiscoveryAnswer] = Field(default_factory=dict)
    selected_template_id: str | None = None
    module_outline: list[dict] = Field(default_factory=list)
    lesson_structure: list[dict] = Field(default_factory=list)
    assessment_model: dict = Field(default_factory=dict)
    interaction_model: dict = Field(default_factory=dict)
    approvals: dict[str, bool] = Field(default_factory=dict)
    source_chunk_count: int = 0


class ChapterLayoutRequest(MaterialTicketRequest):
    answers: dict[str, str] = Field(default_factory=dict, max_length=20)


class ChapterLayoutResult(BaseModel):
    status: Literal["needs_more_information", "ready_for_generation"]
    missing_fields: list[str]
    next_questions: list[str]
    chapters: list[dict]
    media_plan: list[dict]
    interactive_plan: list[dict]
    confirmation_prompt: str


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
    status: Literal["draft", "generated", "quality_failed", "needs_review", "approved", "exported", "published", "archived"]


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
    duration_minutes: int = Field(default=60, ge=3, le=480)
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
    status: Literal["approved", "passed", "needs_review", "failed"]
    issues: list[dict] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)


class ExportPackageRequest(BaseModel):
    project_id: str = Field(pattern=r"^course_[a-z0-9]{8,20}$")
    export_format: Literal["scorm", "h5p"] = "scorm"
    scorm_version: Literal["1.2", "2004"] = "1.2"


class StorylineHandoffRequest(BaseModel):
    project_id: str = Field(pattern=r"^course_[a-z0-9]{8,20}$")


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


class TemplateSelectionRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=300)
    audience: str = Field(min_length=2, max_length=200)
    industry: str | None = Field(default=None, max_length=120)
    delivery_mode: str | None = Field(default=None, max_length=40)


class TemplateSelectionResult(BaseModel):
    template_id: str
    name: str
    recommended_interactions: list[str]
    quality_rules: dict
    theme: dict
    reason: str | None = None


class SuperiorQualityValidationRequest(BaseModel):
    project_id: str = Field(pattern=r"^course_[a-z0-9]{8,20}$")


class SuperiorQualityValidationResult(BaseModel):
    score: int = Field(ge=0, le=100)
    status: Literal["pass", "needs_review", "fail"]
    component_scores: dict
    issues: list[dict] = Field(default_factory=list)
    similarity_matrix: list[dict] = Field(default_factory=list)
    repeated_phrases: dict[str, int] = Field(default_factory=dict)


class InteractiveVideoRequest(BaseModel):
    project_id: str = Field(pattern=r"^course_[a-z0-9]{8,20}$")
    module_id: str | None = Field(default=None, pattern=r"^module_[0-9]{1,2}$")
    lesson_id: str | None = Field(default=None, pattern=r"^lesson_[A-Za-z0-9_\-]{1,60}$")
    template_id: str | None = Field(default=None, max_length=80)


class InteractiveVideoResult(BaseModel):
    project_id: str
    video_id: str
    package_path: str
    files: list[str]
    note: str


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
