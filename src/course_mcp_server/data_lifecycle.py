from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from psycopg import sql
from psycopg.types.json import Jsonb

from .database import connection
from .object_store import object_store


TENANT_TABLES = (
    "projects",
    "jobs",
    "job_attempts",
    "artifacts",
    "outbox_dead_letters",
    "outbox_events",
    "audit_events",
    "hosted_releases",
    "custom_domains",
    "learning_collections",
    "learning_collection_items",
    "share_grants",
    "learner_identities",
    "enrollments",
    "learner_attempts",
    "learner_events",
    "hosted_entitlements",
    "captured_leads",
    "subscriptions",
    "product_licenses",
    "entitlements",
    "usage_entries",
    "email_deliveries",
    "scheduled_reports",
    "analytics_report_runs",
    "analytics_quality_checks",
    "analytics_ingestion_observations",
    "billing_events",
    "badge_definitions",
    "badge_awards",
    "learner_certificates",
)


DELETE_ORDER = (
    "analytics_ingestion_observations",
    "analytics_quality_checks",
    "analytics_report_runs",
    "scheduled_reports",
    "captured_leads",
    "email_deliveries",
    "learner_events",
    "learner_certificates",
    "badge_awards",
    "badge_definitions",
    "learner_attempts",
    "enrollments",
    "learner_identities",
    "hosted_entitlements",
    "learning_collection_items",
    "learning_collections",
    "custom_domains",
    "share_grants",
    "hosted_releases",
    "product_licenses",
    "outbox_dead_letters",
    "outbox_events",
    "job_attempts",
    "jobs",
    "artifacts",
    "projects",
)


def export_tenant(*, tenant_id: str) -> dict[str, Any]:
    exported: dict[str, Any] = {
        "tenant_id": tenant_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 1,
        "tables": {},
    }
    with connection() as active:
        tenant = active.execute(
            "SELECT tenant_id, name, status, created_at, updated_at, version FROM tenants WHERE tenant_id = %s",
            (tenant_id,),
        ).fetchone()
        if not tenant:
            raise LookupError("Tenant not found")
        exported["tenant"] = dict(tenant)
        for table in TENANT_TABLES:
            rows = active.execute(
                sql.SQL("SELECT * FROM {} WHERE tenant_id = %s").format(sql.Identifier(table)),
                (tenant_id,),
            ).fetchall()
            exported["tables"][table] = [dict(row) for row in rows]
    canonical = json.dumps(exported, sort_keys=True, default=str, separators=(",", ":")).encode()
    exported["sha256"] = hashlib.sha256(canonical).hexdigest()
    return exported


def delete_tenant_customer_data(
    *, tenant_id: str, requested_by: str, confirmation: str, export_sha256: str
) -> dict[str, Any]:
    if confirmation != tenant_id or not re.fullmatch(r"[0-9a-f]{64}", export_sha256):
        raise ValueError("Tenant deletion confirmation or export evidence is invalid")
    deleted: dict[str, int] = {}
    tenant_hash = hashlib.sha256(tenant_id.encode()).hexdigest()
    deletion_id = f"delete_{uuid4().hex}"
    with connection() as active:
        active.execute("SET LOCAL course_mcp.retention_operation = 'on'")
        for table in DELETE_ORDER:
            result = active.execute(
                sql.SQL("DELETE FROM {} WHERE tenant_id = %s").format(sql.Identifier(table)),
                (tenant_id,),
            )
            deleted[table] = result.rowcount
        active.execute(
            "UPDATE tenants SET name = %s, status = 'deleted', updated_at = now(), version = version + 1 WHERE tenant_id = %s",
            (f"deleted-{tenant_hash[:12]}", tenant_id),
        )
        active.execute(
            """
            INSERT INTO deletion_records
                (deletion_id, tenant_hash, requested_by, export_sha256, deleted_counts)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (deletion_id, tenant_hash, requested_by, export_sha256, Jsonb(deleted)),
        )
    object_count = object_store().delete_prefix(f"tenants/{tenant_id}")
    return {
        "deletion_id": deletion_id,
        "tenant_hash": tenant_hash,
        "deleted_counts": deleted,
        "deleted_objects": object_count,
        "retained": ["audit_events", "subscriptions", "entitlements", "usage_entries", "billing_events"],
    }
