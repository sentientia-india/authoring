from course_mcp_server.analytics import export_csv


def test_csv_export_is_stable_and_complete():
    output = export_csv([{"learners": 2, "course": "A"}, {"course": "B", "learners": 3}])
    assert output.splitlines()[0] == "course,learners"
    assert "A,2" in output and "B,3" in output
