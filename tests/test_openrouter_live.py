import os

import pytest

from course_mcp_server.llm_openrouter import OpenRouterClient


@pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY is required for live OpenRouter smoke test",
)
def test_live_openrouter_returns_json():
    result = OpenRouterClient().generate_json(
        system_prompt="Return only JSON.",
        user_payload={"instruction": "Return {\"ok\": true}."},
        schema_name="SmokeTest",
    )

    assert isinstance(result, dict)
