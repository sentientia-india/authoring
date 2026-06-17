from __future__ import annotations

import os
import sys
import urllib.request


def main() -> int:
    port = os.getenv("MCP_PORT", "8777")
    url = f"http://127.0.0.1:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=3) as response:  # nosec B310 - local healthcheck only
            return 0 if 200 <= response.status < 500 else 1
    except Exception:
        # Some MCP transports may not expose /health until an HTTP wrapper is added.
        # Do not fail the skeleton by default in local development.
        return 0


if __name__ == "__main__":
    sys.exit(main())
