from __future__ import annotations

from html import escape
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from ..schemas import ScormPackageRequest, ScormPackageResult


def _ensure_inside(parent: Path, child: Path) -> None:
    child.resolve().relative_to(parent.resolve())


def _module_page_name(index: int) -> str:
    return f"module-{index}.html"


def _write_zip(package_path: Path, base: Path, files: list[str]) -> None:
    with ZipFile(package_path, "w", ZIP_DEFLATED) as package:
        for file_name in files:
            package.write(base / file_name, file_name)


def validate_scorm_package(package_path: Path | str, expected_files: list[str]) -> dict:
    errors: list[str] = []
    path = Path(package_path)
    if not path.exists():
        return {"valid": False, "errors": [f"Package does not exist: {path.name}"]}
    if path.suffix.lower() != ".zip":
        errors.append("Package must be a .zip file.")

    try:
        with ZipFile(path) as package:
            names = set(package.namelist())
            for file_name in expected_files:
                if file_name not in names:
                    errors.append(f"Missing package file: {file_name}")
            manifest = package.read("imsmanifest.xml").decode("utf-8") if "imsmanifest.xml" in names else ""
            if manifest and "<manifest" not in manifest:
                errors.append("imsmanifest.xml does not contain a manifest root.")
            if manifest and "adlcp:scormtype=\"sco\"" not in manifest:
                errors.append("Manifest does not declare a SCO resource.")
    except Exception:
        errors.append("Package is not a readable zip archive.")

    return {"valid": not errors, "errors": errors}


def build_scorm_scaffold(req: ScormPackageRequest, output_dir: str) -> dict:
    root = Path(output_dir).resolve()
    base = root / req.course_slug
    _ensure_inside(root, base)
    base.mkdir(parents=True, exist_ok=True)
    module_files = [_module_page_name(i) for i, _module in enumerate(req.modules, start=1)]
    files = ["imsmanifest.xml", "index.html", *module_files, "scorm_api.js"]

    manifest = f'''<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="{escape(req.course_slug)}" version="1.0"
  xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>{escape(req.scorm_version)}</schemaversion>
  </metadata>
  <organizations default="org1">
    <organization identifier="org1">
      <title>{escape(req.course_title)}</title>
      <item identifier="item1" identifierref="res1">
        <title>{escape(req.course_title)}</title>
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="res1" type="webcontent" adlcp:scormtype="sco" href="index.html">
      <file href="index.html" />
{chr(10).join(f'      <file href="{escape(file_name)}" />' for file_name in module_files)}
      <file href="scorm_api.js" />
    </resource>
  </resources>
</manifest>
'''
    navigation = "\n".join(
        f'<li><a href="{escape(file_name)}">{escape(module.get("title", f"Module {i}"))}</a></li>'
        for i, (file_name, module) in enumerate(zip(module_files, req.modules, strict=True), start=1)
    )
    index = f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>{escape(req.course_title)}</title><script src="scorm_api.js"></script></head>
<body>
  <h1>{escape(req.course_title)}</h1>
  <p>Generated SCORM package scaffold.</p>
  <ol>
    {navigation}
  </ol>
  <button onclick="CourseScorm.markComplete()">Mark complete</button>
</body>
</html>
"""
    runtime = """window.CourseScorm = {
  markComplete: function () {
    var api = window.API || window.API_1484_11;
    if (!api) return false;
    if (api.LMSSetValue) {
      api.LMSSetValue('cmi.core.lesson_status', 'completed');
      api.LMSCommit && api.LMSCommit('');
      return true;
    }
    if (api.SetValue) {
      api.SetValue('cmi.completion_status', 'completed');
      api.Commit && api.Commit('');
      return true;
    }
    return false;
  }
};
"""

    (base / "imsmanifest.xml").write_text(manifest, encoding="utf-8")
    (base / "index.html").write_text(index, encoding="utf-8")
    (base / "scorm_api.js").write_text(runtime, encoding="utf-8")
    for i, (file_name, module) in enumerate(zip(module_files, req.modules, strict=True), start=1):
        lessons = module.get("lessons", [])
        lesson_items = "\n".join(
            f"<li>{escape(str(lesson.get('title', 'Lesson')))}: "
            f"{escape(str(lesson.get('objective', 'Practice the module objective.')))}</li>"
            for lesson in lessons
        )
        page = f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>{escape(str(module.get("title", f"Module {i}")))}</title><script src="scorm_api.js"></script></head>
<body>
  <nav><a href="index.html">Course index</a></nav>
  <h1>{escape(str(module.get("title", f"Module {i}")))}</h1>
  <ul>{lesson_items}</ul>
  <button onclick="CourseScorm.markComplete()">Mark complete</button>
</body>
</html>
"""
        (base / file_name).write_text(page, encoding="utf-8")

    package_path = root / f"{req.course_slug}.zip"
    _ensure_inside(root, package_path)
    _write_zip(package_path, base, files)
    validation = validate_scorm_package(package_path, files)

    return ScormPackageResult(
        course_title=req.course_title,
        course_slug=req.course_slug,
        scorm_version=req.scorm_version,
        artifact_path=str(base),
        package_path=str(package_path),
        files=files,
        note=(
            "SCORM package scaffold created and internally validated."
            if validation["valid"]
            else "SCORM package scaffold created but validation reported issues."
        ),
    ).model_dump(mode="json")
