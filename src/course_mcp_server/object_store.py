from __future__ import annotations

import hashlib
import os
import re
import shutil
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

    def delete_prefix(self, prefix: str) -> int:
        relative = PurePosixPath(prefix)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ObjectStoreError("Unsafe object prefix")
        target = (self.root / Path(*relative.parts)).resolve()
        if self.root == target or self.root not in target.parents:
            raise ObjectStoreError("Object prefix escapes storage root")
        if not target.exists():
            return 0
        count = sum(path.is_file() for path in target.rglob("*"))
        shutil.rmtree(target)
        return count

    def access(self, key: str) -> dict[str, str]:
        relative = PurePosixPath(key)
        if relative.is_absolute() or ".." in relative.parts:
            raise ObjectStoreError("Unsafe object key")
        target = (self.root / Path(*relative.parts)).resolve()
        if self.root not in target.parents or not target.is_file():
            raise ObjectStoreError("Object not found")
        return {"backend": "local", "path": str(target)}


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

    def delete_prefix(self, prefix: str) -> int:
        deleted = 0
        continuation = None
        while True:
            arguments = {"Bucket": self.bucket, "Prefix": prefix}
            if continuation:
                arguments["ContinuationToken"] = continuation
            page = self.client.list_objects_v2(**arguments)
            objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if objects:
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": objects, "Quiet": True})
                deleted += len(objects)
            if not page.get("IsTruncated"):
                return deleted
            continuation = page.get("NextContinuationToken")

    def access(self, key: str) -> dict[str, str]:
        url = self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=300,
        )
        return {"backend": "s3", "url": url}


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
