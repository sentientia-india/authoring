from course_mcp_server.analytics import export_csv, issue_certificate, summarize_course_metrics


def test_csv_export_is_stable_and_complete():
    output = export_csv([{"learners": 2, "course": "A"}, {"course": "B", "learners": 3}])
    assert output.splitlines()[0] == "course,learners"
    assert "A,2" in output and "B,3" in output


def test_portable_summary_and_certificate_contract_remains_available():
    metrics = summarize_course_metrics(
        project_id="course_1",
        events=[{"learner_id": "l1", "event_type": "completed", "score": 90, "duration_seconds": 60}],
    )
    certificate = issue_certificate(
        project_id="course_1",
        learner_id="l1",
        learner_name="Learner",
        course_title="Course",
        score=90,
        valid_days=365,
    )
    assert metrics["completion_count"] == 1
    assert certificate["certificate_id"].startswith("cert_")
