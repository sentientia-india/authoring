from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row


def database_url() -> str | None:
    value = os.getenv("DATABASE_URL", "").strip()
    return value or None


@contextmanager
def connection() -> Iterator[Connection]:
    url = database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    with psycopg.connect(url, row_factory=dict_row) as active:
        yield active


def ensure_tenant(active: Connection, tenant_id: str) -> None:
    active.execute(
        """
        INSERT INTO tenants (tenant_id, name)
        VALUES (%s, %s)
        ON CONFLICT (tenant_id) DO NOTHING
        """,
        (tenant_id, tenant_id),
    )
