"""Backward-compatible re-export shim.

The real implementation moved to text_providers/openrouter.py as part of the TextProvider
adapter refactor (P5-1b). Every symbol that used to live in this module is re-exported here
unchanged so existing imports (`from .llm_openrouter import OpenRouterClient`,
`from course_mcp_server.llm_openrouter import OpenRouterClient, OpenRouterError`, etc.)
continue to work without modification.
"""

from __future__ import annotations

from .text_providers.openrouter import (
    DEFAULT_OPENROUTER_BASE_URL,
    DEFAULT_OPENROUTER_MODEL,
    OpenRouterClient,
    OpenRouterConfig,
    OpenRouterError,
    OpenRouterTextProvider,
    Transport,
    extract_json_object,
)

__all__ = [
    "DEFAULT_OPENROUTER_BASE_URL",
    "DEFAULT_OPENROUTER_MODEL",
    "OpenRouterClient",
    "OpenRouterConfig",
    "OpenRouterError",
    "OpenRouterTextProvider",
    "Transport",
    "extract_json_object",
]
