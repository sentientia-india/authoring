from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PublishPlan:
    lms: Literal["moodle", "canvas", "custom"]
    required_secret_names: list[str]
    approval_required: bool
    supported_actions: list[str]


def build_publish_plan(lms: Literal["moodle", "canvas", "custom"]) -> dict:
    secret_names = {
        "moodle": ["MOODLE_BASE_URL", "MOODLE_TOKEN"],
        "canvas": ["CANVAS_BASE_URL", "CANVAS_OAUTH_TOKEN"],
        "custom": ["CUSTOM_LMS_BASE_URL", "CUSTOM_LMS_TOKEN"],
    }
    actions = {
        "moodle": ["upload_scorm_package", "create_course_module", "set_completion", "sync_gradebook"],
        "canvas": ["upload_file", "create_module_item", "configure_external_tool", "sync_gradebook"],
        "custom": ["upload_package", "register_course", "sync_completion"],
    }
    return PublishPlan(
        lms=lms,
        required_secret_names=secret_names[lms],
        approval_required=True,
        supported_actions=actions[lms],
    ).__dict__
