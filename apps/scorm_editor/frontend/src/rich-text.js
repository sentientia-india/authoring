// Client-side companion to src/course_mcp_server/html_sanitizer.py.
//
// This is a courtesy/UX pass, NOT the security boundary: the server
// (course_schema_v2.py's ContentBlock validator, and again defensively in
// exporters/scorm.py._normalize_scorm_payload at export time) re-sanitizes
// every text_html value on every write, because it cannot trust that Course
// Studio was the only thing that ever wrote the field. Running the same
// small allowlist here just keeps what the editor sends already clean and
// lets the UI derive a plain-text `text` value optimistically without a
// server round trip.
//
// Pure string parsing (no DOM APIs) so this runs identically in the browser
// bundle and under vitest's default node environment.

export const ALLOWED_TAGS = new Set(["strong", "em", "u", "a", "ul", "ol", "li"]);

// Tags whose end (or presence, for <br>) should introduce a word boundary
// when projecting rich text down to plain text.
var BLOCK_LIKE_END_TAGS = new Set(["li", "ul", "ol", "p", "div"]);

var TAG_RE = /<(\/?)([a-zA-Z][a-zA-Z0-9]*)((?:\s+[a-zA-Z_:][-a-zA-Z0-9_:.]*(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+))?)*)\s*(\/?)>/g;
var ATTR_RE = /([a-zA-Z_:][-a-zA-Z0-9_:.]*)(?:\s*=\s*("([^"]*)"|'([^']*)'|[^\s>]+))?/g;

function parseAttrs(attrString) {
  var attrs = {};
  var match;
  ATTR_RE.lastIndex = 0;
  while ((match = ATTR_RE.exec(attrString || ""))) {
    var name = match[1].toLowerCase();
    var value = match[3] !== undefined ? match[3] : match[4] !== undefined ? match[4] : match[2] || "";
    attrs[name] = value;
  }
  return attrs;
}

function escapeAttr(value) {
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/**
 * Strip every tag/attribute outside ALLOWED_TAGS from an HTML fragment.
 * Disallowed tags are removed but their text content is kept. Only
 * `<a href="http(s)://...">` / `<a href="mailto:...">` survive as links;
 * text between tags is passed through unmodified (Tiptap already produces
 * well-formed, correctly-escaped HTML — this only filters structure).
 */
// Tags whose entire text content must be discarded, not just the tag itself
// (a stripped-tag-keeps-text rule would otherwise leak raw script/style source).
var SUPPRESS_CONTENT_TAGS = new Set(["script", "style"]);

export function sanitizeRichTextHtml(html) {
  var input = String(html == null ? "" : html);
  var out = [];
  var stack = [];
  var suppressTag = null;
  var lastIndex = 0;
  var match;
  TAG_RE.lastIndex = 0;
  while ((match = TAG_RE.exec(input))) {
    var textBefore = match.index > lastIndex ? input.slice(lastIndex, match.index) : "";
    lastIndex = TAG_RE.lastIndex;
    var isEnd = match[1] === "/";
    var tag = match[2].toLowerCase();
    var selfClosing = match[4] === "/";

    if (suppressTag) {
      if (isEnd && tag === suppressTag) suppressTag = null;
      continue; // swallow both the tag and any text while inside script/style
    }
    if (textBefore) out.push(textBefore);
    if (!isEnd && SUPPRESS_CONTENT_TAGS.has(tag) && !selfClosing) {
      suppressTag = tag;
      continue;
    }
    if (!ALLOWED_TAGS.has(tag)) continue;
    if (isEnd) {
      if (stack.indexOf(tag) === -1) continue;
      while (stack.length && stack[stack.length - 1] !== tag) out.push("</" + stack.pop() + ">");
      if (stack.length) {
        stack.pop();
        out.push("</" + tag + ">");
      }
      continue;
    }
    if (tag === "a") {
      var attrs = parseAttrs(match[3]);
      var href = (attrs.href || "").trim();
      if (!/^(https?:|mailto:)/i.test(href)) continue; // no safe href: drop tag, keep text
      out.push('<a href="' + escapeAttr(href) + '" rel="noopener noreferrer" target="_blank">');
      if (!selfClosing) stack.push(tag);
      continue;
    }
    out.push("<" + tag + ">");
    if (!selfClosing) stack.push(tag);
  }
  if (!suppressTag && lastIndex < input.length) out.push(input.slice(lastIndex));
  while (stack.length) out.push("</" + stack.pop() + ">");
  return out.join("");
}

/**
 * Plain-text projection of a (sanitized or unsanitized) HTML fragment,
 * whitespace-normalized. Mirrors html_sanitizer.strip_tags_to_text so the
 * editor can keep `block.text` in sync with `block.text_html` client-side.
 */
export function richTextToPlainText(html) {
  var input = String(html == null ? "" : html);
  var text = input.replace(/<br\s*\/?>/gi, " ");
  text = text.replace(/<\/([a-zA-Z0-9]+)>/g, function (full, tag) {
    return BLOCK_LIKE_END_TAGS.has(tag.toLowerCase()) ? " " : "";
  });
  text = text.replace(/<[^>]*>/g, "");
  text = text
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'");
  return text.replace(/\s+/g, " ").trim();
}
