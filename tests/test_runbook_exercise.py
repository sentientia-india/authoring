import json
from pathlib import Path

from scripts.runbook_exercise import run_exercise


ROOT = Path(__file__).resolve().parents[1]


def test_runbook_tabletop_exercises_critical_and_provider_incidents():
    evidence = run_exercise(release="abc123", exercised_at="2026-07-13T12:00:00+00:00")
    assert evidence["passed"] is True
    assert evidence["production_mutation"] is False
    assert len(evidence["scenarios"]) == 3
    assert {scenario["scenario"] for scenario in evidence["scenarios"]} == {
        "Bad deploy",
        "Email outage",
        "Suspected tenant leak",
    }
    for scenario in evidence["scenarios"]:
        assert scenario["incident_lead"]
        assert scenario["evidence_preserved"] is True
        assert scenario["secrets_or_pii_in_channel"] is False
        assert scenario["reversible_action"] is True
        assert scenario["customer_update"]


def test_stored_runbook_exercise_evidence_is_complete_and_passed():
    evidence = json.loads(
        (ROOT / "docs" / "evidence" / "support-runbook-2026-07-13.json").read_text(encoding="utf-8")
    )
    assert evidence["passed"] is True
    assert evidence["production_mutation"] is False
    assert len(evidence["release"]) == 40
    assert {result["scenario"] for result in evidence["scenario_results"]} == {
        "Bad deploy",
        "Email outage",
        "Suspected tenant leak",
    }
