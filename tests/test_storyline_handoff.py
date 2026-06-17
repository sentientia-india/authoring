from pathlib import Path
from zipfile import ZipFile

from course_mcp_server.storyline_handoff import build_storyline_handoff_package


def test_storyline_handoff_package(tmp_path: Path):
    course = {
        "course_title": "Emergency Evacuation",
        "course_slug": "emergency-evacuation",
        "audience": "Cabin crew",
        "difficulty": "beginner",
        "estimated_duration_minutes": 45,
        "learning_objectives": [{"id": "lo_apply", "text": "Apply the evacuation checklist."}],
        "modules": [{
            "title": "Evacuation Basics",
            "lessons": [{
                "title": "Assess Conditions",
                "duration_minutes": 10,
                "objective_ids": ["lo_apply"],
                "content_blocks": [{"type": "intro", "text": "Assess before opening the exit."}],
                "activities": [{"id": "act_1", "type": "decision_tree", "title": "Choose", "instructions": "Choose the correct action."}],
            }],
        }],
        "final_assessment": {"questions": [{
            "id": "q_1",
            "type": "mcq",
            "question": "What should you do first?",
            "options": ["Assess", "Open"],
            "correct_answers": ["Assess"],
            "explanation": "Assessment prevents unsafe actions.",
            "objective_ids": ["lo_apply"],
        }]},
    }
    result = build_storyline_handoff_package(course, tmp_path)
    assert result["native_story_file_generated"] is False
    with ZipFile(result["package_path"]) as zf:
        names = set(zf.namelist())
    assert "storyboard.md" in names
    assert "quiz_import.csv" in names
    assert "storyline_build_spec.json" in names
