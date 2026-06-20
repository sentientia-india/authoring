from __future__ import annotations

from typing import Any

COURSE_DISCOVERY_QUESTIONS: list[dict[str, Any]] = [
    {
        "id": "course_title",
        "stage": "brief",
        "question": "What is the course title? Press Enter for AI suggestion.",
        "type": "text",
        "required": True,
    },
    {
        "id": "target_learner",
        "stage": "brief",
        "question": "Who will take this course? Press Enter for AI suggestion.",
        "type": "text",
        "required": True,
    },
    {
        "id": "course_goal",
        "stage": "brief",
        "question": "What should learners be able to do after this course? Press Enter for AI suggestion.",
        "type": "text",
        "required": True,
    },
    {
        "id": "learner_level",
        "stage": "brief",
        "question": "What is the learner level? beginner / intermediate / advanced / mixed. Press Enter for AI recommendation.",
        "type": "single_select",
        "options": ["beginner", "intermediate", "advanced", "mixed"],
        "default_if_blank": "beginner",
        "required": True,
    },
    {
        "id": "industry_context",
        "stage": "brief",
        "question": "What industry or context is this course for? Press Enter for AI suggestion.",
        "type": "text",
        "required": True,
    },
    {
        "id": "course_type",
        "stage": "brief",
        "question": "What type of course is this? Press Enter for AI suggestion.",
        "type": "single_select",
        "options": ["simple course", "interactive course", "scenario-based course", "simulation-style course", "gamified course", "compliance course"],
        "default_if_blank": "interactive course",
        "required": True,
    },
    {
        "id": "expected_duration",
        "stage": "brief",
        "question": "What is the expected course duration in minutes? Press Enter for AI recommendation.",
        "type": "number",
        "default_if_blank": 30,
        "required": True,
    },
    {
        "id": "source_material",
        "stage": "brief",
        "question": "Which source material should be used? Press Enter to use uploaded source chunks.",
        "type": "text",
        "default_if_blank": "Use approved uploaded source chunks.",
        "required": True,
    },
    {
        "id": "module_topic_mode",
        "stage": "brief",
        "question": "Should I suggest modules or use your existing topics? Press Enter for suggested modules.",
        "type": "single_select",
        "options": ["suggested_modules", "user_topics"],
        "default_if_blank": "suggested_modules",
        "required": True,
    },
    {
        "id": "export_targets",
        "stage": "brief",
        "question": "What export do you need? html, scorm, lms_package. Press Enter for AI recommendation.",
        "type": "multi_select",
        "recommended_options": ["html", "scorm"],
        "required": True,
    },
    {
        "id": "module_count_preference",
        "stage": "outline",
        "question": "How many modules should the course have? Press Enter for AI recommendation.",
        "type": "number",
        "default_if_blank": 5,
        "required": False,
    },
    {
        "id": "module_topics_review",
        "stage": "outline",
        "question": "Are these proposed module topics good? Press Enter for AI recommendation.",
        "type": "boolean",
        "default_if_blank": True,
        "required": False,
    },
    {
        "id": "assessment_preference",
        "stage": "assessment",
        "question": "Assessment model: lesson quiz, module quiz, final only, scenario-based, or mixed? Press Enter for AI recommendation.",
        "type": "single_select",
        "options": ["lesson_quiz", "module_quiz", "final_only", "scenario_based", "mixed"],
        "default_if_blank": "mixed",
        "required": True,
    },
    {
        "id": "question_types",
        "stage": "assessment",
        "question": "Which question types should be used? Comma-separated. Press Enter for AI recommendation.",
        "type": "multi_select",
        "recommended_options": ["mcq", "multi_select", "matching", "drag_drop", "scenario_decision", "case_study"],
        "required": False,
    },
    {
        "id": "interaction_preference",
        "stage": "interaction",
        "question": "Interaction model: simple, interactive, scenario-based, simulation, gamified, compliance. Press Enter for AI recommendation.",
        "type": "single_select",
        "options": ["simple", "interactive", "scenario_based", "simulation", "gamified", "compliance"],
        "default_if_blank": "scenario_based",
        "required": True,
    },
    {
        "id": "html_video_enabled",
        "stage": "interaction",
        "question": "Generate HTML interactive video? yes/no. Press Enter for Yes.",
        "type": "boolean",
        "default_if_blank": True,
        "required": False,
    },
    {
        "id": "gamification_enabled",
        "stage": "interaction",
        "question": "Enable XP, badges, levels, and completion credential? yes/no. Press Enter for Yes.",
        "type": "boolean",
        "default_if_blank": True,
        "required": False,
    },
]


def get_question(question_id: str) -> dict[str, Any]:
    for question in COURSE_DISCOVERY_QUESTIONS:
        if question["id"] == question_id:
            return question
    raise KeyError(f"Unknown discovery question: {question_id}")


def get_next_unanswered_question(answers: dict[str, Any]) -> dict[str, Any] | None:
    for question in COURSE_DISCOVERY_QUESTIONS:
        if question["id"] not in answers:
            return question
    return None


def get_unanswered_questions(answers: dict[str, Any], *, limit: int = 6, stage: str | None = None) -> list[dict[str, Any]]:
    questions = []
    for question in COURSE_DISCOVERY_QUESTIONS:
        if stage and question.get("stage") != stage:
            continue
        if question["id"] not in answers:
            questions.append(question)
        if len(questions) >= limit:
            break
    return questions
