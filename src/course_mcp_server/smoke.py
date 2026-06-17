from __future__ import annotations

import os

from .llm_openrouter import OpenRouterClient


def openrouter_smoke_status() -> str:
    if not os.getenv("OPENROUTER_API_KEY"):
        return "openrouter skipped: OPENROUTER_API_KEY not set"
    result = OpenRouterClient().generate_json(
        system_prompt="Return only JSON.",
        user_payload={"instruction": 'Return {"ok": true}.'},
        schema_name="SmokeTest",
    )
    if not isinstance(result, dict):
        raise RuntimeError("OpenRouter smoke response was not a JSON object")
    return "openrouter smoke passed"


def main() -> None:
    print(openrouter_smoke_status())


if __name__ == "__main__":
    main()
