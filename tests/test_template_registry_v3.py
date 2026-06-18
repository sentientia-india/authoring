from pathlib import Path

from course_mcp_server.course_templates import TemplateRegistry


def test_template_registry_loads_and_selects_airline_template():
    template_dir = Path(__file__).resolve().parents[1] / "src" / "course_mcp_server" / "templates"
    registry = TemplateRegistry(template_dir).load()
    assert len(registry.list_templates()) >= 5
    match = registry.select_template(
        topic="Emergency evacuation for cabin crew",
        audience="Cabin crew",
        industry="airline",
        delivery_mode="simulation",
    )
    assert match.template.template_id == "airline_safety_simulation"
    assert "interactive_video" in match.template.recommended_interactions


def test_template_quality_rules_are_present():
    template_dir = Path(__file__).resolve().parents[1] / "src" / "course_mcp_server" / "templates"
    template = TemplateRegistry(template_dir).load().get("airline_safety_simulation")
    assert template.quality_rules["min_source_coverage"] >= 0.8
    assert template.gamification.unlock_mode == "mission_map"
