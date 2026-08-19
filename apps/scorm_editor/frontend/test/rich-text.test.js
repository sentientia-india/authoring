import { describe, expect, it } from "vitest";
import { sanitizeRichTextHtml, richTextToPlainText } from "../src/rich-text.js";

describe("sanitizeRichTextHtml", () => {
  it("keeps allowlisted formatting tags", () => {
    expect(sanitizeRichTextHtml("<p><strong>Bold</strong> and <em>italic</em> and <u>underline</u></p>")).toBe(
      "<strong>Bold</strong> and <em>italic</em> and <u>underline</u>"
    );
  });

  it("keeps a safe https link and adds rel/target", () => {
    expect(sanitizeRichTextHtml('<a href="https://example.com">go</a>')).toBe(
      '<a href="https://example.com" rel="noopener noreferrer" target="_blank">go</a>'
    );
  });

  it("keeps a safe mailto link", () => {
    expect(sanitizeRichTextHtml('<a href="mailto:a@b.com">mail</a>')).toBe(
      '<a href="mailto:a@b.com" rel="noopener noreferrer" target="_blank">mail</a>'
    );
  });

  it("drops a link with a javascript: href but keeps its text", () => {
    expect(sanitizeRichTextHtml('<a href="javascript:alert(1)">click</a>')).toBe("click");
  });

  it("drops a link with no href but keeps its text", () => {
    expect(sanitizeRichTextHtml("<a>click</a>")).toBe("click");
  });

  it("keeps bullet lists", () => {
    expect(sanitizeRichTextHtml("<ul><li>one</li><li>two</li></ul>")).toBe("<ul><li>one</li><li>two</li></ul>");
  });

  it("keeps ordered lists", () => {
    expect(sanitizeRichTextHtml("<ol><li>one</li></ol>")).toBe("<ol><li>one</li></ol>");
  });

  it("strips disallowed tags but keeps their text content", () => {
    expect(sanitizeRichTextHtml('<script>alert(1)</script><img src=x onerror=alert(1)>Hello<div class="x">World</div>')).toBe(
      "HelloWorld"
    );
  });

  it("strips style/on* attributes even on an allowed tag", () => {
    expect(sanitizeRichTextHtml('<strong style="color:red" onclick="alert(1)">Bold</strong>')).toBe("<strong>Bold</strong>");
  });

  it("unwraps paragraph tags Tiptap produces by default", () => {
    expect(sanitizeRichTextHtml("<p>Hello <strong>world</strong></p>")).toBe("Hello <strong>world</strong>");
  });

  it("closes unclosed tags", () => {
    expect(sanitizeRichTextHtml("<strong>Bold")).toBe("<strong>Bold</strong>");
  });

  it("returns an empty string for null/undefined/empty input", () => {
    expect(sanitizeRichTextHtml(null)).toBe("");
    expect(sanitizeRichTextHtml(undefined)).toBe("");
    expect(sanitizeRichTextHtml("")).toBe("");
  });
});

describe("richTextToPlainText", () => {
  it("strips tags and normalizes whitespace", () => {
    expect(richTextToPlainText("<p><strong>Bold</strong>  and   <em>italic</em></p>")).toBe("Bold and italic");
  });

  it("inserts a boundary between list items", () => {
    expect(richTextToPlainText("<ul><li>one</li><li>two</li></ul>")).toBe("one two");
  });

  it("decodes basic HTML entities", () => {
    expect(richTextToPlainText("Tom &amp; Jerry&#39;s &quot;quote&quot;")).toBe(`Tom & Jerry's "quote"`);
  });

  it("returns an empty string for null/undefined/empty input", () => {
    expect(richTextToPlainText(null)).toBe("");
    expect(richTextToPlainText(undefined)).toBe("");
    expect(richTextToPlainText("")).toBe("");
  });
});
