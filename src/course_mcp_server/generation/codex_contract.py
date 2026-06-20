from __future__ import annotations

from typing import Any

UNSAFE_PAYLOAD_KEYS = {
    "raw_logs",
    "internal_prompts",
    "source_code",
    "secrets",
    "env",
    "database_query",
    "shell",
    "docker",
    "file_paths",
}


class CodexGenerationContractBuilder:
    def build(
        self,
        *,
        project_id: str,
        course_brief: dict[str, Any],
        selected_template: dict[str, Any],
        approved_module_outline: list[dict[str, Any]],
        approved_lesson_structure: list[dict[str, Any]],
        assessment_model: dict[str, Any],
        interaction_model: dict[str, Any],
        source_chunks: list[dict[str, Any]],
        export_targets: list[str],
    ) -> dict[str, Any]:
        payload = {
            "project_id": project_id,
            "course_brief": course_brief,
            "selected_template": selected_template,
            "approved_module_outline": approved_module_outline,
            "approved_lesson_structure": approved_lesson_structure,
            "assessment_model": assessment_model,
            "interaction_model": interaction_model,
            "source_chunks": self._safe_source_chunks(source_chunks),
            "quality_rules": selected_template.get("quality_rules", selected_template.get("quality_thresholds", {})),
            "codex_prompt_rules": selected_template.get("codex_prompt_rules", selected_template.get("prompt_rules", [])),
            "export_targets": export_targets,
            "required_output": [
                "course_blueprint",
                "modules",
                "lessons",
                "scenario_activities",
                "assessment_bank",
                "remediation_mapping",
                "html_video_project",
                "gamification_events",
                "scorm_runtime_data",
            ],
        }
        self._validate_safe_payload(payload)
        return payload

    def _safe_source_chunks(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        allowed = []
        for chunk in chunks:
            allowed.append(
                {
                    "source_id": chunk.get("source_id"),
                    "chunk_id": chunk.get("chunk_id"),
                    "page": chunk.get("page"),
                    "slide": chunk.get("slide"),
                    "timestamp": chunk.get("timestamp"),
                    "text": chunk.get("text") or chunk.get("content"),
                    "summary": chunk.get("summary"),
                }
            )
        return allowed

    def _validate_safe_payload(self, payload: dict[str, Any]) -> None:
        found = set(payload).intersection(UNSAFE_PAYLOAD_KEYS)
        if found:
            raise ValueError(f"Unsafe keys in Codex payload: {sorted(found)}")
        if not payload["selected_template"]:
            raise ValueError("Codex payload missing selected template.")
        if not payload["approved_module_outline"]:
            raise ValueError("Codex payload missing approved module outline.")
        if not payload["approved_lesson_structure"]:
            raise ValueError("Codex payload missing approved lesson structure.")
        if not payload["source_chunks"]:
            raise ValueError("Codex payload missing source chunks.")
