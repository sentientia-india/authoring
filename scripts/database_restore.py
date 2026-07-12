from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from database_backup import sha256


def restore_backup(
    *, database_url: str, backup: Path, manifest: Path, pg_restore_bin: str = "pg_restore"
) -> dict:
    evidence = json.loads(manifest.read_text(encoding="utf-8"))
    if evidence.get("file") != backup.name or evidence.get("sha256") != sha256(backup):
        raise ValueError("Backup integrity verification failed")
    subprocess.run(
        [
            pg_restore_bin,
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            "--dbname",
            database_url,
            str(backup),
        ],
        check=True,
        capture_output=True,
    )
    return {"restored": True, "file": backup.name, "sha256": evidence["sha256"]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify and restore a PostgreSQL backup.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--pg-restore-bin", default=os.getenv("PG_RESTORE_BIN", "pg_restore"))
    args = parser.parse_args()
    if not args.database_url:
        parser.error("DATABASE_URL or --database-url is required")
    print(
        json.dumps(
            restore_backup(
                database_url=args.database_url,
                backup=args.backup,
                manifest=args.manifest,
                pg_restore_bin=args.pg_restore_bin,
            )
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
