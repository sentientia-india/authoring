import { describe, expect, it } from "vitest";
import { escapeHtml } from "../src/escape-html.js";

describe("escapeHtml", () => {
  it("escapes the five reserved HTML characters", () => {
    expect(escapeHtml(`<a href="x">Tom & Jerry's "quote"</a>`)).toBe(
      "&lt;a href=&quot;x&quot;&gt;Tom &amp; Jerry&#39;s &quot;quote&quot;&lt;/a&gt;"
    );
  });

  it("returns an empty string for null and undefined", () => {
    expect(escapeHtml(null)).toBe("");
    expect(escapeHtml(undefined)).toBe("");
  });

  it("coerces non-string values to strings", () => {
    expect(escapeHtml(42)).toBe("42");
  });

  it("leaves strings with no reserved characters unchanged", () => {
    expect(escapeHtml("plain text")).toBe("plain text");
  });
});
