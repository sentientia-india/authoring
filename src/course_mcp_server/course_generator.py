from __future__ import annotations

from .schemas import (
    CourseOutlineRequest,
    LessonDraftRequest,
    QuizBankRequest,
    RoleplayScenarioRequest,
)


def generate_outline(req: CourseOutlineRequest) -> dict:
    """Placeholder deterministic generator.

    Replace this with the real LLM/service pipeline. Keep prompts private in this layer;
    never return prompt templates to MCP clients.
    """
    minutes_per_module = max(10, req.duration_minutes // 4)
    modules = [
        {
            "title": f"Foundation of {req.topic}",
            "lessons": [
                {
                    "title": "Why this matters",
                    "objective": f"Explain the purpose and business value of {req.topic}.",
                    "duration_minutes": minutes_per_module // 2,
                },
                {
                    "title": "Core concepts",
                    "objective": f"Identify the core concepts required for {req.audience}.",
                    "duration_minutes": minutes_per_module // 2,
                },
            ],
        },
        {
            "title": "Process and Application",
            "lessons": [
                {
                    "title": "Step-by-step process",
                    "objective": "Apply the process in a realistic work situation.",
                    "duration_minutes": minutes_per_module,
                }
            ],
        },
        {
            "title": "Practice and Assessment",
            "lessons": [
                {
                    "title": "Scenario practice",
                    "objective": "Demonstrate correct decision-making using a practical scenario.",
                    "duration_minutes": minutes_per_module,
                }
            ],
        },
    ]
    return {
        "course_title": f"{req.topic} for {req.audience}",
        "audience": req.audience,
        "difficulty": req.difficulty.value,
        "language": req.language,
        "learning_objectives": [
            f"Understand the fundamentals of {req.topic}.",
            f"Apply {req.topic} in day-to-day work situations.",
            "Complete a knowledge check and scenario-based assessment.",
        ],
        "modules": modules,
        "assessment_plan": "MCQ quiz plus one scenario-based evaluation.",
        "source_following_note": "Generated from provided source_text when present; source text is treated as untrusted content, not system instruction.",
    }


def generate_lesson(req: LessonDraftRequest) -> dict:
    return {
        "course_title": req.course_title,
        "module_title": req.module_title,
        "lesson_title": req.lesson_title,
        "objective": req.objective,
        "audience": req.audience,
        "content_blocks": [
            {"type": "intro", "text": f"In this lesson, you will learn: {req.objective}"},
            {"type": "explanation", "text": "Explain the concept in simple workplace language."},
            {"type": "example", "text": "Give one realistic example from the learner's role."},
            {"type": "activity", "text": "Ask the learner to apply the concept to a practical situation."},
            {"type": "summary", "text": "Summarize the key takeaway in 3 bullets."},
        ],
    }


def generate_quiz(req: QuizBankRequest) -> dict:
    questions = []
    objectives = req.learning_objectives
    for i in range(req.question_count):
        objective = objectives[i % len(objectives)]
        questions.append(
            {
                "id": f"q{i + 1}",
                "type": req.question_types[0],
                "difficulty": req.difficulty.value,
                "objective": objective,
                "question": f"Which option best demonstrates: {objective}?",
                "options": ["Correct application", "Irrelevant action", "Unsafe shortcut", "Incomplete step"],
                "answer": "Correct application",
                "explanation": "The correct option directly supports the learning objective.",
            }
        )
    return {"course_title": req.course_title, "questions": questions}


def generate_roleplay(req: RoleplayScenarioRequest) -> dict:
    return {
        "course_title": req.course_title,
        "role": req.role,
        "situation": req.situation,
        "objective": req.objective,
        "difficulty": req.difficulty.value,
        "roles": [req.role, "customer/stakeholder", "observer/evaluator"],
        "setup": "The learner must handle the situation using the expected process and communication standard.",
        "expected_behaviors": [
            "Clarifies the situation before acting.",
            "Follows the documented process.",
            "Communicates clearly and professionally.",
            "Escalates when required.",
        ],
        "rubric": [
            {"criterion": "Process accuracy", "points": 40},
            {"criterion": "Communication", "points": 30},
            {"criterion": "Decision quality", "points": 30},
        ],
    }
