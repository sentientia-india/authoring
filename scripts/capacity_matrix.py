from __future__ import annotations

import argparse
import json

from scripts.load_test import run_load


LOAD_LEVELS = (("1x", 50, 5), ("3x", 150, 15), ("10x", 500, 50))


def run_matrix(*, url: str, timeout: float, max_error_rate: float, max_p95: float) -> dict:
    levels = []
    passed = True
    for name, requests, concurrency in LOAD_LEVELS:
        result = run_load(url=url, requests=requests, concurrency=concurrency, timeout=timeout)
        result["level"] = name
        result["concurrency"] = concurrency
        result["passed"] = result["error_rate"] <= max_error_rate and result["p95_seconds"] <= max_p95
        levels.append(result)
        passed = passed and result["passed"]
    return {"passed": passed, "max_error_rate": max_error_rate, "max_p95": max_p95, "levels": levels}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the bounded 1x, 3x, and 10x capacity gate.")
    parser.add_argument("url")
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--max-error-rate", type=float, default=0)
    parser.add_argument("--max-p95", type=float, default=0.4)
    args = parser.parse_args()
    result = run_matrix(
        url=args.url,
        timeout=args.timeout,
        max_error_rate=args.max_error_rate,
        max_p95=args.max_p95,
    )
    print(json.dumps(result))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
