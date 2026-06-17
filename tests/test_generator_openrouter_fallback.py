from course_mcp_server.course_generator import generate_outline
from course_mcp_server.schemas import CourseOutlineRequest


def test_generator_uses_deterministic_output_without_openrouter_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    result = generate_outline(
        CourseOutlineRequest(topic="Ramp Safety", audience="ground staff", duration_minutes=60)
    )

    assert result["course_title"] == "Ramp Safety for ground staff"
    assert result["generation_provider"] == "deterministic"


def test_generator_uses_openrouter_when_key_is_configured(monkeypatch):
    class FakeConfig:
        enabled = True
        model = "nvidia/nemotron-3-ultra-550b-a55b:free"

    class FakeClient:
        config = FakeConfig()

        def generate_json(self, system_prompt, user_payload, schema_name):
            assert "safe e-learning course outlines" in system_prompt
            assert schema_name == "CourseOutline"
            assert user_payload["topic"] == "Ramp Safety"
            return {
                "course_title": "AI Ramp Safety",
                "audience": "ground staff",
                "difficulty": "beginner",
                "language": "English",
                "learning_objectives": ["Identify ramp hazards"],
                "modules": [
                    {
                        "title": "Ramp hazards",
                        "lessons": [
                            {
                                "title": "Spot hazards",
                                "objective": "Identify common hazards",
                                "duration_minutes": 10,
                            }
                        ],
                    }
                ],
                "assessment_plan": "One MCQ quiz.",
            }

    monkeypatch.setattr("course_mcp_server.course_generator.OpenRouterClient", FakeClient)

    result = generate_outline(
        CourseOutlineRequest(topic="Ramp Safety", audience="ground staff", duration_minutes=60)
    )

    assert result["course_title"] == "AI Ramp Safety"
    assert result["generation_provider"] == "openrouter:nvidia/nemotron-3-ultra-550b-a55b:free"
