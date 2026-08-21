import { afterEach, describe, expect, it, vi } from "vitest";
import {
  CONTENT_BLOCK_TRANSFORMS,
  CONTENT_BLOCK_TRANSFORM_IDS,
  buildContentBlockAiRequest,
  extractRewrittenText,
} from "../src/content-block-ai.js";
import { createUndoStack, pushEntry, undoEntry, canUndo } from "../src/undo-stack.js";

describe("CONTENT_BLOCK_TRANSFORMS", () => {
  it("exposes exactly rewrite/expand/simplify, each with a distinct non-empty system prompt", () => {
    expect(CONTENT_BLOCK_TRANSFORM_IDS).toEqual(["rewrite", "expand", "simplify"]);
    const prompts = CONTENT_BLOCK_TRANSFORM_IDS.map((id) => CONTENT_BLOCK_TRANSFORMS[id].systemPrompt);
    expect(new Set(prompts).size).toBe(3); // all distinct
    prompts.forEach((prompt) => expect(prompt.length).toBeGreaterThan(20));
  });
});

describe("buildContentBlockAiRequest", () => {
  const block = { id: "cb_2", type: "explanation", text: "Original explanation text." };
  const siblings = [
    { id: "cb_1", type: "intro", text: "Intro block text that is reasonably long for an excerpt." },
    block,
    { id: "cb_3", type: "example", text: "Example block text that follows the target block." },
  ];

  it("throws on an unknown transform id", () => {
    expect(() => buildContentBlockAiRequest("translate", block, "Lesson", siblings, {})).toThrow(
      "Unknown content block AI transform"
    );
  });

  it("throws when the block has no text", () => {
    expect(() => buildContentBlockAiRequest("rewrite", { id: "cb_0", type: "intro", text: "" }, "Lesson", [], {})).toThrow(
      "no text to transform"
    );
  });

  it("builds a request with the transform's system prompt, schema_name, and the block's own role/text", () => {
    const body = buildContentBlockAiRequest("expand", block, "Intro to Widgets", siblings, {});
    expect(body.system_prompt).toBe(CONTENT_BLOCK_TRANSFORMS.expand.systemPrompt);
    expect(body.schema_name).toBe("content_block_rewrite");
    expect(body.user_payload.role).toBe("explanation");
    expect(body.user_payload.text).toBe("Original explanation text.");
    expect(body.user_payload.lesson_title).toBe("Intro to Widgets");
  });

  it("includes previous/next sibling block context when present", () => {
    const body = buildContentBlockAiRequest("rewrite", block, "Lesson", siblings, {});
    expect(body.user_payload.previous_block).toEqual({ role: "intro", excerpt: siblings[0].text });
    expect(body.user_payload.next_block).toEqual({ role: "example", excerpt: siblings[2].text });
  });

  it("omits previous/next block context when the block is first/last or alone", () => {
    const body = buildContentBlockAiRequest("rewrite", block, "Lesson", [block], {});
    expect(body.user_payload.previous_block).toBeUndefined();
    expect(body.user_payload.next_block).toBeUndefined();
  });

  it("truncates a long sibling excerpt", () => {
    const longText = "x".repeat(500);
    const localSiblings = [{ id: "cb_1", type: "intro", text: longText }, block];
    const body = buildContentBlockAiRequest("rewrite", block, "Lesson", localSiblings, {});
    expect(body.user_payload.previous_block.excerpt.length).toBeLessThan(200);
    expect(body.user_payload.previous_block.excerpt.endsWith("…")).toBe(true);
  });

  it("spreads in buildAiRequestFields()-style fields untouched (never nested)", () => {
    const aiFields = { text_provider: "openrouter", text_provider_api_key: "sk-live-1" };
    const body = buildContentBlockAiRequest("rewrite", block, "Lesson", siblings, aiFields);
    expect(body.text_provider).toBe("openrouter");
    expect(body.text_provider_api_key).toBe("sk-live-1");
  });
});

describe("extractRewrittenText", () => {
  it("returns the trimmed text on a well-formed result", () => {
    expect(extractRewrittenText({ text: "  Rewritten copy.  " })).toBe("Rewritten copy.");
  });

  it("throws when result is missing/not an object", () => {
    expect(() => extractRewrittenText(null)).toThrow("empty");
    expect(() => extractRewrittenText(undefined)).toThrow("empty");
    expect(() => extractRewrittenText("just a string")).toThrow("empty");
  });

  it("throws when result.text is missing or blank", () => {
    expect(() => extractRewrittenText({})).toThrow("did not include rewritten text");
    expect(() => extractRewrittenText({ text: "   " })).toThrow("did not include rewritten text");
    expect(() => extractRewrittenText({ text: 123 })).toThrow("did not include rewritten text");
  });
});

