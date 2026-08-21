from course_mcp_server.course_generator import generate_outline
from course_mcp_server.schemas import CourseOutlineRequest
from course_mcp_server.text_providers import TextProviderError


def test_generator_uses_deterministic_output_without_openrouter_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    result = generate_outline(
        CourseOutlineRequest(topic="Ramp Safety", audience="ground staff", duration_minutes=60)
    )

    assert result["course_title"] == "Ramp Safety for ground staff"
    assert result["generation_provider"] == "deterministic"
    # No explicit provider was requested and none is configured -- this is the normal/expected
    # graceful degradation, so no error should be surfaced.
    assert result["generation_provider_error"] is None
    assert result["generation_model"] is None
    # No real provider was used on the deterministic-fallback path, so there is no key source.
    assert result["generation_key_source"] is None


def test_generator_uses_openrouter_when_key_is_configured(monkeypatch):
    # generate_outline() now routes through text_providers/registry.py's get_text_provider()
    # (req.text_provider, default "openrouter") instead of constructing OpenRouterClient
    # directly -- see course_generator.py. Patch the registry factory it actually calls.
    class FakeConfig:
        enabled = True
        model = "nvidia/nemotron-3-ultra-550b-a55b:free"

    class FakeProvider:
        config = FakeConfig()
        key_source = "env"

        def generate_json(self, system_prompt, user_payload, schema_name, *, model=None):
            assert "safe e-learning course outlines" in system_prompt
            assert schema_name == "CourseOutline"
            assert user_payload["topic"] == "Ramp Safety"
            # Provider-selection/BYO-key fields must never reach the LLM payload.
            assert "text_provider" not in user_payload
            assert "text_provider_api_key" not in user_payload
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

    def fake_get_text_provider(provider_id, *, api_key=None, base_url=None, model=None):
        assert provider_id == "openrouter"
        return FakeProvider()

    monkeypatch.setattr("course_mcp_server.course_generator.get_text_provider", fake_get_text_provider)

    result = generate_outline(
        CourseOutlineRequest(topic="Ramp Safety", audience="ground staff", duration_minutes=60)
    )

    assert result["course_title"] == "AI Ramp Safety"
    # generation_provider now records the real provider_id used, not a "provider:model" label.
    assert result["generation_provider"] == "openrouter"
    # ... but the specific model actually used is still recoverable, via a sibling field.
    assert result["generation_model"] == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert result["generation_provider_error"] is None
    # generation_key_source mirrors the provider's own .key_source ("env" here).
    assert result["generation_key_source"] == "env"


def test_generator_surfaces_error_when_explicit_provider_genuinely_fails(monkeypatch):
    # The caller explicitly asked for "anthropic" with their own key. If that call genuinely
    # fails, the caller needs a way to detect it -- not just silently see "deterministic".
    class FakeConfig:
        enabled = True
        model = "claude-opus-5"

    class FailingProvider:
        config = FakeConfig()

        def generate_json(self, system_prompt, user_payload, schema_name, *, model=None):
            raise TextProviderError("Anthropic request failed with status 401")

    def fake_get_text_provider(provider_id, *, api_key=None, base_url=None, model=None):
        assert provider_id == "anthropic"
        return FailingProvider()

    monkeypatch.setattr("course_mcp_server.course_generator.get_text_provider", fake_get_text_provider)

    result = generate_outline(
        CourseOutlineRequest(
            topic="Ramp Safety",
            audience="ground staff",
            duration_minutes=60,
            text_provider="anthropic",
            text_provider_api_key="sk-ant-test-key",
        )
    )

    # Still degrades to the deterministic outline (this is not a hard failure of the whole call)...
    assert result["generation_provider"] == "deterministic"
    assert result["course_title"] == "Ramp Safety for ground staff"
    # ...but the caller can now detect that their explicitly-requested provider genuinely failed.
    assert result["generation_provider_error"] is not None
    assert "anthropic" in result["generation_provider_error"]
    assert "401" in result["generation_provider_error"]
    # No real provider succeeded, so there is no key source to report.
    assert result["generation_key_source"] is None


def test_generator_truncates_oversized_provider_error_to_schema_limit(monkeypatch):
    # A malformed provider response can produce a very long error message (e.g. a Pydantic
    # ValidationError.str() dump). CourseOutline.generation_provider_error declares
    # max_length=500 (schemas.py) -- the generator must truncate to fit rather than writing the
    # raw dict field and skipping model re-validation (which would silently bypass the limit).
    class FakeConfig:
        enabled = True
        model = "claude-opus-5"

    huge_error_message = "Anthropic request failed: " + ("x" * 1000)

    class FailingProvider:
        config = FakeConfig()

        def generate_json(self, system_prompt, user_payload, schema_name, *, model=None):
            raise TextProviderError(huge_error_message)

    def fake_get_text_provider(provider_id, *, api_key=None, base_url=None, model=None):
        return FailingProvider()

    monkeypatch.setattr("course_mcp_server.course_generator.get_text_provider", fake_get_text_provider)

    result = generate_outline(
        CourseOutlineRequest(
            topic="Ramp Safety",
            audience="ground staff",
            duration_minutes=60,
            text_provider="anthropic",
            text_provider_api_key="sk-ant-test-key",
        )
    )

    assert result["generation_provider_error"] is not None
    assert len(result["generation_provider_error"]) <= 500
    assert result["generation_provider_error"].endswith("...")
    # Re-validating through the real CourseOutline model must also pass (proves the field's
    # declared max_length=500 is genuinely enforced end-to-end, not just eyeballed here).
    from course_mcp_server.schemas import CourseOutline

    CourseOutline.model_validate(result)
