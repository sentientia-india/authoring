from zipfile import ZipFile

import pytest

from course_mcp_server.hosted_learning import (
    HostedLearningError,
    capture_lead,
    course_dashboard,
    create_share,
    grade_open_answer,
    grant_paid_access,
    record_learner_event,
    resolve_share_file,
)


def _package(path):
    with ZipFile(path, "w") as package:
        package.writestr("index.html", "<h1>Course</h1>")
        package.writestr("assets/app.js", "ok")


def test_share_analytics_paid_access_and_leads(tmp_path, monkeypatch):
    monkeypatch.setenv("HOSTED_COURSE_ROOT", str(tmp_path / "hosted"))
    package = tmp_path / "course.zip"
    _package(package)
    share = create_share(package, tenant="acme", course_id="course_1", paid=True)
    with pytest.raises(HostedLearningError):
        resolve_share_file(share["share_token"], "index.html")
    access = grant_paid_access(share["share_token"], "learner@example.com")
    assert resolve_share_file(share["share_token"], "index.html", access["access_token"]).is_file()
    record_learner_event(share["share_token"], {"type": "attempt", "learner_id": "learner-1"})
    record_learner_event(share["share_token"], {"type": "score", "score": 84, "learner_id": "learner-1"})
    record_learner_event(share["share_token"], {"type": "completion", "learner_id": "learner-1"})
    assert course_dashboard(share["share_token"]) == {
        "learners": 1, "completions": 1, "attempts": 1, "average_score": 84.0
    }
    assert capture_lead(share["share_token"], "learner@example.com")["email_hash"]


def test_share_rejects_zip_slip(tmp_path, monkeypatch):
    monkeypatch.setenv("HOSTED_COURSE_ROOT", str(tmp_path / "hosted"))
    package = tmp_path / "bad.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr("../escape.txt", "bad")
    with pytest.raises(HostedLearningError):
        create_share(package, tenant="acme", course_id="course_1")


def test_open_answer_grading_requires_human_review_when_partial():
    result = grade_open_answer("Check the door and communicate", ["check the door", "assess smoke"])
    assert result["score"] == 50
    assert result["needs_human_review"] is True
