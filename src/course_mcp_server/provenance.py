"""Signed export provenance without exposing license keys."""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any


def sign_export(course_id: str, tenant: str, tier: str) -> dict[str, Any]:
    secret = os.getenv("EXPORT_SIGNING_SECRET", "")
    if not secret:
        return {"signed": False, "course_id": course_id, "tenant": tenant, "tier": tier}
    message = f"{course_id}:{tenant}:{tier}"
    signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return {
        "signed": True,
        "course_id": course_id,
        "tenant": tenant,
        "tier": tier,
        "algorithm": "HMAC-SHA256",
        "signature": signature,
    }


def verify_export_stamp(stamp: dict[str, Any]) -> bool:
    if not stamp.get("signed"):
        return False
    expected = sign_export(str(stamp["course_id"]), str(stamp["tenant"]), str(stamp["tier"]))
    return hmac.compare_digest(str(expected.get("signature", "")), str(stamp.get("signature", "")))

