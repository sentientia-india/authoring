from course_mcp_server.instructional_quality import validate_instructional_quality


def _good_course():
    objectives = [
        {"id": "lo_identify", "text": "Identify unsafe evacuation behaviors.", "bloom_level": "remember"},
        {"id": "lo_apply", "text": "Apply the emergency evacuation checklist in a cabin scenario.", "bloom_level": "apply"},
        {"id": "lo_evaluate", "text": "Evaluate passenger readiness before opening an exit.", "bloom_level": "evaluate"},
    ]
    block_text = " ".join(["This lesson explains the concept with practical airline workplace examples."] * 35)
    modules = []
    for module_index in range(3):
        lessons = []
        for lesson_index in range(2):
            lessons.append({
                "id": f"lesson_{module_index}_{lesson_index}",
                "title": f"Lesson {module_index}-{lesson_index}",
                "duration_minutes": 8,
                "objective_ids": ["lo_apply"],
                "content_blocks": [
                    {"id": "cb_intro", "type": "intro", "text": block_text},
                    {"id": "cb_explanation", "type": "explanation", "text": block_text},
                    {"id": "cb_example", "type": "example", "text": block_text},
                    {"id": "cb_practice", "type": "practice", "text": block_text},
                    {"id": "cb_summary", "type": "summary", "text": block_text},
                ],
                "activities": [{"id": "act_1", "type": "decision_tree", "title": "Evacuation decision", "instructions": "Choose the safest decision based on passenger readiness.", "objective_ids": ["lo_apply"]}],
                "quiz_questions": [],
            })
        modules.append({"id": f"module_{module_index}", "title": f"Module {module_index}", "duration_minutes": 20, "objective_ids": ["lo_apply"], "lessons": lessons})
    questions = []
    for i in range(6):
        questions.append({
            "id": f"q_{i}",
            "type": "scenario" if i == 0 else "mcq",
            "objective_ids": ["lo_apply"],
            "question": "What is the safest action in this realistic emergency scenario?",
            "options": ["Follow checklist", "Open exit immediately", "Ignore passenger", "Wait silently"],
            "correct_answers": ["Follow checklist"],
            "explanation": "Following the checklist is correct because it verifies conditions before action and reduces risk.",
        })
    return {
        "course_title": "Emergency Evacuation for Cabin Crew",
        "audience": "Cabin crew",
        "learning_objectives": objectives,
        "modules": modules,
        "final_assessment": {"questions": questions},
    }


def test_quality_validator_flags_thin_course():
    course = {
        "course_title": "AI",
        "learning_objectives": ["Understand AI"],
        "modules": [{"title": "Module", "lessons": [{"title": "Core lesson", "content_blocks": [{"type": "explanation", "text": "Explain the concept."}]}]}],
        "final_assessment": {"questions": []},
    }
    result = validate_instructional_quality(course)
    assert result["status"] in {"failed", "needs_review"}
    assert result["score"] < 75
    assert any(issue["code"] in {"course_too_short", "placeholder_content", "thin_lessons"} for issue in result["issues"])


def test_quality_validator_approves_strong_course():
    result = validate_instructional_quality(_good_course())
    assert result["score"] >= 75
    assert result["metrics"]["lesson_count"] == 6
    assert result["metrics"]["activity_count"] == 6
