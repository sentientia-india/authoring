from __future__ import annotations

from html import escape
from pathlib import Path

from ..schemas import ScormPackageRequest


def build_scorm_scaffold(req: ScormPackageRequest, output_dir: str) -> dict:
    base = Path(output_dir).resolve() / req.course_slug
    base.mkdir(parents=True, exist_ok=True)

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
    </resource>
  </resources>
</manifest>
'''
    index = f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>{escape(req.course_title)}</title></head>
<body>
  <h1>{escape(req.course_title)}</h1>
  <p>This is a generated SCORM scaffold. Replace with full course runtime.</p>
</body>
</html>
"""

    (base / "imsmanifest.xml").write_text(manifest, encoding="utf-8")
    (base / "index.html").write_text(index, encoding="utf-8")

    return {
        "course_title": req.course_title,
        "course_slug": req.course_slug,
        "scorm_version": req.scorm_version,
        "artifact_path": str(base),
        "files": ["imsmanifest.xml", "index.html"],
        "note": "Scaffold created. Run SCORM validation before publishing to LMS.",
    }