// ---------------------------------------------------------------------------
// The tests below simulate the exact orchestration editor.js's
// runContentBlockAiTransform() performs against POST /api/ai/<sid>/generate --
// build the request with buildContentBlockAiRequest(), call a (mocked) fetch,
// apply extractRewrittenText()'s result to the target block IN PLACE, and
// push a new undo-stack entry via the same undo-stack.js primitives editor.js
// wires into save()/pushHistory(). editor.js itself is a DOM-bound top-level
// IIFE (reads document.getElementById(...) at import time) with no exported
// entry points, so it cannot be imported into a headless test the way the
// extracted pure modules (ai-settings.js, undo-stack.js, content-block-ai.js)
// can -- this harness instead proves the ALGORITHM those exports are wired
// into inside editor.js: same request builder, same response validator, same
// undo-stack push/undo calls, same in-flight guard shape.
function makeCourse() {
  return {
    course_title: "Course",
    modules: [
      {
        title: "Module 1",
        lessons: [
          {
            title: "Lesson 1",
            content_blocks: [
              { id: "cb_1", type: "intro", text: "Intro text." },
              { id: "cb_2", type: "explanation", text: "Original explanation text." },
              { id: "cb_3", type: "example", text: "Example text." },
            ],
          },
        ],
      },
    ],
  };
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

// Mirrors editor.js: aiBlockRequestInFlight (module-level map), save()'s
// pushHistory() (pushEntry(undoStack, clone(course)) before mutating), and
// runContentBlockAiTransform's guard/apply/finally shape.
function createHarness() {
  const course = makeCourse();
  const undoStack = createUndoStack(50);
  pushEntry(undoStack, clone(course)); // initial state, same as openSession()'s pushHistory()
  const inFlight = {};
  const toasts = [];

  function findBlock(cbId) {
    for (const module of course.modules) {
      for (const lesson of module.lessons) {
        for (const block of lesson.content_blocks) {
          if (block.id === cbId) return { block, lesson };
        }
      }
    }
    return null;
  }

  function run(transformId, cbId, fetchImpl) {
    if (inFlight[cbId]) return Promise.resolve("skipped-in-flight");
    const found = findBlock(cbId);
    const body = buildContentBlockAiRequest(transformId, found.block, found.lesson.title, found.lesson.content_blocks, {});
    inFlight[cbId] = transformId;
    return fetchImpl(body)
      .then((data) => {
        if (!data.ok) throw new Error(data.error || "AI request failed.");
        const text = extractRewrittenText(data.result);
        const stillThere = findBlock(cbId);
        stillThere.block.text = text; // in-place mutation, same field editor.js writes
        pushEntry(undoStack, clone(course)); // save(false)'s pushHistory()
        toasts.push(CONTENT_BLOCK_TRANSFORMS[transformId].label + " applied.");
      })
      .catch((error) => {
        toasts.push(CONTENT_BLOCK_TRANSFORMS[transformId].label + " failed: " + error.message);
      })
      .finally(() => {
        delete inFlight[cbId];
      });
  }

  return { course, undoStack, inFlight, toasts, run, findBlock };
}

describe("content block AI transform orchestration (simulated editor.js flow)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("a successful rewrite replaces only the targeted block's text and pushes a genuine undo entry", async () => {
    const h = createHarness();
    const fetchImpl = () => Promise.resolve({ ok: true, result: { text: "Rewritten explanation text." } });

    await h.run("rewrite", "cb_2", fetchImpl);

    expect(h.findBlock("cb_2").block.text).toBe("Rewritten explanation text.");
    // Sibling blocks are untouched.
    expect(h.findBlock("cb_1").block.text).toBe("Intro text.");
    expect(h.findBlock("cb_3").block.text).toBe("Example text.");

    // Genuinely undoable: use undo-stack.js's own exported undoEntry(), not a DOM assertion.
    expect(canUndo(h.undoStack)).toBe(true);
    const restored = undoEntry(h.undoStack);
    const restoredBlock = restored.modules[0].lessons[0].content_blocks.find((b) => b.id === "cb_2");
    expect(restoredBlock.text).toBe("Original explanation text.");

    expect(h.toasts).toEqual(["Rewrite applied."]);
  });

  it("a failed response (TextProviderError-style 400) leaves the original text untouched and surfaces a visible error, with no undo entry pushed", async () => {
    const h = createHarness();
    const depthBefore = h.undoStack.entries.length;
    const fetchImpl = () => Promise.resolve({ ok: false, error: "No API key configured for provider 'openai'." });

    await h.run("expand", "cb_2", fetchImpl);

    expect(h.findBlock("cb_2").block.text).toBe("Original explanation text.");
    expect(h.undoStack.entries.length).toBe(depthBefore); // no new snapshot pushed on failure
    expect(h.toasts).toEqual(["Expand failed: No API key configured for provider 'openai'."]);
  });

  it("a network error also leaves the original text untouched and surfaces a visible error", async () => {
    const h = createHarness();
    const fetchImpl = () => Promise.reject(new Error("Network request failed"));

    await h.run("simplify", "cb_2", fetchImpl);

    expect(h.findBlock("cb_2").block.text).toBe("Original explanation text.");
    expect(h.toasts).toEqual(["Simplify failed: Network request failed"]);
  });

  it("disables re-firing the same transform on the same block while one is already in flight", async () => {
    const h = createHarness();
    let resolveFetch;
    const fetchImpl = () => new Promise((resolve) => { resolveFetch = resolve; });

    const firstCall = h.run("rewrite", "cb_2", fetchImpl);
    expect(h.inFlight.cb_2).toBe("rewrite");

    // A second click on the same block while the first is still in flight is a no-op.
    const secondCall = await h.run("rewrite", "cb_2", fetchImpl);
    expect(secondCall).toBe("skipped-in-flight");

    resolveFetch({ ok: true, result: { text: "Done." } });
    await firstCall;
    expect(h.inFlight.cb_2).toBeUndefined(); // cleared once settled
    expect(h.findBlock("cb_2").block.text).toBe("Done.");
  });

  it("a different block can still run while another block's transform is in flight", async () => {
    const h = createHarness();
    let resolveFirst;
    const blockedFetch = () => new Promise((resolve) => { resolveFirst = resolve; });
    const immediateFetch = () => Promise.resolve({ ok: true, result: { text: "New intro." } });

    const firstCall = h.run("rewrite", "cb_2", blockedFetch);
    expect(h.inFlight.cb_2).toBe("rewrite");

    await h.run("rewrite", "cb_1", immediateFetch);
    expect(h.findBlock("cb_1").block.text).toBe("New intro.");

    resolveFirst({ ok: true, result: { text: "New explanation." } });
    await firstCall;
  });
});
