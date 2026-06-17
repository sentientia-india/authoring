from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def _ensure_inside(parent: Path, child: Path) -> None:
    child.resolve().relative_to(parent.resolve())


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _normalize_activity(activity: dict) -> dict:
    return {
        "type": activity.get("activity_type", activity.get("type", "flashcards")),
        "title": activity.get("title", "Interactive Activity"),
        "objective": activity.get("objective", "Complete the activity."),
        "items": activity.get("items", []),
        "xapi": {
            "completion": "xAPI.completed",
            "score": "xAPI.answered",
        },
    }


def validate_h5p_package(package_path: Path | str, expected_files: list[str]) -> dict:
    path = Path(package_path)
    errors: list[str] = []
    if not path.exists():
        return {"valid": False, "errors": [f"Package does not exist: {path.name}"]}
    if path.suffix != ".h5p":
        errors.append("Package must use .h5p extension.")
    try:
        with ZipFile(path) as package:
            names = set(package.namelist())
            for file_name in expected_files:
                if file_name not in names:
                    errors.append(f"Missing package file: {file_name}")
            if "h5p.json" in names:
                metadata = json.loads(package.read("h5p.json"))
                if "title" not in metadata or "mainLibrary" not in metadata:
                    errors.append("h5p.json is missing required metadata.")
            if "content/content.json" in names:
                content = json.loads(package.read("content/content.json"))
                if not content.get("activities"):
                    errors.append("content/content.json has no activities.")
    except Exception:
        errors.append("Package is not a readable H5P zip archive.")
    return {"valid": not errors, "errors": errors}


def build_h5p_package(course: dict, output_dir: str) -> dict:
    root = Path(output_dir).resolve()
    slug = str(course["course_slug"])
    base = root / f"{slug}-h5p"
    _ensure_inside(root, base)
    content_dir = base / "content"
    library_dir = base / "H5P.SamratCourse-1.0"
    base.mkdir(parents=True, exist_ok=True)
    content_dir.mkdir(exist_ok=True)
    library_dir.mkdir(exist_ok=True)

    activities = [_normalize_activity(activity) for activity in course.get("activities", [])]
    if not activities:
        activities = [
            _normalize_activity(
                {
                    "activity_type": "reflection_prompt",
                    "title": "Reflection",
                    "objective": "Reflect on the course objective.",
                    "items": [{"prompt": "What will you apply first?"}],
                }
            )
        ]

    h5p_json = {
        "title": course["course_title"],
        "language": "en",
        "mainLibrary": "H5P.SamratCourse",
        "embedTypes": ["div"],
        "preloadedDependencies": [{"machineName": "H5P.SamratCourse", "majorVersion": 1, "minorVersion": 0}],
    }
    content_json = {
        "courseTitle": course["course_title"],
        "activities": activities,
    }
    library_json = {
        "title": "Samrat Course Activities",
        "machineName": "H5P.SamratCourse",
        "majorVersion": 1,
        "minorVersion": 0,
        "patchVersion": 0,
        "runnable": 1,
        "preloadedJs": [{"path": "semantics.js"}],
    }
    semantics_js = "window.H5PSamratCourse = { version: '1.0.0' };\n"

    files = [
        "h5p.json",
        "content/content.json",
        "H5P.SamratCourse-1.0/library.json",
        "H5P.SamratCourse-1.0/semantics.js",
    ]
    _write_json(base / "h5p.json", h5p_json)
    _write_json(content_dir / "content.json", content_json)
    _write_json(library_dir / "library.json", library_json)
    (library_dir / "semantics.js").write_text(semantics_js, encoding="utf-8")

    package_path = root / f"{slug}.h5p"
    _ensure_inside(root, package_path)
    with ZipFile(package_path, "w", ZIP_DEFLATED) as package:
        for file_name in files:
            package.write(base / file_name, file_name)

    validation = validate_h5p_package(package_path, files)
    return {
        "course_title": course["course_title"],
        "course_slug": slug,
        "export_format": "h5p",
        "artifact_path": str(base),
        "package_path": str(package_path),
        "files": files,
        "note": "H5P package created and internally validated."
        if validation["valid"]
        else "H5P package created but validation reported issues.",
    }
