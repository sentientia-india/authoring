from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from .storage import storage_backend


def store_artifact_metadata(*, project_id: str, artifact_type: str, package_path: str) -> dict:
    file_name = Path(package_path).name
    digest = hashlib.sha256(f"{project_id}:{artifact_type}:{file_name}".encode()).hexdigest()[:12]
    metadata = {
        "artifact_id": f"artifact_{digest}",
        "project_id": project_id,
        "artifact_type": artifact_type,
        "artifact_uri": f"artifact://{project_id}/{digest}/{file_name}",
        "file_name": file_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    storage_backend().append_artifact(metadata)
    return metadata
