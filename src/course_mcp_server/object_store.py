from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path, PurePosixPath
from typing import BinaryIO


class ObjectStoreError(RuntimeError):
    pass


def _safe_segment(value: str, label: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value or ""):
        raise ObjectStoreError(f"Invalid {label}")
    return value


def object_key(*, tenant_id: str, kind: str, object_id: str, filename: str) -> str:
    tenant = _safe_segment(tenant_id, "tenant_id")
    category = _safe_segment(kind, "object kind")
    identifier = _safe_segment(object_id, "object id")
    name = PurePosixPath(filename.replace("\\", "/"))
    if name.is_absolute() or ".." in name.parts or len(name.parts) != 1 or not name.name:
        raise ObjectStoreError("Invalid object filename")
    return f"tenants/{tenant}/{category}/{identifier}/{name.name}"


class LocalObjectStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()

    def put(self, key: str, source: BinaryIO) -> dict:
        relative = PurePosixPath(key)
        if relative.is_absolute() or ".." in relative.parts:
            raise ObjectStoreError("Unsafe object key")
        destination = (self.root / Path(*relative.parts)).resolve()
        if self.root != destination and self.root not in destination.parents:
            raise ObjectStoreError("Object key escapes storage root")
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with destination.open("wb") as target:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
                target.write(chunk)
        return {"object_key": key, "sha256": digest.hexdigest(), "size_bytes": size, "backend": "local"}


class S3ObjectStore:
    def __init__(self, *, bucket: str, endpoint_url: str | None = None) -> None:
        import boto3

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=os.getenv("OBJECT_STORE_ACCESS_KEY"),
            aws_secret_access_key=os.getenv("OBJECT_STORE_SECRET_KEY"),
            region_name=os.getenv("OBJECT_STORE_REGION", "us-east-1"),
        )

    def put(self, key: str, source: BinaryIO) -> dict:
        digest = hashlib.sha256()
        payload = source.read()
        digest.update(payload)
        self.client.put_object(Bucket=self.bucket, Key=key, Body=payload)
        return {
            "object_key": key,
            "sha256": digest.hexdigest(),
            "size_bytes": len(payload),
            "backend": "s3",
        }


def object_store():
    bucket = os.getenv("OBJECT_STORE_BUCKET", "").strip()
    if bucket:
        return S3ObjectStore(bucket=bucket, endpoint_url=os.getenv("OBJECT_STORE_ENDPOINT"))
    if os.getenv("ENVIRONMENT", "development").lower() == "production":
        raise ObjectStoreError("OBJECT_STORE_BUCKET is required in production")
    root = os.getenv("OBJECT_STORE_LOCAL_ROOT", "course_mcp_output/objects")
    return LocalObjectStore(root)


def store_path(
    path: Path | str,
    *,
    tenant_id: str,
    kind: str,
    object_id: str,
    filename: str | None = None,
) -> dict:
    source_path = Path(path)
    key = object_key(
        tenant_id=tenant_id,
        kind=kind,
        object_id=object_id,
        filename=filename or source_path.name,
    )
    with source_path.open("rb") as source:
        return object_store().put(key, source)
