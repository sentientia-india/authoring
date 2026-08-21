/* Pure state machine + formatter for the toolbar autosave indicator.
   Course Studio already autosaves on every edit (every mutation in editor.js
   routes through save(), which PUTs to /api/course/<sid> immediately -- see
   the many `save(true)`/`save(false)` call sites). This module does not add
   a new persistence mechanism; it only tracks what the real save() calls
   report (in-flight / success / failure) so the UI can show it honestly,
   including a relative-time hint on success and a retry affordance on
   failure. Kept DOM-free and dependency-free so it is trivially unit-tested. */

export function initialSaveStatus() {
  return { phase: "idle", lastSavedAt: null, version: null, error: null };
}

/* Events:
   { type: "saving" }
   { type: "success", version, at }
   { type: "failure", reason, at }   -- network error / non-ok response
   { type: "blocked", reason }       -- 409 conflict / 410 expired: a banner
                                         already tells the user to reload, so
                                         this is tracked separately from a
                                         retryable "failure". */
export function saveStatusReducer(state, event) {
  switch (event.type) {
    case "saving":
      return Object.assign({}, state, { phase: "saving", error: null });
    case "success":
      return { phase: "saved", lastSavedAt: event.at, version: event.version, error: null };
    case "failure":
      return Object.assign({}, state, { phase: "failed", error: event.reason || "Save failed" });
    case "blocked":
      return Object.assign({}, state, { phase: "blocked", error: event.reason || "Save blocked" });
    default:
      return state;
  }
}

export function formatRelativeTime(fromMs, nowMs) {
  var deltaSeconds = Math.max(0, Math.round((nowMs - fromMs) / 1000));
  if (deltaSeconds < 10) return "just now";
  if (deltaSeconds < 60) return deltaSeconds + " seconds ago";
  var minutes = Math.round(deltaSeconds / 60);
  if (minutes < 60) return minutes + " minute" + (minutes === 1 ? "" : "s") + " ago";
  var hours = Math.round(minutes / 60);
  return hours + " hour" + (hours === 1 ? "" : "s") + " ago";
}

/* Returns { text, showRetry } describing how the indicator should render
   right now. `nowMs` is passed in (rather than read from Date.now() here)
   so callers can re-render on a coarse interval and so this stays pure. */
export function formatSaveStatus(state, nowMs) {
  if (state.phase === "saving") return { text: "Saving…", showRetry: false };
  if (state.phase === "failed") {
    var suffix = state.error ? " — " + state.error : "";
    return { text: "Save failed" + suffix, showRetry: true };
  }
  if (state.phase === "blocked") return { text: state.error || "Save blocked", showRetry: false };
  if (state.phase === "saved" && state.lastSavedAt != null) {
    return { text: "Saved " + formatRelativeTime(state.lastSavedAt, nowMs), showRetry: false };
  }
  return { text: "Ready", showRetry: false };
}
