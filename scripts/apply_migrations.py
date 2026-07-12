from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"


def apply(database_url: str, migrations_dir: Path = MIGRATIONS) -> list[str]:
    applied: list[str] = []
    with psycopg.connect(database_url) as connection:
        for path in sorted(migrations_dir.glob("*.sql")):
            connection.execute(path.read_text(encoding="utf-8"))
            applied.append(path.stem)
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply Course MCP PostgreSQL migrations.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--migrations-dir", type=Path, default=MIGRATIONS)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("DATABASE_URL or --database-url is required")
    for version in apply(args.database_url, args.migrations_dir):
        print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
