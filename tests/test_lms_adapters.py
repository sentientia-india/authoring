from course_mcp_server.lms_adapters import build_publish_plan


def test_lms_publish_plans_require_approval_and_secrets():
    moodle = build_publish_plan("moodle")
    canvas = build_publish_plan("canvas")
    custom = build_publish_plan("custom")

    assert moodle["approval_required"] is True
    assert "MOODLE_TOKEN" in moodle["required_secret_names"]
    assert "CANVAS_OAUTH_TOKEN" in canvas["required_secret_names"]
    assert "CUSTOM_LMS_TOKEN" in custom["required_secret_names"]
