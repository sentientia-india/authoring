from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class JsonStorageBackend:
    def __init__(self, path: Path | str | None = None) -> None:
        default_dir = Path(os.getenv("OUTPUT_DIR", "course_mcp_output"))
        self.path = Path(path or os.getenv("APP_STORE_PATH", str(default_dir / "store.json"))).resolve()

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"projects": [], "jobs": [], "audit": [], "artifacts": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def upsert_project(self, project: dict[str, Any]) -> dict[str, Any]:
        data = self._read()
        data["projects"] = [
            item
            for item in data.get("projects", [])
            if not (
                item.get("tenant_id") == project.get("tenant_id")
                and item.get("project_id") == project.get("project_id")
            )
        ]
        data["projects"].append(project)
        self._write(data)
        return project

    def get_project(self, tenant_id: str, project_id: str) -> dict[str, Any] | None:
        for project in self._read().get("projects", []):
            if project.get("tenant_id") == tenant_id and project.get("project_id") == project_id:
                return project
        return None

    def upsert_job(self, job: dict[str, Any]) -> dict[str, Any]:
        data = self._read()
        data["jobs"] = [
            item
            for item in data.get("jobs", [])
            if not (item.get("tenant_id") == job.get("tenant_id") and item.get("job_id") == job.get("job_id"))
        ]
        data["jobs"].append(job)
        self._write(data)
        return job

    def get_job(self, tenant_id: str, job_id: str) -> dict[str, Any] | None:
        for job in self._read().get("jobs", []):
            if job.get("tenant_id") == tenant_id and job.get("job_id") == job_id:
                return job
        return None

    def append_audit(self, event: dict[str, Any]) -> dict[str, Any]:
        data = self._read()
        data.setdefault("audit", []).append(event)
        self._write(data)
        return event

    def list_audit(self, tenant_id: str) -> list[dict[str, Any]]:
        return [event for event in self._read().get("audit", []) if event.get("tenant_id") == tenant_id]

    def append_artifact(self, artifact: dict[str, Any]) -> dict[str, Any]:
        data = self._read()
        data.setdefault("artifacts", []).append(artifact)
        self._write(data)
        return artifact


def storage_backend() -> JsonStorageBackend:
    # DATABASE_URL is reserved for the Postgres backend. JSON remains the safe fallback
    # for local tests and single-node deployments.
    return JsonStorageBackend()
