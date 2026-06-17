# Export Adapter Roadmap

This document captures the safe integration plan for H5P, LiaScript, and LMS export work. These integrations must stay internal until a human approval workflow and narrow tool contracts are approved.

## Current State

- SCORM package generation exists through `build_export_package`.
- Generated SCORM zip packages include `imsmanifest.xml`, `index.html`, module pages, and `scorm_api.js`.
- Internal validation checks for readable zip structure, required files, manifest root, and SCO resource declaration.
- No LMS publish/upload tool is exposed.

## H5P Adapter Plan

Reference: `.codex/reference-repos/scorm-h5p-wrapper`

Safe implementation shape:

1. Accept already-normalized internal course assets, not arbitrary file paths.
2. Generate a bounded H5P content payload in an internal temp/output directory.
3. Package H5P into SCORM only through a fixed internal pipeline.
4. Return structured metadata only: package id, package path, validation status, and warnings.
5. Require human approval before any external LMS upload.

Do not expose:

- arbitrary H5P file upload from the filesystem
- arbitrary path selection
- shell commands
- external web fetch tools
- LMS credentials or upload logs

## LiaScript Adapter Plan

Reference: `.codex/reference-repos/LiaScript-Exporter`

Safe implementation shape:

1. Convert internal course JSON into a deterministic LiaScript Markdown document.
2. Keep export execution inside the container and inside `OUTPUT_DIR`.
3. Validate generated output before returning metadata.
4. Consider SCORM export only after the SCORM validator is stricter.

Do not expose:

- `--git-url` export to arbitrary repositories through MCP
- arbitrary input file paths
- raw exporter logs
- shell passthrough

## Approval Requirement

Publishing to LMS or sending packages to external systems is high risk. Use `course_mcp_server.approval.require_human_approval` before adding any internal publisher. Do not expose publish tools until `docs/tool-contracts.md` explicitly adds a safe contract.
