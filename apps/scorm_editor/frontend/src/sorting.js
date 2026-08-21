// Pure helpers for the "sorting" (ranking) activity type (P5-4d). These mirror
// the shuffle / order-comparison logic embedded in the exported SCORM player's
// renderSortingActivity() (src/course_mcp_server/exporters/scorm.py) closely
// enough to unit test the *shape* of that logic, without duplicating the
// DOM-rendering half of that function (which only exists inside the exported
// player's own JS string and isn't reachable from this frontend bundle) --
// same split as fill-blank.js already documents for renderFillBlankActivity.
//
// Data-shape contract (documented here, and in scorm.py's renderSortingActivity):
//  - The AUTHOR-DEFINED order of activity.items IS the correct order -- there
//    is no separate "correct_order" field. The learner is shown the items in
//    a shuffled order and must reorder them back to positions [0, 1, 2, ...].
//  - Internally, "order" arrays hold the ORIGINAL INDICES of activity.items
//    (not the item objects/text themselves), so items with duplicate display
//    text are still compared/ordered unambiguously.

// Fisher-Yates shuffle of `list` using an injectable random source (defaults
// to Math.random) so callers -- and tests -- can supply a deterministic
// sequence instead of relying on real randomness. If the shuffle happens to
// land back on the original order (a real possibility for short lists, e.g.
// 1-in-6 for 3 items), the result is reversed as a guaranteed-different
// fallback -- an unshuffled-looking start would silently make the activity
// trivial, which is exactly the failure mode this guards against.
export function shuffleItems(list, randomSource) {
  const rng = typeof randomSource === "function" ? randomSource : Math.random;
  if (!Array.isArray(list) || list.length < 2) {
    return Array.isArray(list) ? list.slice() : [];
  }
  const shuffled = list.slice();
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    const tmp = shuffled[i];
    shuffled[i] = shuffled[j];
    shuffled[j] = tmp;
  }
  const unchanged = shuffled.every((value, index) => value === list[index]);
  if (unchanged) shuffled.reverse();
  return shuffled;
}

// Element-wise equality of two order arrays (e.g. index arrays). Used both to
// decide full completion (every position correct) and, per-position, to
// highlight which rows are out of place.
export function isOrderCorrect(currentOrder, correctOrder) {
  if (!Array.isArray(currentOrder) || !Array.isArray(correctOrder)) return false;
  if (currentOrder.length !== correctOrder.length) return false;
  return currentOrder.every((value, index) => value === correctOrder[index]);
}
