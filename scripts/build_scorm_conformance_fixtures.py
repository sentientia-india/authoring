from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
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

MOODLE_PROBE = """
<button id="course-mcp-moodle-acceptance" type="button">Run Moodle acceptance</button>
<p id="course-mcp-moodle-result" role="status"></p>
<script>
(function () {
  var result = document.getElementById("course-mcp-moodle-result");
  var restored = window.CourseScorm.getLocation() === "acceptance-complete" &&
    window.CourseScorm.getSuspendData().marker === "course-mcp-moodle";
  if (restored) result.textContent = "Restored acceptance marker";
  document.getElementById("course-mcp-moodle-acceptance").addEventListener("click", function () {
    var outcomes = [
      window.CourseScorm.initialize(),
      window.CourseScorm.setLocation("acceptance-complete"),
      window.CourseScorm.setSuspendData({marker: "course-mcp-moodle"}),
      window.CourseScorm.setScore(100, 0, 100),
      window.CourseScorm.recordInteraction("final-check", "choice", "safe-exit", "correct", "Moodle acceptance"),
      window.CourseScorm.markComplete(true),
      window.CourseScorm.commit()
    ];
    result.textContent = outcomes.every(function (value) { return value === true || value === "true"; })
      ? "Acceptance complete" : "Acceptance failed";
  });
}());
</script>
""".strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inject_moodle_probe(package: Path) -> None:
    replacement = package.with_suffix(".probe.zip")
    with zipfile.ZipFile(package, "r") as source, zipfile.ZipFile(replacement, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            payload = source.read(item.filename)
            if item.filename == "index.html":
                html = payload.decode("utf-8")
                payload = html.replace("</body>", f"{MOODLE_PROBE}\n</body>").encode("utf-8")
            target.writestr(item, payload)
    replacement.replace(package)


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
            _inject_moodle_probe(expected)
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
