from __future__ import annotations

"""Per-customer licensing, tiers, and export metering.

The MCP server is the monetized gate: course creation requires a valid license
key. The admin bootstrap token (`MCP_API_TOKEN`) keeps working for the operator
and for legacy single-tenant deployments; customer keys are issued with
`scripts/issue_license.py` and stored hashed in the license store.

If the license store has no entries, enforcement is transparent: the bootstrap
token behaves exactly as before (unlimited), so existing deployments and tests
do not break until the operator provisions licenses.
"""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .security import SecurityError, read_secret

TIER_EXPORT_QUOTAS: dict[str, int | None] = {
    "free": 2,
    "pro": 50,
    "white_label": None,  # unlimited
    "admin": None,
}


@dataclass(frozen=True)
class License:
    tenant: str
    tier: str
    monthly_export_quota: int | None
    key_hash: str | None = None

    @property
    def white_label(self) -> bool:
        return self.tier in {"white_label", "admin"}


def _store_path() -> Path:
    return Path(os.getenv("LICENSE_STORE_PATH", "/app/output/licenses.json"))


def _load_store() -> dict:
    path = _store_path()
    if not path.exists():
        return {"licenses": [], "usage": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"licenses": [], "usage": {}}
    data.setdefault("licenses", [])
    data.setdefault("usage", {})
    return data


def _save_store(store: dict) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2), encoding="utf-8")


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def resolve_license(token: str | None) -> License:
    """Resolve a token to a License. Bootstrap token -> admin; else look up hashed key."""
    bootstrap = read_secret("MCP_API_TOKEN")
    if token and bootstrap and token == bootstrap:
        return License(tenant="admin", tier="admin", monthly_export_quota=None)
    if not token:
        raise SecurityError("Missing license key")
    store = _load_store()
    token_hash = hash_key(token)
    for entry in store["licenses"]:
        if entry.get("key_hash") != token_hash:
            continue
        if entry.get("disabled"):
            raise SecurityError("License is disabled")
        expires = entry.get("expires")
        if expires:
            try:
                if datetime.fromisoformat(expires).replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                    raise SecurityError("License has expired")
            except ValueError:
                pass
        tier = entry.get("tier", "free")
        quota = entry.get("monthly_export_quota", TIER_EXPORT_QUOTAS.get(tier, 2))
        return License(
            tenant=entry.get("tenant", "unknown"),
            tier=tier,
            monthly_export_quota=quota,
            key_hash=token_hash,
        )
    raise SecurityError("Invalid license key")


def _month_key() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


def exports_this_month(tenant: str) -> int:
    store = _load_store()
    return int(store["usage"].get(tenant, {}).get(_month_key(), 0))


def check_export_quota(license_: License) -> dict:
    used = exports_this_month(license_.tenant)
    quota = license_.monthly_export_quota
    allowed = quota is None or used < quota
    return {"allowed": allowed, "used": used, "quota": quota, "tier": license_.tier}


def record_export(license_: License) -> None:
    store = _load_store()
    tenant_usage = store["usage"].setdefault(license_.tenant, {})
    tenant_usage[_month_key()] = int(tenant_usage.get(_month_key(), 0)) + 1
    _save_store(store)


def issue_license(
    key: str,
    *,
    tenant: str,
    tier: str = "pro",
    monthly_export_quota: int | None = None,
    expires: str | None = None,
) -> dict:
    if tier not in TIER_EXPORT_QUOTAS or tier == "admin":
        raise ValueError(f"Unknown tier: {tier}")
    store = _load_store()
    entry = {
        "key_hash": hash_key(key),
        "tenant": tenant,
        "tier": tier,
        "monthly_export_quota": (
            monthly_export_quota if monthly_export_quota is not None else TIER_EXPORT_QUOTAS[tier]
        ),
        "expires": expires,
        "disabled": False,
    }
    store["licenses"] = [item for item in store["licenses"] if item.get("tenant") != tenant] + [entry]
    _save_store(store)
    return entry


__all__ = [
    "License",
    "TIER_EXPORT_QUOTAS",
    "resolve_license",
    "check_export_quota",
    "record_export",
    "exports_this_month",
    "issue_license",
    "hash_key",
]
