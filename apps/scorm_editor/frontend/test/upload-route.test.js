import { describe, expect, it } from "vitest";
import { routeDroppedFile } from "../src/upload-route.js";

describe("routeDroppedFile", () => {
  it("routes an image file to the media upload target", () => {
    expect(routeDroppedFile("diagram.png")).toEqual({ kind: "media", extension: ".png" });
  });

  it("routes a video file to the media upload target", () => {
    expect(routeDroppedFile("clip.mp4")).toEqual({ kind: "media", extension: ".mp4" });
  });

  it("routes a PDF to the source upload target with source_type pdf", () => {
    expect(routeDroppedFile("handbook.pdf")).toEqual({ kind: "source", extension: ".pdf", sourceType: "pdf" });
  });

  it("routes a DOCX to the source upload target with source_type docx", () => {
    expect(routeDroppedFile("notes.docx")).toEqual({ kind: "source", extension: ".docx", sourceType: "docx" });
  });

  it("routes a PPTX to the source upload target with source_type pptx", () => {
    expect(routeDroppedFile("deck.pptx")).toEqual({ kind: "source", extension: ".pptx", sourceType: "pptx" });
  });

  it("routes a legacy PPT to the source upload target with source_type ppt", () => {
    expect(routeDroppedFile("old-deck.ppt")).toEqual({ kind: "source", extension: ".ppt", sourceType: "ppt" });
  });

  it("is case-insensitive on extension", () => {
    expect(routeDroppedFile("Handbook.PDF")).toEqual({ kind: "source", extension: ".pdf", sourceType: "pdf" });
  });

  it("returns a null kind for an unsupported extension", () => {
    expect(routeDroppedFile("archive.zip")).toEqual({ kind: null, extension: ".zip" });
  });

  it("returns a null kind and empty extension for a file with no extension", () => {
    expect(routeDroppedFile("README")).toEqual({ kind: null, extension: "" });
  });

  it("returns a null kind for empty or missing input", () => {
    expect(routeDroppedFile("")).toEqual({ kind: null, extension: "" });
    expect(routeDroppedFile(undefined)).toEqual({ kind: null, extension: "" });
  });

  it("uses the final extension for a filename with multiple dots", () => {
    expect(routeDroppedFile("annual.report.v2.pdf")).toEqual({ kind: "source", extension: ".pdf", sourceType: "pdf" });
  });
});
