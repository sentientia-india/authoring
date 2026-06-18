from course_mcp_server.advanced_quality_gates import evaluate_superior_quality


def repeated_course():
    text = "Emergency Evacuation for Cabin Crew requires learners to understand the standard procedure. " * 6
    return {
        "learning_objectives": [{"id": "lo_1"}, {"id": "lo_2"}],
        "modules": [
            {"lessons": [
                {"title": "Lesson A", "content_blocks": [{"type": "explanation", "text": text, "source_refs": []}], "quiz_questions": []},
                {"title": "Lesson B", "content_blocks": [{"type": "explanation", "text": text, "source_refs": []}], "quiz_questions": []},
            ]}
        ],
        "final_assessment": {"questions": []},
    }


def improved_course():
    return {
        "learning_objectives": [{"id": "lo_1"}, {"id": "lo_2"}],
        "modules": [
            {"lessons": [
                {
                    "title": "Assess usable exits",
                    "content_blocks": [
                        {"type": "explanation", "text": "Crew check smoke direction, door status, slide indication, and command confirmation before opening an exit.", "source_refs": [{"source_id": "s1"}]},
                        {"type": "scenario", "text": "In the cabin, a passenger blocks the aisle near the overwing exit while the captain commands evacuation.", "source_refs": [{"source_id": "s1"}]},
                    ],
                    "activities": [{"type": "decision_tree", "instructions": "Choose the first command and action for the passenger blocking the aisle."}],
                    "quiz_questions": [{"objective_ids": ["lo_1"]}],
                },
                {
                    "title": "Direct passenger flow",
                    "content_blocks": [
                        {"type": "explanation", "text": "Crew use short assertive commands and redirect passengers away from blocked exits while monitoring slide crowding.", "source_refs": [{"source_id": "s2"}]},
                        {"type": "scenario", "text": "At the rear galley, smoke increases and passengers try to retrieve bags before reaching the slide.", "source_refs": [{"source_id": "s2"}]},
                    ],
                    "activities": [{"type": "hotspot", "instructions": "Identify unsafe passenger behavior in the cabin diagram."}],
                    "quiz_questions": [{"objective_ids": ["lo_2"]}],
                },
            ]}
        ],
        "final_assessment": {"questions": [{"objective_ids": ["lo_1"]}, {"objective_ids": ["lo_2"]}]},
    }


def test_quality_gate_fails_repetition():
    report = evaluate_superior_quality(repeated_course(), domain="airline")
    assert report["status"] == "fail"
    assert any(issue["code"] == "LESSON_TOO_SIMILAR" for issue in report["issues"])
    assert any(issue["code"] == "LOW_SOURCE_COVERAGE" for issue in report["issues"])


def test_quality_gate_passes_stronger_course():
    report = evaluate_superior_quality(improved_course(), domain="airline", min_source_coverage=0.7)
    assert report["status"] in {"pass", "needs_review"}
    assert report["component_scores"]["source_grounding"] == 100
