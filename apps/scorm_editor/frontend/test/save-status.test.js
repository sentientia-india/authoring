import { describe, expect, it } from "vitest";
import { initialSaveStatus, saveStatusReducer, formatRelativeTime, formatSaveStatus } from "../src/save-status.js";

describe("save-status reducer", () => {
  it("starts idle / Ready", () => {
    const state = initialSaveStatus();
    expect(state.phase).toBe("idle");
    expect(formatSaveStatus(state, Date.now())).toEqual({ text: "Ready", showRetry: false });
  });

  it("moves to saving on a saving event", () => {
    const state = saveStatusReducer(initialSaveStatus(), { type: "saving" });
    expect(state.phase).toBe("saving");
    expect(formatSaveStatus(state, Date.now())).toEqual({ text: "Saving…", showRetry: false });
  });

  it("clears a prior error when a new save starts", () => {
    let state = saveStatusReducer(initialSaveStatus(), { type: "failure", reason: "network down" });
    expect(state.error).toBe("network down");
    state = saveStatusReducer(state, { type: "saving" });
    expect(state.error).toBeNull();
  });

  it("records success with a timestamp and version", () => {
    const state = saveStatusReducer(initialSaveStatus(), { type: "success", version: 7, at: 1000 });
    expect(state).toEqual({ phase: "saved", lastSavedAt: 1000, version: 7, error: null });
  });

  it("records failure with a retry affordance", () => {
    const state = saveStatusReducer(initialSaveStatus(), { type: "failure", reason: "HTTP 500" });
    expect(state.phase).toBe("failed");
    expect(formatSaveStatus(state, Date.now())).toEqual({ text: "Save failed — HTTP 500", showRetry: true });
  });

  it("defaults the failure reason when none is given", () => {
    const state = saveStatusReducer(initialSaveStatus(), { type: "failure" });
    expect(formatSaveStatus(state, Date.now())).toEqual({ text: "Save failed — Save failed", showRetry: true });
  });

  it("records a blocked state (409/410) without a retry affordance", () => {
    const state = saveStatusReducer(initialSaveStatus(), { type: "blocked", reason: "Conflict · reload required" });
    expect(state.phase).toBe("blocked");
    expect(formatSaveStatus(state, Date.now())).toEqual({ text: "Conflict · reload required", showRetry: false });
  });

  it("ignores unknown event types", () => {
    const state = initialSaveStatus();
    expect(saveStatusReducer(state, { type: "nonsense" })).toBe(state);
  });
});

describe("formatRelativeTime", () => {
  it("says 'just now' for anything under 10 seconds", () => {
    expect(formatRelativeTime(1000, 1000)).toBe("just now");
    expect(formatRelativeTime(1000, 9500)).toBe("just now");
  });

  it("counts seconds between 10s and 1 minute", () => {
    expect(formatRelativeTime(0, 15000)).toBe("15 seconds ago");
    expect(formatRelativeTime(0, 59000)).toBe("59 seconds ago");
  });

  it("counts minutes, singular and plural", () => {
    expect(formatRelativeTime(0, 60000)).toBe("1 minute ago");
    expect(formatRelativeTime(0, 2 * 60000)).toBe("2 minutes ago");
    expect(formatRelativeTime(0, 59 * 60000)).toBe("59 minutes ago");
  });

  it("counts hours, singular and plural", () => {
    expect(formatRelativeTime(0, 60 * 60000)).toBe("1 hour ago");
    expect(formatRelativeTime(0, 3 * 60 * 60000)).toBe("3 hours ago");
  });

  it("never goes negative when clock skew makes 'now' earlier than 'from'", () => {
    expect(formatRelativeTime(5000, 1000)).toBe("just now");
  });
});

describe("formatSaveStatus", () => {
  it("shows a relative-time hint for a saved state", () => {
    const state = { phase: "saved", lastSavedAt: 0, version: 3, error: null };
    expect(formatSaveStatus(state, 60000)).toEqual({ text: "Saved 1 minute ago", showRetry: false });
  });

  it("falls back to Ready if saved phase is missing a timestamp", () => {
    const state = { phase: "saved", lastSavedAt: null, version: null, error: null };
    expect(formatSaveStatus(state, Date.now())).toEqual({ text: "Ready", showRetry: false });
  });
});
