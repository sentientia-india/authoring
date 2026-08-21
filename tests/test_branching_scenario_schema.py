"""Tests for the server-side BranchingScenario schema (P5-4e).

The two fixtures below are copied verbatim (not invented) from
apps/scorm_editor/frontend/src/editor.js's ACTIVITY_TEMPLATE_REGISTRY:

  - `decision.build()`  -> activity_type "scenario_decision_tree"
  - `branching.build()` -> activity_type "branching_scenario"

Both templates produce the exact same underlying item shape
(`items: [{scenario, choices: [{label, result, feedback}]}]`); the only
difference is that `branching_scenario` also carries a `persona`. This
confirms the finding recorded in schemas.py's BranchingScenario docstring:
the two activity-type labels are one data shape, not two.

A third fixture is copied from tests/fixtures/agile_course_content.json,
which is the real payload already accepted by submit_course_content today.
Its `decision_tree` activities write a *flat* single scene
(`{"scenario": ..., "choices": [...]}`, no `items` wrapper) -- a second,
legacy write-convention for the same node concept that the schema must
also accept so existing accepted content keeps validating.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from course_mcp_server.schemas import BranchingScenario
from course_mcp_server.security import RequestContext
from course_mcp_server.tools import create_course_project, submit_course_content


def _ctx() -> RequestContext:
    return RequestContext(tenant_id="tenant-a", user_id="user-a", token="token", request_id="req1")


# Verbatim from editor.js ACTIVITY_TEMPLATE_REGISTRY.decision.build()
DECISION_TEMPLATE_ITEMS = {
    "items": [
        {
            "scenario": "Describe the situation…",
            "choices": [
                {"label": "Best action", "result": "best", "feedback": "Why this is right."},
                {"label": "Risky action", "result": "risk", "feedback": "Why this backfires."},
            ],
        }
    ]
}

# Verbatim from editor.js ACTIVITY_TEMPLATE_REGISTRY.branching.build()
BRANCHING_TEMPLATE_DATA = {
    "persona": {"name": "Alex", "role": "Stakeholder"},
    "items": [
        {
            "scenario": "Alex opens with…",
            "choices": [
                {"label": "Strong reply", "result": "best", "feedback": "Great choice."},
                {"label": "Weak reply", "result": "risk", "feedback": "This loses trust."},
            ],
        }
    ],
}


def test_decision_template_round_trips_without_data_loss():
    scenario = BranchingScenario.model_validate(DECISION_TEMPLATE_ITEMS)
    assert scenario.persona is None
    assert len(scenario.nodes) == 1
    node = scenario.nodes[0]
    assert node.scenario == "Describe the situation…"
    assert node.id  # back-filled since editor.js never assigns scene ids
    labels = [choice.label for choice in node.choices]
    assert labels == ["Best action", "Risky action"]
    best, risky = node.choices
    assert best.result == "best" and best.feedback == "Why this is right." and best.is_terminal is True
    assert risky.result == "risk" and risky.feedback == "Why this backfires." and risky.is_terminal is True

    dumped = scenario.model_dump(by_alias=True, exclude_none=True)
    assert dumped["items"][0]["scenario"] == "Describe the situation…"
    assert dumped["items"][0]["choices"][0]["label"] == "Best action"
    assert dumped["items"][0]["choices"][1]["feedback"] == "Why this backfires."


def test_branching_template_round_trips_without_data_loss():
    scenario = BranchingScenario.model_validate(BRANCHING_TEMPLATE_DATA)
    assert scenario.persona is not None
    assert scenario.persona.name == "Alex"
    assert scenario.persona.role == "Stakeholder"
    assert len(scenario.nodes) == 1
    node = scenario.nodes[0]
    assert node.scenario == "Alex opens with…"
    labels = [choice.label for choice in node.choices]
    assert labels == ["Strong reply", "Weak reply"]

    dumped = scenario.model_dump(by_alias=True, exclude_none=True)
    assert dumped["persona"] == {"name": "Alex", "role": "Stakeholder"}
    assert dumped["items"][0]["scenario"] == "Alex opens with…"


def test_legacy_flat_decision_tree_shape_still_validates():
    """The `decision_tree` activities in tests/fixtures/agile_course_content.json
    (real, already-accepted content) write a single scene directly at the top
    level instead of wrapping it in `items`. The schema must still accept
    this so existing submissions do not regress.
    """
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "agile_course_content.json").read_text(encoding="utf-8")
    )
    flat_decision_data = None
    for module in fixture["modules"]:
        for lesson in module["lessons"]:
            for activity in lesson.get("activities", []):
                if activity["type"] == "decision_tree":
                    flat_decision_data = activity["data"]
                    break
    assert flat_decision_data is not None, "fixture should still contain a decision_tree activity"
    assert "items" not in flat_decision_data  # confirms this really is the flat legacy shape

    scenario = BranchingScenario.model_validate(flat_decision_data)
    assert len(scenario.nodes) == 1
    assert scenario.nodes[0].scenario == flat_decision_data["scenario"]
    assert len(scenario.nodes[0].choices) == len(flat_decision_data["choices"])


def test_multi_node_graph_with_valid_next_node_id_validates():
    scenario = BranchingScenario.model_validate(
        {
            "items": [
                {
                    "id": "start",
                    "scenario": "Opening scene.",
                    "choices": [
                        {"label": "Continue", "next_node_id": "end"},
                        {"label": "Bail out", "feedback": "You gave up early.", "is_terminal": True},
                    ],
                },
                {
                    "id": "end",
                    "scenario": "Closing scene.",
                    "choices": [{"label": "Finish", "feedback": "Well done.", "is_terminal": True}],
                },
            ]
        }
    )
    continue_choice = scenario.nodes[0].choices[0]
    assert continue_choice.next_node_id == "end"
    assert continue_choice.is_terminal is False  # derived, not the literal input value


def test_dangling_next_node_id_is_rejected():
    with pytest.raises(ValidationError) as excinfo:
        BranchingScenario.model_validate(
            {
                "items": [
                    {
                        "id": "start",
                        "scenario": "Opening scene.",
                        "choices": [{"label": "Continue", "next_node_id": "nonexistent_node"}],
                    }
                ]
            }
        )
    assert "next_node_id" in str(excinfo.value)
    assert "nonexistent_node" in str(excinfo.value)


def test_duplicate_node_ids_are_rejected():
    with pytest.raises(ValidationError) as excinfo:
        BranchingScenario.model_validate(
            {
                "items": [
                    {"id": "dup", "scenario": "First.", "choices": [{"label": "Go", "feedback": "ok"}]},
                    {"id": "dup", "scenario": "Second.", "choices": [{"label": "Go", "feedback": "ok"}]},
                ]
            }
        )
    assert "duplicate" in str(excinfo.value)


def test_empty_choices_rejected():
    with pytest.raises(ValidationError):
        BranchingScenario.model_validate({"items": [{"scenario": "No choices here.", "choices": []}]})


def test_title_round_trips_through_model_validate_and_model_dump():
    """AI-generated `title` (see branching-scenario-ai.js's system prompt, which asks for
    `{"title": string, ...}`) must survive validate/dump so apps/scorm_editor/server.py's
    `_validate_ai_result_schema` -- which re-serializes via `model_dump(mode="json",
    by_alias=True)` -- passes the real generated title through instead of silently dropping it
    (Pydantic's default extra="ignore" behavior for undeclared fields).
    """
    scenario = BranchingScenario.model_validate(
        {
            "title": "Handling an upset stakeholder",
            "persona": {"name": "Dana", "role": "Stakeholder"},
            "items": [
                {
                    "scenario": "Dana is upset about the delay.",
                    "choices": [{"label": "Acknowledge and propose a plan", "feedback": "Good move."}],
                }
            ],
        }
    )
    assert scenario.title == "Handling an upset stakeholder"

    dumped = scenario.model_dump(mode="json", by_alias=True)
    assert dumped["title"] == "Handling an upset stakeholder"


def test_missing_title_still_validates_for_backward_compatibility():
    """Existing content (including both fixtures above) never wrote a `title` field inside the
    branching-scenario activity `data` object -- the activity's own top-level `title` is separate.
    `title` must stay optional so this pre-existing content keeps validating unchanged.
    """
    scenario = BranchingScenario.model_validate(DECISION_TEMPLATE_ITEMS)
    assert scenario.title is None

    dumped = scenario.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert "title" not in dumped


def test_submit_course_content_rejects_malformed_branching_activity(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSE_PROJECT_STORE_PATH", str(tmp_path / "projects.json"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    context = _ctx()
    project = create_course_project(
        {"course_title": "Branching QA", "audience": "reviewers", "language": "English"}, context
    )
    project_id = project["data"]["project_id"]

    payload = {
        "project_id": project_id,
        "learning_objectives": [{"id": "lo_1", "text": "Handle a difficult stakeholder conversation well."}],
        "modules": [
            {
                "id": "module_1",
                "title": "Difficult Conversations",
                "duration_minutes": 15,
                "objective_ids": ["lo_1"],
                "lessons": [
                    {
                        "id": "lesson_1",
                        "title": "Staying calm under pressure",
                        "duration_minutes": 15,
                        "objective_ids": ["lo_1"],
                        "content_blocks": [
                            {
                                "id": "cb_1",
                                "type": "intro",
                                "text": "Staying composed under pressure protects the relationship and the outcome.",
                            }
                        ],
                        "activities": [
                            {
                                "id": "act_broken",
                                "type": "branching_scenario",
                                "title": "Talk it through",
                                "instructions": "Choose how to respond to the stakeholder.",
                                "data": {
                                    "persona": {"name": "Dana", "role": "Stakeholder"},
                                    "items": [
                                        {
                                            "id": "start",
                                            "scenario": "Dana is upset about the delay.",
                                            "choices": [
                                                {
                                                    "label": "Acknowledge and propose a plan",
                                                    "next_node_id": "does_not_exist",
                                                }
                                            ],
                                        }
                                    ],
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    }

    result = submit_course_content(payload, context)
    assert result["ok"] is False
    assert result["error"] == "invalid_branching_scenario"
    assert result["data"]["errors"]
    assert "act_broken" in result["data"]["errors"][0]
