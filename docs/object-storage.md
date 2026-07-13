# Production object storage

Production requires `OBJECT_STORE_BUCKET`; startup paths fail closed instead of silently storing durable binaries on the application filesystem. `OBJECT_STORE_ENDPOINT` can target an S3-compatible service, with region and credentials supplied through the documented environment variables.

Objects use tenant-prefixed keys and content-addressed identifiers:

```text
tenants/{tenant_id}/sources/source_{sha256-prefix}/{filename}
tenants/{tenant_id}/media/media_{sha256-prefix}/{filename}
tenants/{tenant_id}/exports/export_{sha256-prefix}/{filename}
tenants/{tenant_id}/releases/release_{sha256-prefix}/{filename}
```

This covers raw source uploads, authoring media, SCORM/H5P/interactive-video packages, and immutable hosted-release ZIPs. PostgreSQL stores the corresponding project, artifact, release, digest, and object-key metadata. Re-uploading identical bytes is idempotent; changed bytes create a different content-addressed object.

Tenant deletion removes the complete `tenants/{tenant_id}` prefix after the verified tenant export and relational deletion workflow. Object keys reject traversal, absolute paths, nested filenames, and unsafe identifiers.

Verification:

```powershell
python -m pytest tests/test_object_store.py tests/test_course_workflow_tools.py tests/test_postgres_hosted_repository.py -q
```
