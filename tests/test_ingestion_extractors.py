from zipfile import ZipFile

import course_mcp_server.ingestion as ingestion

from course_mcp_server.ingestion import extract_source


def test_docx_extraction_reads_headings_and_body_text(tmp_path):
    docx = tmp_path / "policy.docx"
    with ZipFile(docx, "w") as package:
        package.writestr(
            "word/document.xml",
            """
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body>
                <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Safety Policy</w:t></w:r></w:p>
                <w:p><w:r><w:t>Inspect equipment before use.</w:t></w:r></w:p>
              </w:body>
            </w:document>
            """,
        )

    result = extract_source(docx, "docx")

    assert "Safety Policy" in result.text
    assert "Inspect equipment" in result.text
    assert result.headings == ["Safety Policy"]
    assert result.references == ["section:Safety Policy"]


def test_pptx_extraction_reads_slide_order_and_notes(tmp_path):
    pptx = tmp_path / "deck.pptx"
    with ZipFile(pptx, "w") as package:
        package.writestr(
            "ppt/slides/slide1.xml",
            """
            <p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
              xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
              <p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Slide Title</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld>
            </p:sld>
            """,
        )
        package.writestr(
            "ppt/notesSlides/notesSlide1.xml",
            """
            <p:notes xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
              xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
              <p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Speaker note</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld>
            </p:notes>
            """,
        )

    result = extract_source(pptx, "pptx")

    assert "Slide 1: Slide Title" in result.text
    assert "Notes 1: Speaker note" in result.text
    assert result.references == ["slide:1", "notes:1"]


def test_youtube_transcript_import_requires_controlled_text_file(tmp_path):
    transcript = tmp_path / "video.txt"
    transcript.write_text("00:00 Welcome\n00:12 First safety rule", encoding="utf-8")

    result = extract_source(transcript, "youtube")

    assert "First safety rule" in result.text
    assert result.references == ["timestamp:00:00", "timestamp:00:12"]


def test_pdf_extraction_reports_page_markers_from_text_pdf(tmp_path):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4\nBT (Page One) Tj ET\n%%Page: 2 2\nBT (Page Two) Tj ET")

    result = extract_source(pdf, "pdf")

    assert "Page One" in result.text
    assert "Page Two" in result.text
    assert "page:1" in result.references


def test_pdf_extraction_uses_page_aware_pypdf(monkeypatch, tmp_path):
    pdf = tmp_path / "thirty-pages.pdf"
    pdf.write_bytes(b"%PDF-1.4 test fixture")

    class Page:
        def __init__(self, number):
            self.number = number

        def extract_text(self):
            return f"Policy page {self.number} — café safety"

    class Reader:
        def __init__(self, _path):
            self.pages = [Page(number) for number in range(1, 31)]

    import pypdf

    monkeypatch.setattr(pypdf, "PdfReader", Reader)
    result = ingestion.extract_source(pdf, "pdf")

    assert "[page 1]" in result.text
    assert "[page 30]" in result.text
    assert "café safety" in result.text
    assert result.references == [f"page:{number}" for number in range(1, 31)]
    assert result.warnings == []
