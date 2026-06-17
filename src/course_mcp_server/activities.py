from __future__ import annotations


def build_activity(*, project_id: str, activity_type: str, objective: str) -> dict:
    title = f"{activity_type.replace('_', ' ').title()} Activity"
    base = {
        "project_id": project_id,
        "activity_id": "activity_1",
        "activity_type": activity_type,
        "title": title,
        "objective": objective,
        "h5p_style": True,
        "scoring": {
            "completion_event": "xAPI.completed",
            "score_event": "xAPI.answered",
            "passing_score": 80,
        },
    }
    if activity_type == "matching":
        items = [
            {"prompt": "Safe action", "match": "Verify with source or SOP"},
            {"prompt": "Risky action", "match": "Guess without checking"},
        ]
    elif activity_type == "timeline":
        items = [
            {"step": 1, "label": "Prepare", "detail": "Review the source material."},
            {"step": 2, "label": "Practice", "detail": objective},
            {"step": 3, "label": "Prove", "detail": "Complete the assessment."},
        ]
    elif activity_type in {"scenario_decision_tree", "branching_scenario"}:
        items = [
            {
                "scenario": "A learner faces a realistic decision.",
                "choices": [
                    {"label": "Follow the documented process", "result": "best"},
                    {"label": "Skip verification", "result": "risk"},
                ],
            }
        ]
    elif activity_type == "fill_in_blanks":
        items = [{"text": "A good response should be [specific], [checked], and [cited]."}]
    elif activity_type == "reflection_prompt":
        items = [{"prompt": f"Describe how you will apply this objective: {objective}"}]
    else:
        items = [
            {"front": "Objective", "back": objective},
            {"front": "Good practice", "back": "Use source-grounded examples and check understanding."},
        ]
    return {**base, "items": items}
