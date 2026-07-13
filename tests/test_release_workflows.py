from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dependency_audit_is_release_blocking():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    dependency_step = workflow.split("- name: Dependency audit", 1)[1].split("- name:", 1)[0]

    assert "pip-audit ." in dependency_step
    assert "|| true" not in dependency_step
    assert "continue-on-error" not in dependency_step


def test_moodle_conformance_environment_is_commit_pinned():
    workflow = (ROOT / ".github" / "workflows" / "moodle-conformance.yml").read_text(encoding="utf-8")

    assert "MOODLE_DOCKER_COMMIT: 81a20665c2d2322469dc491c1f972ebde90ec014" in workflow
    assert "MOODLE_COMMIT: da7446c6c7b786f7f7588537f1cd48b3709c5439" in workflow
    assert "workflow_dispatch" in workflow
    assert "workflow_call" in workflow


def test_production_deployments_require_moodle_conformance():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    manual = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    assert "uses: ./.github/workflows/moodle-conformance.yml" in ci
    assert "needs: [test, moodle-conformance]" in ci
    assert "uses: ./.github/workflows/moodle-conformance.yml" in manual
    assert "needs: moodle-conformance" in manual


def test_production_deploy_applies_migrations_before_application_start():
    for relative in (".github/workflows/ci.yml", ".github/workflows/deploy.yml"):
        workflow = (ROOT / relative).read_text(encoding="utf-8")
        migration = workflow.index("python /app/scripts/apply_migrations.py")
        application_start = workflow.index(
            "docker compose up -d course-mcp scorm-editor outbox-worker analytics-worker", migration
        )
        assert migration < application_start


def test_ci_runs_a_real_postgres_backup_restore_drill():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "Backup and restore drill" in workflow
    assert "pg_dump" in workflow and "pg_restore" in workflow
    assert "course_mcp_restore" in workflow
    assert "SOURCE_COUNT" in workflow and "RESTORE_COUNT" in workflow


def test_deployments_use_immutable_releases_and_rollback_without_in_place_deletion():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "samrat-course-mcp:${RELEASE_ID:-local}" in compose
    assert "samrat-scorm-editor:${RELEASE_ID:-local}" in compose
    for relative in (".github/workflows/ci.yml", ".github/workflows/deploy.yml"):
        workflow = (ROOT / relative).read_text(encoding="utf-8")
        assert 'RELEASE_PATH="$DEPLOY_PATH/releases/$RELEASE_ID"' in workflow
        assert 'ln -sfn "$RELEASE_PATH" "$DEPLOY_PATH/current"' in workflow
        assert "rollback()" in workflow and "trap rollback ERR" in workflow
        assert "deployment.json" in workflow
        assert 'find "$DEPLOY_PATH" -mindepth 1' not in workflow
        assert "RELEASE_ID='$RELEASE_ID' MCP_API_TOKEN_B64" in workflow
        assert 'test -n "$RELEASE_ID"' in workflow
        assert 'export RELEASE_ID="$(basename "$PREVIOUS")"' in workflow


def test_deployments_run_a_bounded_canary_load_gate_before_promotion():
    for relative in (".github/workflows/ci.yml", ".github/workflows/deploy.yml"):
        workflow = (ROOT / relative).read_text(encoding="utf-8")
        load_gate = workflow.index("/app/scripts/capacity_matrix.py")
        promotion = workflow.index('ln -sfn "$RELEASE_PATH" "$DEPLOY_PATH/current"')
        assert load_gate < promotion
        assert "--max-error-rate 0" in workflow
        assert "--max-p95 0.4" in workflow
    capacity_script = (ROOT / "scripts/capacity_matrix.py").read_text(encoding="utf-8")
    assert all(level in capacity_script for level in ('"1x"', '"3x"', '"10x"'))


def test_deployments_preserve_a_stable_pii_encryption_key_outside_releases():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "PII_ENCRYPTION_KEY_FILE: /run/secrets/pii_encryption_key" in compose
    for relative in (".github/workflows/ci.yml", ".github/workflows/deploy.yml"):
        workflow = (ROOT / relative).read_text(encoding="utf-8")
        assert '$DEPLOY_PATH/shared/secrets/pii_encryption_key.txt' in workflow
        assert "openssl rand -base64 32" in workflow
        assert "cp \"$DEPLOY_PATH/shared/secrets/pii_encryption_key.txt\"" in workflow
        assert "docker compose up -d course-mcp scorm-editor outbox-worker analytics-worker" in workflow


def test_custom_domain_tls_is_restricted_to_verified_database_records():
    caddy = (ROOT / "Caddyfile").read_text(encoding="utf-8")
    server = (ROOT / "src" / "course_mcp_server" / "server.py").read_text(encoding="utf-8")
    assert "on_demand_tls" in caddy
    assert "ask http://course-mcp:8777/internal/caddy/domain-allowed" in caddy
    assert "rewrite * /domain/{host}{uri}" in caddy
    assert '"/internal/caddy/domain-allowed"' in server
    assert '"/domain/{hostname}/{asset_path:path}"' in server
    assert '"/embed/{token}"' in server
