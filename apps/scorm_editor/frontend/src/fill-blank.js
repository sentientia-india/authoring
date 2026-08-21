// Pure helpers for the "fill_blank" activity type (P5-4b). These mirror the
// blank-counting / answer-normalizing logic embedded in the exported SCORM
// player's renderFillBlankActivity() (src/course_mcp_server/exporters/scorm.py)
// closely enough to unit test the *shape* of the data Course Studio produces,
// without duplicating the DOM-rendering half of that function (which only
// exists inside the exported player's own JS string and isn't reachable from
// this frontend bundle).
//
// Data-shape contract (documented here, and in scorm.py's renderFillBlankActivity):
//  - activity.text: a string containing one or more literal "{{blank}}" tokens.
//  - activity.blanks: an array, one entry per "{{blank}}" occurrence in text
//    order. Each entry's accepted answers are given either as a real array
//    (`{ answers: ["Paris", "paris, France"] }`) or -- since Course Studio's
//    inspector edits it as a single text field -- a comma-separated string
//    (`{ answers: "Paris, capital of France" }`). `{ answer: "Paris" }`
//    (singular) is also accepted as a one-answer shorthand.
//  - Comparison is case-insensitive and trims whitespace on both the accepted
//    answer(s) and the learner's input.

export function countBlankTokens(text) {
  if (!text) return 0;
  const matches = String(text).match(/\{\{blank\}\}/g);
  return matches ? matches.length : 0;
}

export function normalizeAnswers(raw) {
  const list = Array.isArray(raw) ? raw : String(raw ?? "").split(",");
  return list
    .filter((entry) => entry !== undefined && entry !== null)
    .map((entry) => String(entry).trim().toLowerCase())
    .filter(Boolean);
}

export function isAnswerAccepted(value, raw) {
  const accepted = normalizeAnswers(raw);
  const normalizedValue = String(value ?? "").trim().toLowerCase();
  return accepted.length ? accepted.includes(normalizedValue) : false;
}
