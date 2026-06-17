from course_mcp_server.analytics import issue_certificate, summarize_course_metrics
from course_mcp_server.activities import build_activity
from course_mcp_server.quality import validate_course_quality


def test_h5p_style_activity_types_have_interaction_schema():
    activity = build_activity(
        project_id="course_abc12345",
        activity_type="matching",
        objective="Match each safety signal to the correct action.",
    )

    assert activity["activity_type"] == "matching"
    assert activity["h5p_style"] is True
    assert activity["items"]
    assert activity["scoring"]["completion_event"] == "xAPI.completed"


def test_quality_validator_scores_alignment_and_source_grounding():
    project = {
        "sources": [{"source_id": "source_1", "extracted_text": "Inspect the aircraft door before arming."}],
        "artifacts": [
            {
                "artifact_type": "blueprint",
                "payload": {"learning_objectives": ["Inspect aircraft doors before arming."]},
            },
            {"artifact_type": "modules", "payload": {"modules": [{"module_id": "module_1"}]}},
            {
                "artifact_type": "lessons",
                "payload": {
                    "lessons": [
                        {
                            "objective": "Inspect aircraft doors before arming.",
                            "content_blocks": [{"text": "Inspect the aircraft door before arming."}],
                            "citations": [{"source_id": "source_1", "reference": "line:1"}],
                        }
                    ]
                },
            },
            {
                "artifact_type": "assessment",
                "payload": {
                    "questions": [
                        {
                            "objective": "Inspect aircraft doors before arming.",
                            "question": "What should be inspected before arming?",
                        }
                    ]
                },
            },
        ],
    }

    result = validate_course_quality(project)

    assert result["score"] >= 90
    assert result["status"] == "passed"


def test_analytics_summary_and_certificate_are_structured():
    metrics = summarize_course_metrics(
        project_id="course_abc12345",
        events=[
            {"learner_id": "l1", "event_type": "completed", "score": 92, "duration_seconds": 300},
            {"learner_id": "l1", "event_type": "attempted", "score": 80, "duration_seconds": 120},
        ],
    )
    certificate = issue_certificate(
        project_id="course_abc12345",
        learner_id="l1",
        learner_name="Learner One",
        course_title="Safety",
        score=92,
        valid_days=365,
    )

    assert metrics["completion_count"] == 1
    assert metrics["attempt_count"] == 2
    assert certificate["certificate_id"].startswith("cert_")
    assert certificate["recertification_due_date"]
