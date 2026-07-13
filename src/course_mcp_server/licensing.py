"""Per-customer licensing, tiers, and export metering.

The MCP server is the monetized gate: course creation requires a valid license
key. The admin bootstrap token (`MCP_API_TOKEN`) keeps working for the operator
and for legacy single-tenant deployments; customer keys are issued with
`scripts/issue_license.py` and stored hashed in the license store.

If the license store has no entries, enforcement is transparent: the bootstrap
token behaves exactly as before (unlimited), so existing deployments and tests
do not break until the operator provisions licenses.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .database import connection, database_url, ensure_tenant
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
    token_hash = hash_key(token)
    if database_url():
        with connection() as active:
            row = active.execute(
                """
                SELECT tenant_id, tier, monthly_export_quota, key_hash, expires_at, disabled_at
                FROM product_licenses WHERE key_hash = %s
                """,
                (token_hash,),
            ).fetchone()
        if not row or row["disabled_at"]:
            raise SecurityError("Invalid or disabled license key")
        if row["expires_at"] and row["expires_at"] < datetime.now(timezone.utc):
            raise SecurityError("License has expired")
        return License(
            tenant=row["tenant_id"],
            tier=row["tier"],
            monthly_export_quota=row["monthly_export_quota"],
            key_hash=row["key_hash"],
        )
    store = _load_store()
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
    if database_url():
        with connection() as active:
            row = active.execute(
                """
                SELECT COALESCE(sum(quantity), 0) AS exports
                FROM usage_entries
                WHERE tenant_id = %s AND dimension = 'export'
                  AND occurred_at >= date_trunc('month', now())
                  AND occurred_at < date_trunc('month', now()) + interval '1 month'
                """,
                (tenant,),
            ).fetchone()
        return int(row["exports"])
    store = _load_store()
    return int(store["usage"].get(tenant, {}).get(_month_key(), 0))


def check_export_quota(license_: License) -> dict:
    used = exports_this_month(license_.tenant)
    quota = license_.monthly_export_quota
    allowed = quota is None or used < quota
    return {"allowed": allowed, "used": used, "quota": quota, "tier": license_.tier}


def usage_export() -> list[dict]:
    if database_url():
        with connection() as active:
            rows = active.execute(
                """
                SELECT tenant_id AS tenant, to_char(date_trunc('month', occurred_at), 'YYYY-MM') AS month,
                       sum(quantity)::integer AS exports
                FROM usage_entries WHERE dimension = 'export'
                GROUP BY tenant_id, date_trunc('month', occurred_at)
                ORDER BY tenant_id, date_trunc('month', occurred_at)
                """
            ).fetchall()
        return [dict(row) for row in rows]
    store = _load_store()
    rows: list[dict] = []
    for tenant, months in sorted(store["usage"].items()):
        for month, exports in sorted(months.items()):
            rows.append({"tenant": tenant, "month": month, "exports": int(exports)})
    return rows


def lifecycle_warning(license_: License) -> str | None:
    if not license_.key_hash:
        return None
    if database_url():
        with connection() as active:
            row = active.execute(
                "SELECT expires_at FROM product_licenses WHERE tenant_id = %s AND key_hash = %s",
                (license_.tenant, license_.key_hash),
            ).fetchone()
        expires = row["expires_at"] if row else None
        if not expires:
            return None
        days = (expires - datetime.now(timezone.utc)).days
        return f"License expires in {max(days, 0)} day(s). Renew to avoid interruption." if days <= 14 else None
    store = _load_store()
    entry = next((item for item in store["licenses"] if item.get("key_hash") == license_.key_hash), None)
    if not entry or not entry.get("expires"):
        return None
    try:
        expires = datetime.fromisoformat(entry["expires"]).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    days = (expires - datetime.now(timezone.utc)).days
    if days <= 14:
        return f"License expires in {max(days, 0)} day(s). Renew to avoid interruption."
    return None


def record_export(license_: License) -> None:
    if database_url():
        usage_id = f"usage_{uuid4().hex}"
        with connection() as active:
            row = active.execute(
                """
                SELECT monthly_export_quota FROM product_licenses
                WHERE tenant_id = %s FOR UPDATE
                """,
                (license_.tenant,),
            ).fetchone()
            if not row:
                raise SecurityError("License not found")
            used = active.execute(
                """
                SELECT COALESCE(sum(quantity), 0) AS exports FROM usage_entries
                WHERE tenant_id = %s AND dimension = 'export'
                  AND occurred_at >= date_trunc('month', now())
                  AND occurred_at < date_trunc('month', now()) + interval '1 month'
                """,
                (license_.tenant,),
            ).fetchone()["exports"]
            quota = row["monthly_export_quota"]
            if quota is not None and int(used) >= int(quota):
                raise SecurityError("Monthly export quota exceeded")
            active.execute(
                """
                INSERT INTO usage_entries
                    (tenant_id, usage_id, dimension, quantity, source_event_id, occurred_at)
                VALUES (%s, %s, 'export', 1, %s, now())
                """,
                (license_.tenant, usage_id, usage_id),
            )
        return
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
    if database_url():
        expires_at = None
        if expires:
            try:
                expires_at = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
            except ValueError as exc:
                raise ValueError("Invalid license expiry") from exc
        license_id = f"license_{uuid4().hex}"
        quota = monthly_export_quota if monthly_export_quota is not None else TIER_EXPORT_QUOTAS[tier]
        with connection() as active:
            ensure_tenant(active, tenant)
            row = active.execute(
                """
                INSERT INTO product_licenses
                    (tenant_id, license_id, key_hash, tier, monthly_export_quota, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id) DO UPDATE
                SET license_id = EXCLUDED.license_id, key_hash = EXCLUDED.key_hash,
                    tier = EXCLUDED.tier, monthly_export_quota = EXCLUDED.monthly_export_quota,
                    expires_at = EXCLUDED.expires_at, disabled_at = NULL, updated_at = now()
                RETURNING key_hash, tenant_id AS tenant, tier, monthly_export_quota, expires_at
                """,
                (tenant, license_id, hash_key(key), tier, quota, expires_at),
            ).fetchone()
        return dict(row)
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
    "usage_export",
    "lifecycle_warning",
]
