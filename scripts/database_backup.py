from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_backup(*, database_url: str, output_dir: Path, pg_dump_bin: str = "pg_dump") -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = output_dir / f"course-mcp-{timestamp}.dump"
    subprocess.run(
        [pg_dump_bin, "--format=custom", "--no-owner", "--no-privileges", "--file", str(backup), database_url],
        check=True,
        capture_output=True,
    )
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "format": "postgres-custom",
        "file": backup.name,
        "sha256": sha256(backup),
        "size_bytes": backup.stat().st_size,
    }
    manifest_path = backup.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {**manifest, "backup_path": str(backup), "manifest_path": str(manifest_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an integrity-manifested PostgreSQL backup.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--pg-dump-bin", default=os.getenv("PG_DUMP_BIN", "pg_dump"))
    args = parser.parse_args()
    if not args.database_url:
        parser.error("DATABASE_URL or --database-url is required")
    result = create_backup(
        database_url=args.database_url, output_dir=args.output_dir, pg_dump_bin=args.pg_dump_bin
    )
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
