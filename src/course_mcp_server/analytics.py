from __future__ import annotations

import hashlib
from datetime import date, timedelta


def summarize_course_metrics(*, project_id: str, events: list[dict]) -> dict:
    scores = [int(event.get("score", 0)) for event in events if event.get("score") is not None]
    durations = [int(event.get("duration_seconds", 0)) for event in events]
    return {
        "project_id": project_id,
        "attempt_count": len(events),
        "completion_count": sum(1 for event in events if event.get("event_type") == "completed"),
        "average_score": round(sum(scores) / len(scores), 2) if scores else 0,
        "time_spent_seconds": sum(durations),
        "learner_count": len({event.get("learner_id") for event in events if event.get("learner_id")}),
    }


def issue_certificate(
    *,
    project_id: str,
    learner_id: str,
    learner_name: str,
    course_title: str,
    score: int,
    valid_days: int,
) -> dict:
    issued = date.today()
    digest = hashlib.sha256(f"{project_id}:{learner_id}:{issued.isoformat()}".encode()).hexdigest()[:12]
    return {
        "certificate_id": f"cert_{digest}",
        "project_id": project_id,
        "learner_id": learner_id,
        "learner_name": learner_name,
        "course_title": course_title,
        "score": score,
        "issued_date": issued.isoformat(),
        "recertification_due_date": (issued + timedelta(days=valid_days)).isoformat(),
    }
