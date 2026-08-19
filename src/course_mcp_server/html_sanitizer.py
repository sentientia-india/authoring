"""Allowlist HTML sanitizer for rich-text content blocks.

`ContentBlock.text_html` (see course_schema_v2.py) is the only place raw markup
is allowed to flow through the system. Everything downstream of it — the SCORM
exporter, the Adapt exporter, word-count/quality-gate heuristics, image-prompt
extraction — either expects plain text or expects HTML limited to a small,
known-safe set of tags. This module is the single choke point that enforces
that: any tag/attribute outside the allowlist is dropped (its text content is
kept), so nothing downstream ever sees markup it doesn't understand.

Used both where `text_html` is written (schema validation) and, defensively,
again at export time — the Course Studio editor's autosave path persists
course.json directly without going through the pydantic model, so the
exporter cannot assume the field was ever sanitized.
"""

from __future__ import annotations

from html.parser import HTMLParser

# The only tags Course Studio's Tiptap editor is configured to produce, and the
# only tags the SCORM/Adapt exporters know how to render. Keep these two lists
# (this allowlist and the Tiptap extension set in editor.js) in sync.
ALLOWED_TAGS = frozenset({"strong", "em", "u", "a", "ul", "ol", "li"})

# Tags whose entire text content must be discarded, not just the tag itself
# (a stripped-tag-keeps-text rule would otherwise leak raw script/style source
# into the plain-text `text` field that word counts/dedup/image prompts read).
_SUPPRESS_CONTENT_TAGS = frozenset({"script", "style"})

# Tags whose end-tag should introduce a word boundary when projecting to plain text.
_BLOCK_LIKE_TAGS = frozenset({"li", "ul", "ol", "p", "div", "br"})


def _escape_text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_attr(value: str) -> str:
    return _escape_text(value).replace('"', "&quot;")


class _AllowlistSanitizer(HTMLParser):
    """Rebuilds an HTML fragment keeping only allowlisted tags/attributes."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []
        self._open_stack: list[str] = []
        self._suppress_tag: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._emit_start(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._emit_start(tag, attrs, self_closing=True)

    def _emit_start(self, tag: str, attrs: list[tuple[str, str | None]], *, self_closing: bool) -> None:
        tag = tag.lower()
        if self._suppress_tag:
            return
        if tag in _SUPPRESS_CONTENT_TAGS and not self_closing:
            self._suppress_tag = tag
            return
        if tag not in ALLOWED_TAGS:
            return
        if tag == "a":
            href = ""
            for name, value in attrs:
                if name.lower() == "href" and value:
                    candidate = value.strip()
                    if candidate.lower().startswith(("http://", "https://", "mailto:")):
                        href = candidate
            if not href:
                # No safe href: drop the tag itself but keep its text content.
                return
            self._out.append(f'<a href="{_escape_attr(href)}" rel="noopener noreferrer" target="_blank">')
            if not self_closing:
                self._open_stack.append(tag)
            return
        self._out.append(f"<{tag}>")
        if not self_closing:
            self._open_stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._suppress_tag:
            if tag == self._suppress_tag:
                self._suppress_tag = None
            return
        if tag not in ALLOWED_TAGS or tag not in self._open_stack:
            return
        while self._open_stack and self._open_stack[-1] != tag:
            closed = self._open_stack.pop()
            self._out.append(f"</{closed}>")
        if self._open_stack:
            self._open_stack.pop()
            self._out.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._suppress_tag:
            return
        self._out.append(_escape_text(data))

    def close_all_open_tags(self) -> None:
        while self._open_stack:
            tag = self._open_stack.pop()
            self._out.append(f"</{tag}>")

    def get_html(self) -> str:
        return "".join(self._out)


def sanitize_html_fragment(html: str | None) -> str:
    """Strip every tag/attribute outside ALLOWED_TAGS from an HTML fragment.

    Disallowed tags are removed but their text content is preserved. Only
    `<a href="http(s)://...">` and `<a href="mailto:...">` survive as links;
    an `<a>` with any other/missing href is dropped (text kept). Returns ""
    for falsy input.
    """
    if not html:
        return ""
    parser = _AllowlistSanitizer()
    parser.feed(html)
    parser.close()
    parser.close_all_open_tags()
    return parser.get_html()


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in _BLOCK_LIKE_TAGS:
            self.parts.append(" ")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "br":
            self.parts.append(" ")


def sanitize_content_block_dict(block: dict) -> None:
    """Sanitize a single content-block dict's `text_html` in place, keeping
    `text` in sync. Shared by every write path that can persist course JSON
    without going through the ContentBlock pydantic model: Course Studio's
    autosave (apps/scorm_editor/server.py `save_course`) and the SCORM
    exporter's defensive re-pass (exporters/scorm.py `_normalize_scorm_payload`).
    """
    text_html = block.get("text_html")
    if not text_html or not isinstance(text_html, str):
        block["text_html"] = None
        return
    sanitized = sanitize_html_fragment(text_html)
    plain = strip_tags_to_text(sanitized)
    if not plain:
        block["text_html"] = None
        return
    block["text_html"] = sanitized
    block["text"] = plain[:6000]


def sanitize_course_rich_text(course: dict) -> None:
    """Walk a full course dict and sanitize every content block's `text_html`
    in place. Safe to call on any shape of course dict (missing/malformed
    modules, lessons, or content_blocks are silently skipped).
    """
    if not isinstance(course, dict):
        return
    for module in course.get("modules") or []:
        if not isinstance(module, dict):
            continue
        for lesson in module.get("lessons") or []:
            if not isinstance(lesson, dict):
                continue
            for block in lesson.get("content_blocks") or []:
                if isinstance(block, dict):
                    sanitize_content_block_dict(block)


def strip_tags_to_text(html: str | None) -> str:
    """Plain-text projection of an HTML fragment, whitespace-normalized.

    Used to keep `ContentBlock.text` (the plain-text canonical field every
    other consumer reads) in sync with `text_html` whenever the latter is set.
    """
    if not html:
        return ""
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return " ".join("".join(parser.parts).split()).strip()
