# Release, compatibility, and migration policy

The public tool contract is versioned with the product. Stable tools remain
backward compatible for at least two minor releases and 90 days, whichever is
longer. New optional request fields and response fields may be added in a minor
release. Removing or renaming a tool/field, changing its meaning, or tightening
a previously valid schema requires a major release.

Deprecations are announced in the changelog with the replacement, first
deprecated version, earliest removal version/date, and a tested migration
example. Security fixes may shorten the window only when preserving the old
behavior would expose customers; the advisory must explain the exception.

Database migrations use expand/migrate/contract:

1. expand with nullable/additive structures compatible with the current and
   previous application release;
2. deploy code that reads both shapes and writes the new shape;
3. backfill with a bounded, resumable operation and verify counts/digests;
4. switch reads only after evidence is clean;
5. contract in a later release after the rollback window expires.

Every release must pass lint, tests, dependency/security scans, migration
application, clean backup restore, Docker build, Moodle conformance, deployment
smoke, and capacity gates. The deployed Git SHA, timestamp, and prior release
are recorded on the server. MCP registry publication uses `server.json`; replace
the placeholder domain and publish only after the public TLS endpoint and an
external clean-machine installation have passed.
