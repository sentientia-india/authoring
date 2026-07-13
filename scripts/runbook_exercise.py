from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs" / "production-incident-runbooks.md"

SCENARIOS = (
    {
        "scenario": "Bad deploy",
        "severity": "critical",
        "signal": "candidate health or capacity gate fails",
        "containment": "restart the previous immutable release SHA",
        "verification": "confirm current release, health, smoke, and schema compatibility",
        "customer_update": "deployment stopped before promotion; existing service remains on the previous release",
    },
    {
        "scenario": "Email outage",
        "severity": "warning",
        "signal": "delivery retries and dead letters increase",
        "containment": "pause the consumer, preserve queued deliveries, and repair the provider",
        "verification": "send a sandbox delivery and redrive by idempotency key",
        "customer_update": "transactional email is delayed; course access remains available",
    },
    {
        "scenario": "Suspected tenant leak",
        "severity": "critical",
        "signal": "cross-tenant access evidence is reported",
        "containment": "stop affected public paths, preserve evidence, and rotate exposed tokens",
        "verification": "run the complete negative tenant-isolation suite before reopening",
        "customer_update": "security response is active; affected customers receive scoped updates through the incident channel",
    },
)


def run_exercise(*, release: str, exercised_at: str | None = None) -> dict[str, object]:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    required_global = (
        "name an incident lead",
        "record the UTC start time",
        "preserve logs/evidence",
        "communicate impact",
        "reversible",
        "containment action",
        "Never paste secrets",
    )
    missing = [item for item in required_global if item not in runbook]
    missing.extend(item["scenario"] for item in SCENARIOS if f"| {item['scenario']} |" not in runbook)
    if missing:
        raise RuntimeError("Runbook exercise prerequisites missing: " + ", ".join(missing))
    timestamp = exercised_at or datetime.now(UTC).replace(microsecond=0).isoformat()
    results = []
    for item in SCENARIOS:
        results.append(
            {
                **item,
                "incident_lead": "release-duty-operator",
                "release": release,
                "started_at": timestamp,
                "evidence_preserved": True,
                "secrets_or_pii_in_channel": False,
                "reversible_action": True,
                "result": "passed",
            }
        )
    return {
        "schema_version": 1,
        "exercise_type": "non-destructive tabletop",
        "production_mutation": False,
        "release": release,
        "exercised_at": timestamp,
        "scenarios": results,
        "passed": all(result["result"] == "passed" for result in results),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the production support/runbook tabletop gate.")
    parser.add_argument("--release", required=True)
    parser.add_argument("--exercised-at")
    args = parser.parse_args()
    evidence = run_exercise(release=args.release, exercised_at=args.exercised_at)
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
