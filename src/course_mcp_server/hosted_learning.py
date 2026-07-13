"""Hosted learner delivery primitives kept outside the MCP tool registry."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZipFile

from .database import database_url
from .hosted_repository import (
    append_event as append_hosted_event,
    capture_lead as capture_hosted_lead,
    create_grant,
    create_release,
    dashboard as hosted_dashboard,
    grant_entitlement,
    has_entitlement,
    resolve_grant,
)
from .object_store import store_path


class HostedLearningError(RuntimeError):
    pass


def _root() -> Path:
    return Path(os.getenv("HOSTED_COURSE_ROOT", "course_mcp_output/hosted")).resolve()


def _store_path() -> Path:
    return _root() / "hosted.json"


def _load() -> dict[str, Any]:
    if not _store_path().exists():
        return {"shares": {}, "events": [], "entitlements": {}, "leads": []}
    return json.loads(_store_path().read_text(encoding="utf-8"))


def _save(data: dict[str, Any]) -> None:
    _root().mkdir(parents=True, exist_ok=True)
    _store_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def create_share(
    package_path: Path | str,
    *,
    tenant: str,
    course_id: str,
    paid: bool = False,
    access_mode: str | None = None,
) -> dict:
    package = Path(package_path).resolve()
    if not package.is_file() or package.suffix.lower() != ".zip":
        raise HostedLearningError("A valid SCORM ZIP is required")
    package_digest = hashlib.sha256(package.read_bytes()).hexdigest()
    release_id = f"release_{package_digest[:24]}"
    mode = access_mode or ("paid" if paid else "unlisted")
    allowed_modes = {"public", "unlisted", "email_verified", "invite_only", "tenant_only", "paid"}
    if mode not in allowed_modes:
        raise HostedLearningError("Unsupported share mode")
    token = secrets.token_urlsafe(24)
    target = _root() / ("releases" if database_url() else "shares") / (release_id if database_url() else token)
    target.mkdir(parents=True, exist_ok=True)
    with ZipFile(package) as archive:
        for info in archive.infolist():
            member = PurePosixPath(info.filename.replace("\\", "/"))
            if member.is_absolute() or ".." in member.parts:
                raise HostedLearningError("Unsafe package member")
            if info.is_dir():
                continue
            destination = (target / Path(*member.parts)).resolve()
            if target not in destination.parents:
                raise HostedLearningError("Package member escapes share directory")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(info))
    if not (target / "index.html").is_file():
        raise HostedLearningError("Package has no index.html launch file")
    if database_url():
        stored = store_path(
            package,
            tenant_id=tenant,
            kind="releases",
            object_id=release_id,
            filename=package.name,
        )
        release = create_release(
            tenant_id=tenant,
            course_id=course_id,
            release_id=release_id,
            object_key=stored["object_key"],
            package_sha256=stored["sha256"],
        )
        grant = create_grant(
            tenant_id=tenant,
            release_id=release["release_id"],
            token=token,
            mode=mode,
        )
        return {
            "share_token": token,
            "release_id": release["release_id"],
            "grant_id": grant["grant_id"],
            "launch_path": f"/learn/{token}/index.html",
            "paid": mode == "paid",
            "access_mode": mode,
        }
    data = _load()
    data["shares"][token] = {
        "tenant": tenant,
        "course_id": course_id,
        "paid": mode == "paid",
        "access_mode": mode,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _save(data)
    return {
        "share_token": token,
        "launch_path": f"/learn/{token}/index.html",
        "paid": mode == "paid",
        "access_mode": mode,
    }


def resolve_share_file(token: str, relative_path: str, access_token: str | None = None) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,80}", token):
        raise HostedLearningError("Invalid share token")
    if database_url():
        grant = resolve_grant(token)
        if not grant:
            raise HostedLearningError("Share not found")
        required_sources = {
            "paid": {"purchase"},
            "email_verified": {"email_verified"},
            "invite_only": {"invitation"},
            "tenant_only": {"tenant_membership"},
        }.get(grant["mode"])
        if required_sources and not has_entitlement(
            tenant_id=grant["tenant_id"],
            release_id=grant["release_id"],
            access_token=access_token,
            required_sources=required_sources,
        ):
            raise HostedLearningError("Access entitlement required")
        relative = PurePosixPath((relative_path or "index.html").replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts:
            raise HostedLearningError("Invalid share path")
        root = (_root() / "releases" / grant["release_id"]).resolve()
        target = (root / Path(*relative.parts)).resolve()
        if root != target and root not in target.parents:
            raise HostedLearningError("Share path escapes package")
        if not target.is_file():
            raise HostedLearningError("Share asset not found")
        return target
    data = _load()
    share = data["shares"].get(token)
    if not share:
        raise HostedLearningError("Share not found")
    required_source = {
        "paid": "purchase",
        "email_verified": "email_verified",
        "invite_only": "invitation",
        "tenant_only": "tenant_membership",
    }.get(share.get("access_mode"))
    if required_source:
        entitlement = data["entitlements"].get(hashlib.sha256((access_token or "").encode()).hexdigest())
        if (
            not entitlement
            or entitlement.get("share_token") != token
            or entitlement.get("source") != required_source
        ):
            raise HostedLearningError("Access entitlement required")
    relative = PurePosixPath((relative_path or "index.html").replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts:
        raise HostedLearningError("Invalid share path")
    root = (_root() / "shares" / token).resolve()
    target = (root / Path(*relative.parts)).resolve()
    if root != target and root not in target.parents:
        raise HostedLearningError("Share path escapes package")
    if not target.is_file():
        raise HostedLearningError("Share asset not found")
    return target


def record_learner_event(token: str, event: dict[str, Any]) -> dict:
    if database_url():
        grant = resolve_grant(token)
        if not grant:
            raise HostedLearningError("Share not found")
        allowed = {"completion", "score", "attempt", "interaction"}
        event_type = str(event.get("type") or "")
        if event_type not in allowed:
            raise HostedLearningError("Unsupported analytics event")
        score = max(0, min(100, int(event.get("score", 0)))) if event_type == "score" else None
        learner_hash = hashlib.sha256(str(event.get("learner_id", "anonymous")).encode()).hexdigest()
        row = append_hosted_event(
            tenant_id=grant["tenant_id"],
            release_id=grant["release_id"],
            event_type=event_type,
            learner_hash=learner_hash,
            payload={
                "score": score,
                "idempotency_key": event.get("idempotency_key"),
                "interaction": event.get("interaction") if event_type == "interaction" else None,
            },
        )
        return {
            "share_token": token,
            "type": event_type,
            "score": score,
            "learner_hash": learner_hash,
            "timestamp": row["occurred_at"].isoformat(),
        }
    data = _load()
    if token not in data["shares"]:
        raise HostedLearningError("Share not found")
    allowed = {"completion", "score", "attempt", "interaction"}
    event_type = str(event.get("type") or "")
    if event_type not in allowed:
        raise HostedLearningError("Unsupported analytics event")
    clean = {
        "share_token": token,
        "type": event_type,
        "score": max(0, min(100, int(event.get("score", 0)))) if event_type == "score" else None,
        "learner_hash": hashlib.sha256(str(event.get("learner_id", "anonymous")).encode()).hexdigest(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    data["events"].append(clean)
    _save(data)
    return clean


def course_dashboard(token: str) -> dict[str, Any]:
    if database_url():
        grant = resolve_grant(token)
        if not grant:
            raise HostedLearningError("Share not found")
        return hosted_dashboard(tenant_id=grant["tenant_id"], release_id=grant["release_id"])
    events = [event for event in _load()["events"] if event["share_token"] == token]
    learners = {event["learner_hash"] for event in events}
    scores = [event["score"] for event in events if event["type"] == "score"]
    return {
        "learners": len(learners),
        "completions": sum(event["type"] == "completion" for event in events),
        "attempts": sum(event["type"] == "attempt" for event in events),
        "average_score": round(sum(scores) / len(scores), 2) if scores else None,
    }


def grade_open_answer(answer: str, rubric_terms: list[str]) -> dict[str, Any]:
    normalized = set(re.findall(r"[a-z0-9]+", answer.lower()))
    matched = [term for term in rubric_terms if set(re.findall(r"[a-z0-9]+", term.lower())) <= normalized]
    score = round(100 * len(matched) / max(1, len(rubric_terms)))
    return {"score": score, "matched_criteria": matched, "needs_human_review": score < 100}


def tutor_reply(question: str, course_context: str, api_key: str, model: str) -> str:
    """Call an OpenAI-compatible provider with a learner-supplied key; never persist the key."""
    if not api_key or len(api_key) < 12:
        raise HostedLearningError("A valid BYO provider key is required")
    base_url = os.getenv("TUTOR_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    if not base_url.startswith("https://"):
        raise HostedLearningError("Tutor provider must use HTTPS")
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "Answer only from the supplied course context. Say when the answer is not present.",
                },
                {"role": "user", "content": f"COURSE CONTEXT:\n{course_context[:12000]}\n\nQUESTION:\n{question[:1000]}"},
            ],
        }
    ).encode()
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310 - HTTPS enforced
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise HostedLearningError("Tutor provider request failed") from exc
    try:
        return str(payload["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise HostedLearningError("Tutor provider returned an invalid response") from exc


def grant_share_access(
    share_token: str, subject: str, source: str, *, expected_tenant_id: str | None = None
) -> dict[str, str]:
    subject = subject.strip().lower()
    if len(subject) < 3 or len(subject) > 320:
        raise HostedLearningError("A valid entitlement subject is required")
    mode_sources = {
        "paid": "purchase",
        "email_verified": "email_verified",
        "invite_only": "invitation",
        "tenant_only": "tenant_membership",
    }
    if database_url():
        grant = resolve_grant(share_token)
        if not grant:
            raise HostedLearningError("Share not found")
        if expected_tenant_id and grant["tenant_id"] != expected_tenant_id:
            raise HostedLearningError("Share not found")
        if mode_sources.get(grant["mode"]) != source:
            raise HostedLearningError("Entitlement source does not match share mode")
        access_token = secrets.token_urlsafe(32)
        grant_entitlement(
            tenant_id=grant["tenant_id"],
            release_id=grant["release_id"],
            purchaser=subject,
            access_token=access_token,
            source=source,
        )
        return {"access_token": access_token, "share_token": share_token}
    data = _load()
    share = data["shares"].get(share_token)
    if not share or (expected_tenant_id and share["tenant"] != expected_tenant_id):
        raise HostedLearningError("Share not found")
    if mode_sources.get(share.get("access_mode")) != source:
        raise HostedLearningError("Entitlement source does not match share mode")
    access_token = secrets.token_urlsafe(32)
    data["entitlements"][hashlib.sha256(access_token.encode()).hexdigest()] = {
        "share_token": share_token,
        "subject_hash": hashlib.sha256(subject.lower().encode()).hexdigest(),
        "source": source,
    }
    _save(data)
    return {"access_token": access_token, "share_token": share_token}


def grant_paid_access(share_token: str, purchaser: str) -> dict[str, str]:
    return grant_share_access(share_token, purchaser, "purchase")


def capture_lead(share_token: str, email: str) -> dict[str, Any]:
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HostedLearningError("Invalid email")
    if database_url():
        grant = resolve_grant(share_token)
        if not grant:
            raise HostedLearningError("Share not found")
        return capture_hosted_lead(
            tenant_id=grant["tenant_id"], release_id=grant["release_id"], email=email
        )
    data = _load()
    if share_token not in data["shares"]:
        raise HostedLearningError("Share not found")
    row = {
        "share_token": share_token,
        "email_hash": hashlib.sha256(email.lower().encode()).hexdigest(),
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    data["leads"].append(row)
    _save(data)
    return row
