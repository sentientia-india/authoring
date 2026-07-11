from __future__ import annotations

import argparse
import base64
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile
import copy
from defusedxml import ElementTree as ET


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
SAMPLES = STATIC / "samples"


def _index_html() -> bytes:
    return (STATIC / "index.html").read_bytes()


def _read_json(text: str) -> dict:
    return json.loads(text)


def _zip_members(package: ZipFile) -> list[str]:
    names = sorted(name for name in package.namelist() if not name.endswith("/"))
    for name in names:
        member = PurePosixPath(name.replace("\\", "/"))
        if member.is_absolute() or ".." in member.parts:
            raise ValueError(f"Unsafe ZIP member: {name}")
    return names


def _parse_manifest(xml_text: str) -> dict:
    if not xml_text.strip():
        raise ValueError("Missing imsmanifest.xml")
    root = ET.fromstring(xml_text)
    ns = {
        "imscp": "http://www.imsproject.org/xsd/imscp_rootv1p1p2",
        "adlcp": "http://www.adlnet.org/xsd/adlcp_rootv1p2",
    }
    title = root.findtext(".//imscp:organization/imscp:item/imscp:title", default="", namespaces=ns)
    href = root.find(".//imscp:resource", ns)
    return {
        "course_title": title,
        "launch_href": href.attrib.get("href") if href is not None else "index.html",
    }


def _import_package(zip_bytes: bytes) -> dict:
    with ZipFile(BytesIO(zip_bytes)) as package:
        names = _zip_members(package)
        if "imsmanifest.xml" not in names:
            raise ValueError("Missing imsmanifest.xml")
        if "data/course.json" not in names:
            raise ValueError("Missing data/course.json")
        manifest = _parse_manifest(package.read("imsmanifest.xml").decode("utf-8"))
        course = _read_json(package.read("data/course.json").decode("utf-8"))
        course.setdefault("course_title", manifest.get("course_title") or course.get("course_title") or "Untitled Course")
        course.setdefault("course_slug", course.get("course_slug") or f"course-{uuid4().hex[:8]}")
        course.setdefault("modules", [])
        return {
            "manifest": manifest,
            "course": course,
            "files": names,
    }


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    content_length = int(handler.headers.get("content-length", "0"))
    payload = handler.rfile.read(content_length)
    return json.loads(payload.decode("utf-8"))


def _decode_zip_blob(value: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError("Missing zip file.")
    if "," in value:
        value = value.split(",", 1)[1]
    return base64.b64decode(value)


def _normalize_course(course: dict) -> dict:
    course = copy.deepcopy(course)
    course.setdefault("modules", [])
    course["modules"] = [module for module in course["modules"] if isinstance(module, dict)]
    for module in course["modules"]:
        module.setdefault("lessons", [])
        module.setdefault("activities", [])
        module["lessons"] = [lesson for lesson in module["lessons"] if isinstance(lesson, dict)]
        module["activities"] = [activity for activity in module["activities"] if isinstance(activity, dict)]
    return course


def _build_zip(zip_bytes: bytes, course_json: dict, media_files: dict[str, bytes] | None = None) -> bytes:
    normalized = _normalize_course(course_json)
    media_files = media_files or {}
    buffer = BytesIO()
    with ZipFile(BytesIO(zip_bytes)) as source, ZipFile(buffer, "w", ZIP_DEFLATED) as target:
        names = _zip_members(source)
        original_course = _read_json(source.read("data/course.json").decode("utf-8"))
        for protected in ("branding", "license", "license_stamp", "export_stamp"):
            if protected in original_course:
                normalized[protected] = original_course[protected]
        replacements = {f"assets/media/{name}": payload for name, payload in media_files.items()}
        for name in names:
            if name == "data/course.json":
                target.writestr(name, json.dumps(normalized, indent=2))
            elif name in replacements:
                target.writestr(name, replacements.pop(name))
            else:
                target.writestr(name, source.read(name))
        for name, payload in replacements.items():
            target.writestr(name, payload)
    return buffer.getvalue()


def _decode_media_files(value: dict | None) -> dict[str, bytes]:
    decoded: dict[str, bytes] = {}
    for filename, blob in (value or {}).items():
        safe_name = Path(str(filename)).name
        if safe_name != filename or not safe_name:
            raise ValueError("Media filenames must not contain paths")
        payload = _decode_zip_blob(blob)
        if len(payload) > 25 * 1024 * 1024:
            raise ValueError(f"Media file is too large: {safe_name}")
        decoded[safe_name] = payload
    return decoded


class Handler(BaseHTTPRequestHandler):
    server_version = "SCORMEditor/1.0"

    def _set_headers(self, status: HTTPStatus = HTTPStatus.OK, content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _json(self, status: HTTPStatus, payload: dict) -> None:
        self._set_headers(status, "application/json; charset=utf-8")
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/" or route == "/index.html":
            self._set_headers()
            self.wfile.write(_index_html())
            return
        if route == "/api/samples":
            samples = []
            if SAMPLES.exists():
                for path in sorted(SAMPLES.glob("*.zip")):
                    samples.append(
                        {
                            "id": path.stem,
                            "title": path.stem.replace("-", " ").title(),
                            "url": f"/static/samples/{path.name}",
                            "size_bytes": path.stat().st_size,
                        }
                    )
            self._json(HTTPStatus.OK, {"ok": True, "data": samples})
            return
        if route.startswith("/static/"):
            asset = STATIC / route.removeprefix("/static/")
            if asset.exists() and asset.is_file():
                content_type = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
                self._set_headers(content_type=content_type)
                self.wfile.write(asset.read_bytes())
                return
        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/api/import":
            self._handle_import()
            return
        if route == "/api/export":
            self._handle_export()
            return
        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})

    def _handle_import(self) -> None:
        try:
            body = _read_json_body(self)
            imported = _import_package(_decode_zip_blob(body.get("zip", "")))
        except Exception as exc:  # noqa: BLE001
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        self._json(HTTPStatus.OK, {"ok": True, "data": imported})

    def _handle_export(self) -> None:
        try:
            body = _read_json_body(self)
            rebuilt = _build_zip(
                _decode_zip_blob(body.get("zip", "")),
                body.get("course", {}),
                _decode_media_files(body.get("media_files")),
            )
        except Exception as exc:  # noqa: BLE001
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", 'attachment; filename="scorm-editor-export.zip"')
        self.send_header("Content-Length", str(len(rebuilt)))
        self.end_headers()
        self.wfile.write(rebuilt)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the SCORM editor service.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8788, type=int)
    args = parser.parse_args(argv)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"SCORM editor listening on http://{args.host}:{args.port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
