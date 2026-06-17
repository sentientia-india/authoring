from course_mcp_server.approval import ApprovalDecision, require_human_approval


def test_publish_action_requires_human_approval_by_default(monkeypatch):
    monkeypatch.delenv("ALLOW_PUBLISH_TO_LMS", raising=False)

    decision = require_human_approval("publish_to_lms")

    assert decision == ApprovalDecision(
        allowed=False,
        action="publish_to_lms",
        reason="Human approval is required for high-risk action: publish_to_lms",
    )


def test_publish_action_can_be_enabled_explicitly(monkeypatch):
    monkeypatch.setenv("ALLOW_PUBLISH_TO_LMS", "true")

    decision = require_human_approval("publish_to_lms")

    assert decision.allowed is True
