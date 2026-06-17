from pathlib import Path
from zipfile import ZipFile

from course_mcp_server.exporters.scorm import build_scorm_scaffold, validate_scorm_package
from course_mcp_server.schemas import ScormPackageRequest


def test_scorm_scaffold_creates_zip_with_manifest_and_module_pages(tmp_path):
    result = build_scorm_scaffold(
        ScormPackageRequest(
            course_title="Ramp Safety",
            course_slug="ramp-safety",
            modules=[
                {
                    "title": "Hazards",
                    "lessons": [
                        {
                            "title": "Spot hazards",
                            "objective": "Identify hazards",
                            "duration_minutes": 15,
                        }
                    ],
                }
            ],
        ),
        str(tmp_path),
    )

    package_path = Path(result["package_path"])
    assert package_path.exists()
    assert package_path.suffix == ".zip"
    assert result["files"] == ["imsmanifest.xml", "index.html", "module-1.html", "scorm_api.js"]

    with ZipFile(package_path) as package:
        names = sorted(package.namelist())
        assert names == ["imsmanifest.xml", "index.html", "module-1.html", "scorm_api.js"]
        assert "module-1.html" in package.read("imsmanifest.xml").decode("utf-8")


def test_scorm_artifact_path_stays_inside_output_dir(tmp_path):
    result = build_scorm_scaffold(
        ScormPackageRequest(
            course_title="Safe Course",
            course_slug="safe-course",
            modules=[{"title": "Intro", "lessons": []}],
        ),
        str(tmp_path),
    )

    artifact_path = Path(result["artifact_path"]).resolve()
    assert artifact_path.is_relative_to(tmp_path.resolve())


def test_validate_scorm_package_reports_missing_manifest(tmp_path):
    package_path = tmp_path / "broken.zip"
    with ZipFile(package_path, "w") as package:
        package.writestr("index.html", "<html></html>")

    result = validate_scorm_package(package_path, ["imsmanifest.xml", "index.html"])

    assert result["valid"] is False
    assert "Missing package file: imsmanifest.xml" in result["errors"]
