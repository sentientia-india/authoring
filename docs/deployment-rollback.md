# Immutable deployment and rollback

Each deployment is extracted into `DEPLOY_PATH/releases/<git-sha>`. The release directory is never modified after extraction except for its private runtime `.env` and secret files.

The deployment workflow:

1. uploads a SHA-addressed archive;
2. creates a new release directory without deleting the current installation;
3. builds candidate images once and tags them with the immutable Git SHA;
4. applies forward-compatible migrations;
5. starts the candidate and runs application, editor, and smoke health checks;
6. atomically updates `DEPLOY_PATH/current` only after every check passes;
7. records the release, deployment time, and previous release in `deployment.json`.

If any build, migration, startup, health, or smoke command fails, the error trap restarts the previous SHA-tagged images without rebuilding them. The `current` symlink remains unchanged.

Database migrations must be expand/contract and forward compatible with the previous application release. A destructive schema contraction is a later release after all running and rollback-eligible versions no longer depend on the removed shape.

Manual rollback:

```bash
cd "$(dirname "$(readlink -f "$DEPLOY_PATH/current")")/<previous-git-sha>"
export COMPOSE_PROJECT_NAME=samrat-course-mcp
export RELEASE_ID="$(basename "$PWD")"
docker compose up -d course-mcp scorm-editor
python -m course_mcp_server.healthcheck
ln -sfn "$PWD" "$DEPLOY_PATH/current"
```

Never delete a release until it is outside the rollback window and its database compatibility window has ended.
