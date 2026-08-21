// Pure helpers for the "image_hotspot" activity type (P5-4c). These carry the
// percentage-geometry math out of the inspector's click-drag DOM event handler
// (editor.js's ACTIVITY_INSPECTORS "hotspot" entry) so it can be unit tested
// without a real DOM/mouse.
//
// Data-shape contract (documented here, and in scorm.py's renderHotspotActivity):
//  - activity.image: { src, alt } -- src is an editor-relative media path
//    ("assets/media/xxx.png") produced by the same /api/media/{session} upload
//    flow the existing image content-block media editor uses.
//  - activity.regions: an array of rectangles, each given as PERCENTAGES of the
//    image's own displayed width/height (not pixels, and not percentages of
//    the inspector panel) so a region survives the image being shown at any
//    size -- `{ x_pct, y_pct, width_pct, height_pct, tag, feedback, label }`.
//    `tag` is one of "correct" | "incorrect" | "informational".

// `displayedRect` and `drawnRect` are both DOMRect-shaped ({left, top, width,
// height}) in the same coordinate space (typically both from
// element.getBoundingClientRect() during a mouse drag). Converts the drawn
// rectangle into percentages of the displayed image's own box, clamped to
// [0, 100] and normalized so width/height are never negative (a drag that
// moves left/up of its start point still produces a valid rectangle).
export function computeRegionPercentages(displayedRect, drawnRect) {
  const imgWidth = displayedRect.width || 1;
  const imgHeight = displayedRect.height || 1;

  const left = Math.min(drawnRect.left, drawnRect.left + drawnRect.width);
  const top = Math.min(drawnRect.top, drawnRect.top + drawnRect.height);
  const width = Math.abs(drawnRect.width);
  const height = Math.abs(drawnRect.height);

  const clampPct = (value) => Math.min(100, Math.max(0, value));

  const xPct = clampPct(((left - displayedRect.left) / imgWidth) * 100);
  const yPct = clampPct(((top - displayedRect.top) / imgHeight) * 100);
  // Clamp width/height so the region never extends past the image's right/bottom edge.
  const widthPct = clampPct(Math.min((width / imgWidth) * 100, 100 - xPct));
  const heightPct = clampPct(Math.min((height / imgHeight) * 100, 100 - yPct));

  return { x_pct: xPct, y_pct: yPct, width_pct: widthPct, height_pct: heightPct };
}

// Two mouse points (in the same coordinate space as computeRegionPercentages'
// `displayedRect`) -> the {left, top, width, height} rectangle between them,
// in "raw drag" form (width/height may be negative, matching a drag that
// moved up/left -- computeRegionPercentages normalizes that).
export function rectFromPoints(startPoint, endPoint) {
  return {
    left: startPoint.x,
    top: startPoint.y,
    width: endPoint.x - startPoint.x,
    height: endPoint.y - startPoint.y,
  };
}

// A drawn rectangle only becomes a region if it's a deliberate drag, not a
// stray click -- guards against a plain click on the image creating a
// zero-size (or accidental sliver) region.
export function isRegionSizeUsable(drawnRect, minSizePx) {
  const threshold = minSizePx == null ? 4 : minSizePx;
  return Math.abs(drawnRect.width) >= threshold && Math.abs(drawnRect.height) >= threshold;
}
