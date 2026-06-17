# Project Rotation System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable project rotation and contributor handoff system for Samrat Course MCP.

**Architecture:** The system is documentation-first and lives under `docs/`, with the README acting as the front door. The task board tracks active work, the worklog records state changes, and the rotation checklist is the trigger document for future Codex/project handoffs.

**Tech Stack:** Markdown docs, Python test/lint commands, existing MCP security architecture.

---

### Task 1: Rotation Docs

**Files:**
- Create: `docs/project-rotation.md`
- Create: `docs/contributor-onboarding.md`
- Create: `docs/task-board.md`
- Create: `docs/worklog.md`
- Create: `docs/reference-repos.md`

- [x] **Step 1: Add the rotation checklist**

Create `docs/project-rotation.md` with the trigger phrases, required first-pass reads, baseline commands, security gate, handoff flow, reference repo rule, and done definition.

- [x] **Step 2: Add contributor onboarding**

Create `docs/contributor-onboarding.md` with read order, baseline commands, important files, coding rules, and a required handoff note format.

- [x] **Step 3: Add the task board**

Create `docs/task-board.md` with status keys, active tasks, backlog, and integration queue.

- [x] **Step 4: Add the worklog**

Create `docs/worklog.md` with the current baseline and the rotation-system addition.

- [x] **Step 5: Add reference repo manifest**

Create `docs/reference-repos.md` with local repo locations, intended usage, refresh command, and integration rules.

### Task 2: README and Ignore Integration

**Files:**
- Modify: `README.md`
- Modify: `.gitignore`

- [x] **Step 1: Link README to the rotation system**

Add a "Project Rotation" section near the top of `README.md` that tells new workers to start from `docs/project-rotation.md`.

- [x] **Step 2: Ignore cloned reference repos**

Add `.codex/reference-repos/` to `.gitignore` so external research clones do not become product source.

### Task 3: Verification

**Files:**
- Verify: `README.md`
- Verify: `docs/*.md`

- [x] **Step 1: Run tests**

Run: `python -m pytest`

Expected: all product tests pass.

- [x] **Step 2: Run focused lint**

Run: `python -m ruff check src tests`

Expected: product lint passes.

## Self-Review

- Spec coverage: The user asked for a system to track work, decide what needs revisiting, and guide other contributors from the README. This plan creates those docs and links them from README.
- Placeholder scan: No task uses TBD or vague placeholder work.
- Type consistency: No code types are introduced by this plan.

