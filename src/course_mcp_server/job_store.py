from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _store_path() -> Path:
    default_dir = Path(os.getenv("OUTPUT_DIR", "course_mcp_output"))
    return Path(os.getenv("JOB_STORE_PATH", str(default_dir / "jobs.json"))).resolve()


def reset_job_store() -> None:
    path = _store_path()
    if path.exists():
        path.unlink()


def _read_jobs() -> list[dict[str, Any]]:
    path = _store_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [job for job in data if isinstance(job, dict)]


def _write_jobs(jobs: list[dict[str, Any]]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jobs, indent=2, sort_keys=True), encoding="utf-8")


def record_job(
    *,
    job_id: str,
    tenant_id: str,
    user_id: str,
    tool_name: str,
    status: str,
    message: str,
) -> dict[str, Any]:
    jobs = [job for job in _read_jobs() if job.get("job_id") != job_id]
    job = {
        "job_id": job_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "tool_name": tool_name,
        "status": status,
        "message": message,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    jobs.append(job)
    _write_jobs(jobs)
    return job


def get_job_status(*, job_id: str, tenant_id: str) -> dict[str, Any]:
    for job in _read_jobs():
        if job.get("job_id") == job_id and job.get("tenant_id") == tenant_id:
            return {
                "job_id": job_id,
                "status": job.get("status", "not_found"),
                "tool_name": job.get("tool_name"),
                "message": job.get("message", ""),
            }
    return {"job_id": job_id, "status": "not_found", "tool_name": None, "message": "Job not found."}
