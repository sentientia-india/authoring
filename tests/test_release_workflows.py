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


def test_production_deploy_applies_migrations_before_application_start():
    for relative in (".github/workflows/ci.yml", ".github/workflows/deploy.yml"):
        workflow = (ROOT / relative).read_text(encoding="utf-8")
        migration = workflow.index("python /app/scripts/apply_migrations.py")
        application_start = workflow.index("docker compose up -d course-mcp scorm-editor")
        assert migration < application_start
