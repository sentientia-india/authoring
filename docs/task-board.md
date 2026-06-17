# Task Board

This is the project-level source of truth for work status. Update it whenever work is assigned, started, blocked, integrated, or completed.

## Status Key

- `Ready`: clear enough for a contributor to start.
- `In Progress`: someone is actively coding it.
- `Review`: code exists and needs review/integration.
- `Blocked`: cannot move without a decision or dependency.
- `Done`: integrated, tested, and documented.

## Active Work

| ID | Status | Owner | Task | Files | Acceptance |
|---|---|---|---|---|---|
| T-001 | Ready | Unassigned | Add structured response schemas for all MVP tools. | `src/course_mcp_server/schemas.py`, `tests/` | Pydantic response models exist and tests validate successful tool output shape. |
| T-002 | Ready | Unassigned | Replace placeholder course generation with a private generation service interface. | `src/course_mcp_server/course_generator.py`, `src/course_mcp_server/schemas.py`, `tests/` | Generators return validated structured data and never expose prompts/provider internals. |
| T-003 | Ready | Unassigned | Build real SCORM package output with zip creation and path safety. | `src/course_mcp_server/exporters/scorm.py`, `tests/` | Creates a package under configured output dir, rejects unsafe slugs/paths, includes manifest and HTML pages. |
| T-004 | Ready | Unassigned | Add minimal internal job store and status tracking. | `src/course_mcp_server/`, `tests/` | Known job IDs return scoped status; unrelated or unknown IDs reveal nothing. |
| T-005 | Ready | Unassigned | Add source text normalization and instructional-design checks. | `src/course_mcp_server/course_generator.py`, `src/course_mcp_server/schemas.py`, `tests/` | Source text is treated as untrusted content and outputs include objective/module validation notes. |
| T-006 | Ready | Unassigned | Harden docs and CI commands around reference repos. | `README.md`, `pyproject.toml`, `.gitignore`, `docs/` | Normal lint/test commands ignore local reference repos and contributor docs explain why. |

## Backlog

| ID | Status | Task | Notes |
|---|---|---|---|
| B-001 | Ready | H5P packaging research spike | Use `scorm-h5p-wrapper` as reference; do not expose arbitrary file tools. |
| B-002 | Ready | LiaScript export research spike | Determine whether a safe internal export adapter is worth adding after SCORM MVP. |
| B-003 | Ready | LMS adapter planning | Future only; publishing requires human approval and must not be in MVP tool surface. |
| B-004 | Ready | Human approval workflow | Needed before any publish/deploy/upload tools are considered. |

## Integration Queue

No external code is currently waiting for integration.

