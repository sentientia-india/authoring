from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from course_mcp_server.exporters.scorm import build_scorm_package, validate_scorm_package
from course_mcp_server.schemas import ScormPackageRequest


COURSE = {
    "title": "Cabin Evacuation Decision Practice",
    "slug": "cabin-evacuation-conformance",
    "modules": [
        {
            "title": "Evacuation Decisions",
            "lessons": [
                {
                    "title": "Assess the exit",
                    "objective": "Choose a safe exit using smoke, commands, and slide conditions.",
                    "content": "Assess smoke direction, exit condition, and commands before opening an exit.",
                }
            ],
        }
    ],
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(output: Path, verify_only: bool = False) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for version in ("1.2", "2004"):
        expected = output / f"course-mcp-scorm-{version.replace('.', '')}.zip"
        if not verify_only:
            result = build_scorm_package(
                ScormPackageRequest(
                    course_title=COURSE["title"],
                    course_slug=COURSE["slug"],
                    modules=COURSE["modules"],
                    scorm_version=version,
                ),
                str(output / "build" / version.replace(".", "")),
            )
            Path(result["package_path"]).replace(expected)
            required = result["files"]
        else:
            if not expected.is_file():
                raise FileNotFoundError(expected)
            required = ["imsmanifest.xml", "index.html", "assets/scorm_api.js", "data/course.json"]
        report = validate_scorm_package(expected, required)
        if not report["valid"]:
            raise RuntimeError(f"SCORM {version} fixture is invalid: {report['errors']}")
        records.append(
            {
                "scorm_version": version,
                "file": expected.name,
                "sha256": _sha256(expected),
                "validation": report,
            }
        )
    evidence = {"moodle_target": "4.5 LTS", "packages": records}
    (output / "conformance.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deterministic SCORM LMS conformance fixtures.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    build(args.output, args.verify_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
