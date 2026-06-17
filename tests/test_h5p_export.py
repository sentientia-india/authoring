import json
from pathlib import Path
from zipfile import ZipFile

from course_mcp_server.exporters.h5p import build_h5p_package, validate_h5p_package


def test_h5p_package_contains_required_metadata_content_and_library_files(tmp_path):
    result = build_h5p_package(
        {
            "course_title": "Ramp Safety",
            "course_slug": "ramp-safety",
            "activities": [
                {
                    "activity_type": "matching",
                    "title": "Match hazards",
                    "objective": "Match each hazard to the correct control.",
                    "items": [{"prompt": "FOD", "match": "Remove immediately"}],
                }
            ],
        },
        str(tmp_path),
    )

    package_path = Path(result["package_path"])
    assert package_path.exists()
    assert package_path.suffix == ".h5p"
    assert validate_h5p_package(package_path, result["files"]) == {"valid": True, "errors": []}

    with ZipFile(package_path) as package:
        h5p = json.loads(package.read("h5p.json"))
        content = json.loads(package.read("content/content.json"))

    assert h5p["title"] == "Ramp Safety"
    assert content["activities"][0]["type"] == "matching"
    assert content["activities"][0]["xapi"]["completion"] == "xAPI.completed"
