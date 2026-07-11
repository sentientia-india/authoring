"""Issue a customer license key for the course MCP (admin-only, run on the server).

Usage:
    python scripts/issue_license.py --tenant acme --tier pro
    python scripts/issue_license.py --tenant acme --tier white_label --expires 2027-01-01

Prints the plaintext key once; only its hash is stored in LICENSE_STORE_PATH.
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from course_mcp_server.licensing import TIER_EXPORT_QUOTAS, issue_license  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", required=True, help="Customer tenant id (unique per customer)")
    parser.add_argument("--tier", default="pro", choices=[t for t in TIER_EXPORT_QUOTAS if t != "admin"])
    parser.add_argument("--quota", type=int, default=None, help="Override monthly export quota")
    parser.add_argument("--expires", default=None, help="ISO date, e.g. 2027-01-01")
    args = parser.parse_args()

    key = f"cmk_{secrets.token_urlsafe(32)}"
    entry = issue_license(key, tenant=args.tenant, tier=args.tier, monthly_export_quota=args.quota, expires=args.expires)
    print(f"License issued for tenant '{entry['tenant']}' (tier={entry['tier']}, quota={entry['monthly_export_quota']}, expires={entry['expires']})")
    print("Give this key to the customer (it is shown only once):")
    print(key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
