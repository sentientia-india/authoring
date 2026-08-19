// Pure helper extracted from editor.js so the drag-and-drop upload routing decision can be
// unit tested without a DOM (this repo's vitest has no jsdom environment configured -- see
// move-item.js for the same pattern). Given a dropped file's name, decides which upload
// endpoint it belongs to and, for source documents, which source_type the server's
// course_mcp_server.ingestion.extract_source() should use.
export var MEDIA_UPLOAD_EXTENSIONS = [".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif", ".mp4", ".webm", ".mp3"];

export var SOURCE_UPLOAD_EXTENSIONS = { ".pdf": "pdf", ".docx": "docx", ".pptx": "pptx", ".ppt": "ppt" };

function extensionOf(filename) {
  var name = String(filename || "");
  var dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

// Returns { kind: "media" | "source" | null, extension, sourceType? }.
// kind "media" -> POST /api/media/<sid>. kind "source" -> POST /api/sources/<sid>/upload
// with sourceType passed through so the caller can surface it in error/status messages.
// kind null -> unsupported extension for either upload surface.
export function routeDroppedFile(filename) {
  var extension = extensionOf(filename);
  if (MEDIA_UPLOAD_EXTENSIONS.indexOf(extension) >= 0) {
    return { kind: "media", extension: extension };
  }
  var sourceType = SOURCE_UPLOAD_EXTENSIONS[extension];
  if (sourceType) {
    return { kind: "source", extension: extension, sourceType: sourceType };
  }
  return { kind: null, extension: extension };
}
