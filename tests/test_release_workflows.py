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
        application_start = workflow.index("docker compose up -d course-mcp scorm-editor", migration)
        assert migration < application_start


def test_ci_runs_a_real_postgres_backup_restore_drill():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "Backup and restore drill" in workflow
    assert "pg_dump" in workflow and "pg_restore" in workflow
    assert "course_mcp_restore" in workflow
    assert "SOURCE_COUNT" in workflow and "RESTORE_COUNT" in workflow


def test_deployments_use_immutable_releases_and_rollback_without_in_place_deletion():
    for relative in (".github/workflows/ci.yml", ".github/workflows/deploy.yml"):
        workflow = (ROOT / relative).read_text(encoding="utf-8")
        assert 'RELEASE_PATH="$DEPLOY_PATH/releases/$RELEASE_ID"' in workflow
        assert 'ln -sfn "$RELEASE_PATH" "$DEPLOY_PATH/current"' in workflow
        assert "rollback()" in workflow and "trap rollback ERR" in workflow
        assert "deployment.json" in workflow
        assert 'find "$DEPLOY_PATH" -mindepth 1' not in workflow
        assert "RELEASE_ID='$RELEASE_ID' MCP_API_TOKEN_B64" in workflow
        assert 'test -n "$RELEASE_ID"' in workflow


def test_deployments_run_a_bounded_canary_load_gate_before_promotion():
    for relative in (".github/workflows/ci.yml", ".github/workflows/deploy.yml"):
        workflow = (ROOT / relative).read_text(encoding="utf-8")
        load_gate = workflow.index("/app/scripts/load_test.py")
        promotion = workflow.index('ln -sfn "$RELEASE_PATH" "$DEPLOY_PATH/current"')
        assert load_gate < promotion
        assert "--max-error-rate 0" in workflow
        assert "--max-p95 0.4" in workflow
