from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


def build_delivery_metadata(*, project_id: str, artifact_type: str, package_path: str) -> dict:
    mode = os.getenv("EXPORT_DELIVERY_MODE", "download_only")
    retention_seconds = int(os.getenv("EXPORT_RETENTION_SECONDS", "86400"))
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=retention_seconds)
    return {
        "project_id": project_id,
        "artifact_type": artifact_type,
        "delivery_mode": mode,
        "storage_required": mode not in {"download_only", "bring_your_own_lms"},
        "customer_action": "download_and_upload_to_lms",
        "file_name": Path(package_path).name,
        "expires_at": expires_at.isoformat(),
        "note": "Generated file is intended for customer download and upload to their own LMS.",
    }
