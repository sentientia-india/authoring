"""SCORM WYSIWYG editor service.

The editor canvas is the REAL exported course player: an imported zip is
extracted into an on-disk workspace and served at /course/<session>/..., so the
center iframe renders the exact HTML/CSS/JS learners will see. Edits update
data/course.json AND the embedded course-data script in the page shells, then
the canvas reloads. Export rebuilds a valid SCORM zip (manifest updated for any
media added in the editor).
"""

from __future__ import annotations

import argparse
import base64
import copy
import json
import mimetypes
import os
import re
import shutil
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from defusedxml import ElementTree as ET

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"

MEDIA_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif", ".mp4", ".webm", ".mp3"}
MAX_UPLOAD_BYTES = 60 * 1024 * 1024
MAX_EXTRACTED_BYTES = 300 * 1024 * 1024
MAX_ZIP_FILES = 5_000
MAX_COMPRESSION_RATIO = 200
COURSE_DATA_RE = re.compile(r'(<script id="course-data" type="application/json">)(.*?)(</script>)', re.S)


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
    ns = {"imscp": "http://www.imsproject.org/xsd/imscp_rootv1p1p2"}
    title = root.findtext(".//imscp:organization/imscp:item/imscp:title", default="", namespaces=ns)
    resource = root.find(".//imscp:resource", ns)
    return {
        "course_title": title,
        "launch_href": resource.attrib.get("href") if resource is not None else "index.html",
    }


def _import_package(zip_bytes: bytes) -> dict:
    """Compatibility parser for callers that do not need a live workspace."""
    with ZipFile(BytesIO(zip_bytes)) as package:
        names = _zip_members(package)
        if "imsmanifest.xml" not in names:
            raise ValueError("Missing imsmanifest.xml")
        if "data/course.json" not in names:
            raise ValueError("Missing data/course.json")
        manifest = _parse_manifest(package.read("imsmanifest.xml").decode("utf-8"))
        course = json.loads(package.read("data/course.json").decode("utf-8"))
        course.setdefault("course_title", manifest.get("course_title") or "Untitled Course")
        course.setdefault("course_slug", f"course-{uuid4().hex[:8]}")
        course.setdefault("modules", [])
        return {"manifest": manifest, "course": course, "files": names}


def _build_zip(zip_bytes: bytes, course_json: dict, media_files: dict[str, bytes] | None = None) -> bytes:
    """Compatibility in-memory editor used by tests and API clients."""
    normalized = copy.deepcopy(course_json)
    normalized.setdefault("modules", [])
    normalized["modules"] = [module for module in normalized["modules"] if isinstance(module, dict)]
    media_files = media_files or {}
    buffer = BytesIO()
    with ZipFile(BytesIO(zip_bytes)) as source, ZipFile(buffer, "w", ZIP_DEFLATED) as target:
        names = _zip_members(source)
        original_course = json.loads(source.read("data/course.json").decode("utf-8"))
        for protected in ("branding", "license", "license_stamp", "export_stamp"):
            if protected in original_course:
                normalized[protected] = original_course[protected]
        replacements = {f"assets/media/{Path(name).name}": payload for name, payload in media_files.items()}
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


