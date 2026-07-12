# Backup and restore runbook

## Objectives

- Recovery point objective: 15 minutes or less.
- Recovery time objective: 60 minutes or less.
- Backups are encrypted by the storage provider, access-controlled, integrity-manifested, and copied outside the application host.

## Create a backup

```bash
python scripts/database_backup.py --output-dir /secure/backups/course-mcp
```

Upload both the `.dump` and `.manifest.json` files to the protected backup bucket. Never store database URLs or credentials in either file.

## Restore drill

Restore into a clean, isolated database first:

```bash
python scripts/database_restore.py \
  --database-url "$RESTORE_DATABASE_URL" \
  --backup /secure/backups/course-mcp/course-mcp-TIMESTAMP.dump \
  --manifest /secure/backups/course-mcp/course-mcp-TIMESTAMP.manifest.json
```

The restore command refuses a backup whose filename or SHA-256 digest does not match the manifest.

After restoration:

1. run all migrations to prove forward compatibility;
2. compare tenant, project, release, enrollment, event, subscription, entitlement, and audit counts;
3. validate object-store references and sample SHA-256 digests;
4. run health and smoke checks against the isolated database;
5. record start time, finish time, achieved RPO/RTO, backup digest, discrepancies, and operator;
6. destroy the isolated restore credentials and environment after evidence is retained.

Production restoration requires incident authorization and a recorded rollback point. Never restore unverified bytes directly over production.
