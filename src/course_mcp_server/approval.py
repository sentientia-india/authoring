from __future__ import annotations

import os
from dataclasses import dataclass

HIGH_RISK_ACTIONS = {"publish_to_lms", "upload_to_lms", "send_to_external_system"}


@dataclass(frozen=True)
class ApprovalDecision:
    allowed: bool
    action: str
    reason: str


def require_human_approval(action: str) -> ApprovalDecision:
    if action not in HIGH_RISK_ACTIONS:
        return ApprovalDecision(allowed=True, action=action, reason="Action does not require approval.")

    if os.getenv("ALLOW_PUBLISH_TO_LMS", "false").lower() == "true":
        return ApprovalDecision(allowed=True, action=action, reason="High-risk action explicitly enabled.")

    return ApprovalDecision(
        allowed=False,
        action=action,
        reason=f"Human approval is required for high-risk action: {action}",
    )
