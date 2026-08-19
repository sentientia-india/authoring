from zipfile import ZipFile

import pytest
from pydantic import ValidationError

from course_mcp_server.course_schema_v2 import ContentBlock
from course_mcp_server.exporters.scorm import build_scorm_package
from course_mcp_server.html_sanitizer import sanitize_html_fragment, strip_tags_to_text
from course_mcp_server.schemas import ScormPackageRequest


# ---------------------------------------------------------------------------
# html_sanitizer.py — pure function coverage
# ---------------------------------------------------------------------------


def test_sanitize_html_fragment_keeps_allowlisted_tags():
    html = "<p><strong>Bold</strong> and <em>italic</em> and <u>underline</u></p>"
    assert sanitize_html_fragment(html) == "<strong>Bold</strong> and <em>italic</em> and <u>underline</u>"


def test_sanitize_html_fragment_unwraps_paragraph_but_keeps_formatting():
    html = "<p>Hello <strong>world</strong></p>"
    assert sanitize_html_fragment(html) == "Hello <strong>world</strong>"


def test_sanitize_html_fragment_keeps_safe_link_and_adds_safety_attrs():
    html = '<a href="https://example.com">go</a>'
    assert sanitize_html_fragment(html) == (
        '<a href="https://example.com" rel="noopener noreferrer" target="_blank">go</a>'
    )


def test_sanitize_html_fragment_drops_unsafe_href_but_keeps_text():
    html = '<a href="javascript:alert(1)">click</a>'
    assert sanitize_html_fragment(html) == "click"


def test_sanitize_html_fragment_strips_script_and_its_text():
    html = "<script>alert(1)</script>Hello"
    assert sanitize_html_fragment(html) == "Hello"


def test_sanitize_html_fragment_strips_disallowed_tags_but_keeps_text():
    html = '<img src=x onerror=alert(1)>Hello<div class="x">World</div>'
    assert sanitize_html_fragment(html) == "HelloWorld"


def test_sanitize_html_fragment_keeps_lists():
    html = "<ul><li>one</li><li>two</li></ul>"
    assert sanitize_html_fragment(html) == "<ul><li>one</li><li>two</li></ul>"


def test_sanitize_html_fragment_handles_empty_input():
    assert sanitize_html_fragment(None) == ""
    assert sanitize_html_fragment("") == ""


def test_strip_tags_to_text_produces_plain_text_with_boundaries():
    html = "<ul><li>one</li><li>two</li></ul>"
    assert strip_tags_to_text(html) == "one two"


def test_strip_tags_to_text_handles_empty_input():
    assert strip_tags_to_text(None) == ""


# ---------------------------------------------------------------------------
# course_schema_v2.py — ContentBlock schema validation
# ---------------------------------------------------------------------------


def test_content_block_text_html_round_trips_and_syncs_plain_text():
    block = ContentBlock(
        id="cb_1",
        type="explanation",
        text="placeholder",
        text_html="<p>Use <strong>strong</strong> caution and <a href=\"https://example.com\">read this</a>.</p>",
    )
    assert block.text_html == 'Use <strong>strong</strong> caution and <a href="https://example.com" rel="noopener noreferrer" target="_blank">read this</a>.'
    assert block.text == "Use strong caution and read this."


def test_content_block_strips_disallowed_tags_from_text_html():
    block = ContentBlock(
        id="cb_2",
        type="explanation",
        text="placeholder",
        text_html='<script>alert(1)</script><div onclick="x()">Careful <em>here</em></div>',
    )
    assert "<script" not in block.text_html
    assert "onclick" not in block.text_html
    assert block.text_html == "Careful <em>here</em>"
    assert block.text == "Careful here"


def test_content_block_without_text_html_is_unaffected():
    block = ContentBlock(id="cb_3", type="explanation", text="Plain text only.")
    assert block.text_html is None
    assert block.text == "Plain text only."


def test_content_block_text_html_that_sanitizes_to_nothing_falls_back_to_plain_text():
    block = ContentBlock(
        id="cb_4",
        type="explanation",
        text="Keep this plain text.",
        text_html="<script>alert(1)</script>",
    )
    assert block.text_html is None
    assert block.text == "Keep this plain text."


def test_content_block_text_html_max_length_enforced():
    with pytest.raises(ValidationError):
        ContentBlock(id="cb_5", type="explanation", text="x", text_html="<em>" + "a" * 9000 + "</em>")


# ---------------------------------------------------------------------------
# exporters/scorm.py — export-time rendering + defensive re-sanitization
# ---------------------------------------------------------------------------


def _build(content_blocks, tmp_path):
    return build_scorm_package(
        ScormPackageRequest(
            course_title="Rich Text Course",
            course_slug="rich-text-course",
            modules=[
                {
                    "title": "Module 1",
                    "lessons": [
                        {
                            "title": "Lesson 1",
                            "objective": "Learn formatting",
                            "content_blocks": content_blocks,
                        }
                    ],
                }
            ],
        ),
        str(tmp_path),
    )


def test_scorm_export_renders_sanitized_text_html_for_learners(tmp_path):
    result = _build(
        [
            {
                "type": "explanation",
                "text": "placeholder",
                "text_html": '<p>Read the <strong>bold</strong> <em>italic</em> <a href="https://example.com">policy</a>.</p>',
            }
        ],
        tmp_path,
    )
    with ZipFile(result["package_path"]) as package:
        course_json = package.read("data/course.json").decode("utf-8")
        player_js = package.read("assets/player.js").decode("utf-8")

    # The rendered HTML actually contains real markup, not an escaped literal.
    assert "<strong>bold</strong>" in course_json
    assert "<em>italic</em>" in course_json
    assert '<a href=\\"https://example.com\\" rel=\\"noopener noreferrer\\" target=\\"_blank\\">policy</a>' in course_json
    assert "&lt;strong&gt;" not in course_json

    # Plain text field stayed in sync for word-count/dedup/etc. consumers.
    assert "Read the bold italic policy." in course_json

    # The player renders block.text_html verbatim (already sanitized) instead
    # of escaping it through the plain-text path.
    assert "block.text_html" in player_js


def test_scorm_export_defensively_strips_unsafe_html_bypassing_the_schema(tmp_path):
    # ScormPackageRequest.modules is `list[dict]` (see schemas.py) — course.json
    # written by Course Studio's autosave never passes through the ContentBlock
    # pydantic model, so a hand-crafted dict with disallowed markup must still
    # be neutralized at export time.
    result = _build(
        [
            {
                "type": "explanation",
                "text": "placeholder",
                "text_html": '<script>alert(1)</script><img src=x onerror=alert(1)><div onclick="x()">Careful <strong>now</strong></div>',
            }
        ],
        tmp_path,
    )
    with ZipFile(result["package_path"]) as package:
        course_json = package.read("data/course.json").decode("utf-8")

    assert "<script" not in course_json
    assert "onerror" not in course_json
    assert "onclick" not in course_json
    assert "alert(1)" not in course_json
    assert "<strong>now</strong>" in course_json
    assert "Careful now" in course_json


def test_scorm_export_falls_back_to_plain_text_when_no_text_html(tmp_path):
    result = _build(
        [{"type": "explanation", "text": "No rich text here."}],
        tmp_path,
    )
    with ZipFile(result["package_path"]) as package:
        course_json = package.read("data/course.json").decode("utf-8")

    assert "No rich text here." in course_json
