from pathlib import Path

import pytest

from course_mcp_server.source_ingestion import SourceIngestionError, ingest_source_from_upload, resolve_under_root


def test_resolve_under_root_rejects_escape(tmp_path: Path):
    with pytest.raises(SourceIngestionError):
        resolve_under_root(tmp_path, "../secret.txt")


def test_ingest_text_file(tmp_path: Path):
    source = tmp_path / "sop.txt"
    source.write_text("Emergency evacuation procedure\nStep 1: assess conditions\nStep 2: communicate clearly", encoding="utf-8")
    result = ingest_source_from_upload(tmp_path, "sop.txt")
    assert result.source_type == "txt"
    assert "Emergency evacuation" in result.text
    assert result.chunks
    assert result.source_id.startswith("src_")


def test_ingest_rejects_absolute_path(tmp_path: Path):
    with pytest.raises(SourceIngestionError):
        ingest_source_from_upload(tmp_path, str(tmp_path / "sop.txt"))


def test_pdf_chunks_keep_page_anchored_source_refs(monkeypatch, tmp_path: Path):
    source = tmp_path / "manual.pdf"
    source.write_bytes(b"%PDF-1.4 fixture")

    class Page:
        def __init__(self, text: str):
            self.text = text

        def extract_text(self):
            return self.text

    class Reader:
        def __init__(self, _path):
            self.pages = [Page("Alpha procedure"), Page("Beta procedure")]

    import pypdf

    monkeypatch.setattr(pypdf, "PdfReader", Reader)
    result = ingest_source_from_upload(tmp_path, "manual.pdf")

    assert [chunk["source_ref"] for chunk in result.chunks] == ["page:1", "page:2"]
    assert all(chunk["source_id"] == result.source_id for chunk in result.chunks)