def workspace_root() -> Path:
    root = Path(os.getenv("EDITOR_WORKSPACE_DIR", Path(tempfile.gettempdir()) / "scorm-editor-workspaces"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_session(sid: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{12}", sid or ""):
        raise ValueError("Invalid session id")
    return sid


def _workspace(sid: str) -> Path:
    path = workspace_root() / _safe_session(sid)
    if not path.is_dir():
        raise FileNotFoundError("Unknown session")
    return path


def _decode_blob(value: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError("Missing file data.")
    if "," in value[:80]:
        value = value.split(",", 1)[1]
    blob = base64.b64decode(value)
    if len(blob) > MAX_UPLOAD_BYTES:
        raise ValueError("File too large.")
    return blob


def _extract_zip(blob: bytes, target: Path) -> list[str]:
    names: list[str] = []
    with ZipFile(BytesIO(blob)) as package:
        files = [info for info in package.infolist() if not info.is_dir()]
        if len(files) > MAX_ZIP_FILES:
            raise ValueError(f"ZIP contains too many files (maximum {MAX_ZIP_FILES}).")
        expanded_size = sum(info.file_size for info in files)
        if expanded_size > MAX_EXTRACTED_BYTES:
            raise ValueError("ZIP expands beyond the allowed size.")
        for info in files:
            unix_mode = (info.external_attr >> 16) & 0xF000
            if unix_mode == 0xA000:
                raise ValueError(f"ZIP contains a symbolic link: {info.filename}")
            if info.file_size and info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO:
                raise ValueError(f"ZIP entry has an unsafe compression ratio: {info.filename}")
        for info in files:
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                raise ValueError(f"Unsafe path in zip: {name}")
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(package.read(info))
            names.append(name)
    return sorted(names)


def import_package(blob: bytes) -> dict:
    """Extract a SCORM zip into a fresh workspace; returns session + course."""
    sid = uuid4().hex[:12]
    target = workspace_root() / sid
    target.mkdir(parents=True)
    try:
        names = _extract_zip(blob, target)
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
    if "imsmanifest.xml" not in names:
        shutil.rmtree(target, ignore_errors=True)
        raise ValueError("Missing imsmanifest.xml - not a SCORM package.")
    if "data/course.json" not in names:
        shutil.rmtree(target, ignore_errors=True)
        raise ValueError("Missing data/course.json - this editor works with courses exported by the Course MCP.")
    course = json.loads((target / "data" / "course.json").read_text(encoding="utf-8"))
    return {"session": sid, "course": course, "files": names}


def save_course(sid: str, course: dict) -> dict:
    """Persist course.json and refresh the embedded course-data in all page shells."""
    workspace = _workspace(sid)
    payload = json.dumps(course, indent=2)
    (workspace / "data" / "course.json").write_text(payload, encoding="utf-8")
    embedded = payload.replace("</", "<\\/")
    for page in [workspace / "index.html", *sorted(workspace.glob("module-*.html"))]:
        if not page.is_file():
            continue
        html = page.read_text(encoding="utf-8")
        updated, count = COURSE_DATA_RE.subn(lambda m: m.group(1) + embedded + m.group(3), html)
        if count:
            page.write_text(updated, encoding="utf-8")
    theme = course.get("theme")
    if theme:
        index = workspace / "index.html"
        if index.is_file():
            html = index.read_text(encoding="utf-8")
            html = re.sub(r'data-theme="[^"]*"', f'data-theme="{theme}"', html, count=1)
            index.write_text(html, encoding="utf-8")
    return {"session": sid, "saved": True}


def add_media(sid: str, filename: str, blob: bytes) -> dict:
    workspace = _workspace(sid)
    name = Path(filename.replace("\\", "/")).name
    if not name or Path(name).suffix.lower() not in MEDIA_EXTENSIONS:
        raise ValueError("Unsupported media type.")
    media_dir = workspace / "assets" / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    (media_dir / name).write_bytes(blob)
    return {"session": sid, "src": f"assets/media/{name}"}


def _sync_manifest(workspace: Path) -> None:
    """Ensure every workspace file is declared in the manifest resource."""
    manifest_path = workspace / "imsmanifest.xml"
    manifest = manifest_path.read_text(encoding="utf-8")
    listed = set(re.findall(r'<file href="([^"]+)"', manifest))
    actual = sorted(
        str(path.relative_to(workspace)).replace("\\", "/")
        for path in workspace.rglob("*")
        if path.is_file() and path.name != "imsmanifest.xml"
    )
    missing = [name for name in actual if name not in listed]
    if missing:
        insertion = "".join(f'      <file href="{name}" />\n' for name in missing)
        manifest = manifest.replace("</resource>", insertion + "    </resource>", 1)
        manifest_path.write_text(manifest, encoding="utf-8")


def export_package(sid: str) -> bytes:
    workspace = _workspace(sid)
    _sync_manifest(workspace)
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as package:
        for path in sorted(workspace.rglob("*")):
            if path.is_file():
                package.write(path, str(path.relative_to(workspace)).replace("\\", "/"))
    return buffer.getvalue()


class Handler(BaseHTTPRequestHandler):
    server_version = "SCORMEditor/2.0"

    def log_message(self, *args) -> None:  # keep the console quiet
        pass

    def _headers(self, status: HTTPStatus = HTTPStatus.OK, content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _json(self, status: HTTPStatus, payload: dict) -> None:
        self._headers(status, "application/json; charset=utf-8")
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def _body(self) -> dict:
        length = int(self.headers.get("content-length", "0"))
        if length > MAX_UPLOAD_BYTES * 2:
            raise ValueError("Request too large")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _serve_file(self, path: Path) -> bool:
        if not path.is_file():
            return False
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._headers(content_type=content_type)
        self.wfile.write(path.read_bytes())
        return True

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        try:
            if route in ("/", "/index.html"):
                self._serve_file(STATIC / "index.html")
                return
            if route.startswith("/static/"):
                relative = route.removeprefix("/static/")
                if ".." not in relative and self._serve_file(STATIC / relative):
                    return
            if route.startswith("/course/"):
                parts = route.removeprefix("/course/").split("/", 1)
                if len(parts) == 2 and ".." not in parts[1]:
                    if self._serve_file(_workspace(parts[0]) / parts[1]):
                        return
            if route.startswith("/api/course/"):
                sid = route.removeprefix("/api/course/")
                course = json.loads((_workspace(sid) / "data" / "course.json").read_text(encoding="utf-8"))
                self._json(HTTPStatus.OK, {"session": sid, "course": course})
                return
        except (ValueError, FileNotFoundError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})

    def do_PUT(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        try:
            if route.startswith("/api/course/"):
                sid = route.removeprefix("/api/course/")
                body = self._body()
                result = save_course(sid, body.get("course") or {})
                self._json(HTTPStatus.OK, {"ok": True, **result})
                return
        except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        try:
            if route == "/api/import":
                body = self._body()
                result = import_package(_decode_blob(body.get("zip", "")))
                self._json(HTTPStatus.OK, {"ok": True, **result})
                return
            if route.startswith("/api/media/"):
                sid = route.removeprefix("/api/media/")
                body = self._body()
                result = add_media(sid, body.get("filename", ""), _decode_blob(body.get("content_base64", "")))
                self._json(HTTPStatus.OK, {"ok": True, **result})
                return
            if route.startswith("/api/export/"):
                sid = route.removeprefix("/api/export/")
                blob = export_package(sid)
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", 'attachment; filename="course-edited.zip"')
                self.send_header("Content-Length", str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)
                return
        except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the SCORM WYSIWYG editor service.")
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
