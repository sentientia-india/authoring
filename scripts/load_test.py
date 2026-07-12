from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import time
import urllib.request


def request_once(url: str, timeout: float) -> tuple[float, bool]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # nosec B310 - operator URL
            response.read()
            success = 200 <= response.status < 300
    except Exception:  # noqa: BLE001
        success = False
    return time.perf_counter() - started, success


def run_load(*, url: str, requests: int, concurrency: int, timeout: float) -> dict:
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(lambda _index: request_once(url, timeout), range(requests)))
    latencies = sorted(duration for duration, _ in results)
    successes = sum(success for _, success in results)

    def percentile(value: float) -> float:
        if not latencies:
            return 0
        index = min(len(latencies) - 1, max(0, int(round(value * (len(latencies) - 1)))))
        return latencies[index]

    return {
        "requests": requests,
        "successes": successes,
        "errors": requests - successes,
        "error_rate": round((requests - successes) / max(1, requests), 4),
        "mean_seconds": round(statistics.fmean(latencies), 4) if latencies else 0,
        "p95_seconds": round(percentile(0.95), 4),
        "p99_seconds": round(percentile(0.99), 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a bounded HTTP load and SLO check.")
    parser.add_argument("url")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument("--max-p95", type=float, default=0.4)
    args = parser.parse_args()
    if args.requests < 1 or args.concurrency < 1 or args.concurrency > 100:
        parser.error("requests and concurrency are outside safe bounds")
    result = run_load(
        url=args.url, requests=args.requests, concurrency=args.concurrency, timeout=args.timeout
    )
    print(json.dumps(result))
    return int(result["error_rate"] > args.max_error_rate or result["p95_seconds"] > args.max_p95)


if __name__ == "__main__":
    raise SystemExit(main())
