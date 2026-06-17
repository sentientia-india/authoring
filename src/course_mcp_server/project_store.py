from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _store_path() -> Path:
    default_dir = Path(os.getenv("OUTPUT_DIR", "course_mcp_output"))
    return Path(os.getenv("COURSE_PROJECT_STORE_PATH", str(default_dir / "projects.json"))).resolve()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_projects() -> list[dict[str, Any]]:
    path = _store_path()
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _write_projects(projects: list[dict[str, Any]]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(projects, indent=2, sort_keys=True), encoding="utf-8")


def stable_project_id(*, tenant_id: str, course_title: str, audience: str) -> str:
    raw = f"{tenant_id}:{course_title}:{audience}".encode("utf-8")
    return f"course_{hashlib.sha256(raw).hexdigest()[:12]}"


def create_project(
    *,
    tenant_id: str,
    user_id: str,
    course_title: str,
    audience: str,
    language: str,
    compliance_domain: str | None,
) -> dict[str, Any]:
    projects = _read_projects()
    project_id = stable_project_id(tenant_id=tenant_id, course_title=course_title, audience=audience)
    existing = next(
        (
            project
            for project in projects
            if project.get("tenant_id") == tenant_id and project.get("project_id") == project_id
        ),
        None,
    )
    if existing:
        return existing
    project = {
        "project_id": project_id,
        "tenant_id": tenant_id,
        "created_by": user_id,
        "course_title": course_title,
        "audience": audience,
        "language": language,
        "compliance_domain": compliance_domain,
        "status": "draft",
        "sources": [],
        "artifacts": [],
        "created_at": _now(),
        "updated_at": _now(),
    }
    projects.append(project)
    _write_projects(projects)
    return project


def get_project(*, tenant_id: str, project_id: str) -> dict[str, Any] | None:
    for project in _read_projects():
        if project.get("tenant_id") == tenant_id and project.get("project_id") == project_id:
            return project
    return None


def save_project(project: dict[str, Any]) -> dict[str, Any]:
    projects = _read_projects()
    project["updated_at"] = _now()
    updated = False
    for index, existing in enumerate(projects):
        if (
            existing.get("tenant_id") == project.get("tenant_id")
            and existing.get("project_id") == project.get("project_id")
        ):
            projects[index] = project
            updated = True
            break
    if not updated:
        projects.append(project)
    _write_projects(projects)
    return project


def add_artifact(project: dict[str, Any], artifact_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    artifact = {
        "artifact_id": f"{artifact_type}_{len(project.get('artifacts', [])) + 1}",
        "artifact_type": artifact_type,
        "payload": payload,
        "created_at": _now(),
    }
    project.setdefault("artifacts", []).append(artifact)
    if project.get("status") == "draft":
        project["status"] = "generated"
    save_project(project)
    return artifact


def latest_artifact(project: dict[str, Any], artifact_type: str) -> dict[str, Any] | None:
    for artifact in reversed(project.get("artifacts", [])):
        if artifact.get("artifact_type") == artifact_type:
            return artifact
    return None
