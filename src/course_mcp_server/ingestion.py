from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path
from zipfile import ZipFile

from defusedxml import ElementTree


@dataclass(frozen=True)
class ExtractedSource:
    text: str
    headings: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    tables: list[list[str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _xml_text(xml: str) -> list[str]:
    root = ElementTree.fromstring(xml)
    return [_collapse(node.text or "") for node in root.iter() if node.text and _collapse(node.text)]


def _extract_docx(path: Path) -> ExtractedSource:
    with ZipFile(path) as package:
        xml = package.read("word/document.xml").decode("utf-8", errors="ignore")
    root = ElementTree.fromstring(xml)
    paragraphs: list[str] = []
    headings: list[str] = []
    for para in root.iter():
        if not para.tag.endswith("}p"):
            continue
        texts = [_collapse(node.text or "") for node in para.iter() if node.tag.endswith("}t") and node.text]
        text = " ".join(part for part in texts if part).strip()
        if not text:
            continue
        paragraphs.append(text)
        para_xml = ElementTree.tostring(para, encoding="unicode")
        if "Heading" in para_xml:
            headings.append(text)
    refs = [f"section:{heading}" for heading in headings] or ["section:body"]
    return ExtractedSource(text="\n".join(paragraphs), headings=headings, references=refs)


def _slide_number(name: str) -> int:
    match = re.search(r"(\d+)\.xml$", name)
    return int(match.group(1)) if match else 0


def _extract_pptx(path: Path) -> ExtractedSource:
    lines: list[str] = []
    refs: list[str] = []
    with ZipFile(path) as package:
        slide_names = sorted(
            [name for name in package.namelist() if name.startswith("ppt/slides/slide")],
            key=_slide_number,
        )
        note_names = sorted(
            [name for name in package.namelist() if name.startswith("ppt/notesSlides/notesSlide")],
            key=_slide_number,
        )
        for name in slide_names:
            number = _slide_number(name)
            text = " ".join(_xml_text(package.read(name).decode("utf-8", errors="ignore")))
            if text:
                lines.append(f"Slide {number}: {text}")
                refs.append(f"slide:{number}")
        for name in note_names:
            number = _slide_number(name)
            text = " ".join(_xml_text(package.read(name).decode("utf-8", errors="ignore")))
            if text:
                lines.append(f"Notes {number}: {text}")
                refs.append(f"notes:{number}")
    return ExtractedSource(text="\n".join(lines), references=refs)


def _extract_pdf(path: Path) -> ExtractedSource:
    raw = path.read_bytes().decode("latin-1", errors="ignore")
    strings = re.findall(r"\(([^()] {0,0}.*?)\)\s*Tj", raw)
    if not strings:
        strings = re.findall(r"[A-Za-z][A-Za-z0-9 ,.;:!?'-]{4,}", raw)
    text = "\n".join(_collapse(item) for item in strings if _collapse(item))
    page_count = max(1, raw.count("/Page") or raw.count("%%Page") or 1)
    return ExtractedSource(text=text, references=[f"page:{index}" for index in range(1, page_count + 1)])


def _extract_timed_text(path: Path) -> ExtractedSource:
    text = path.read_text(encoding="utf-8", errors="ignore")
    refs = re.findall(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b", text)
    return ExtractedSource(text=text, references=[f"timestamp:{stamp}" for stamp in refs])


def _extract_raw_text(path: Path) -> ExtractedSource:
    text = path.read_text(encoding="utf-8", errors="ignore")
    headings = [
        line.lstrip("#").strip()
        for line in text.splitlines()
        if line.strip().startswith("#") and line.lstrip("#").strip()
    ]
    refs = [f"section:{heading}" for heading in headings] or ["line:1"]
    return ExtractedSource(text=text, headings=headings, references=refs)


def extract_source(path: Path | str, source_type: str) -> ExtractedSource:
    source_path = Path(path)
    if source_type == "docx":
        return _extract_docx(source_path)
    if source_type in {"pptx", "ppt"}:
        return _extract_pptx(source_path)
    if source_type == "pdf":
        return _extract_pdf(source_path)
    if source_type in {"youtube", "website"}:
        return _extract_timed_text(source_path)
    return _extract_raw_text(source_path)
