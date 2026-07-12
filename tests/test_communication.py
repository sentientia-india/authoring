import pytest

from course_mcp_server.communication import CommunicationError, render_template


@pytest.mark.parametrize("template", ("invitation", "receipt", "enrollment", "completion", "dunning"))
def test_transactional_templates_render(template):
    subject, body = render_template(
        template,
        {
            "course_title": "Safety",
            "product_name": "Safety course",
            "amount": "$10.00",
            "action_url": "https://example.com/action",
        },
    )
    assert subject and body
    assert "https://example.com/action" in body


def test_template_rejects_missing_data():
    with pytest.raises(CommunicationError):
        render_template("invitation", {})
