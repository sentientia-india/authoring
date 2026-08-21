import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ALT_TEXT_CONTEXT_ONLY_NOTE,
  ALT_TEXT_SYSTEM_PROMPT,
  buildAltTextRequest,
  extractAltText,
} from "../src/alt-text-ai.js";
import { createUndoStack, pushEntry, undoEntry, canUndo } from "../src/undo-stack.js";

describe("ALT_TEXT_SYSTEM_PROMPT / ALT_TEXT_CONTEXT_ONLY_NOTE", () => {
  it("is a non-trivial prompt that tells the model it cannot see the image", () => {
    expect(ALT_TEXT_SYSTEM_PROMPT.length).toBeGreaterThan(20);
    expect(ALT_TEXT_SYSTEM_PROMPT).toMatch(/cannot see the/i);
  });

  it("exposes a user-facing note documenting the text-only, context-based approximation", () => {
    expect(typeof ALT_TEXT_CONTEXT_ONLY_NOTE).toBe("string");
    expect(ALT_TEXT_CONTEXT_ONLY_NOTE.length).toBeGreaterThan(10);
  });
});

describe("buildAltTextRequest", () => {
  const imageBlock = {
    id: "cb_2",
    type: "example",
    text: "This diagram shows the widget assembly steps.",
    media: { kind: "image", src: "assets/media/widget-diagram.png", caption: "Widget assembly", alt: "" },
  };

  it("throws when the block has no image media", () => {
    expect(() => buildAltTextRequest({ id: "cb_1", type: "intro", text: "x" }, "Lesson", {})).toThrow(
      "no image to describe"
    );
    expect(() =>
      buildAltTextRequest({ id: "cb_1", media: { kind: "video", src: "x.mp4" } }, "Lesson", {})
    ).toThrow("no image to describe");
  });

  it("throws when there is no text, caption, or filename to draw context from", () => {
    const bareBlock = { id: "cb_3", type: "example", text: "", media: { kind: "image", src: "", caption: "" } };
    expect(() => buildAltTextRequest(bareBlock, "Lesson", {})).toThrow(
      "Add a caption or some block text"
    );
  });

  it("builds a request with the system prompt, schema_name, and role/text/caption/filename context", () => {
    const body = buildAltTextRequest(imageBlock, "Assembling Widgets", {});
    expect(body.system_prompt).toBe(ALT_TEXT_SYSTEM_PROMPT);
    expect(body.schema_name).toBe("image_alt_text");
    expect(body.user_payload.role).toBe("example");
    expect(body.user_payload.lesson_title).toBe("Assembling Widgets");
    expect(body.user_payload.block_text).toBe("This diagram shows the widget assembly steps.");
    expect(body.user_payload.caption).toBe("Widget assembly");
    expect(body.user_payload.filename).toBe("widget-diagram.png");
  });

  it("parses the filename out of an external URL with a query string", () => {
    const block = {
      id: "cb_4",
      type: "example",
      text: "",
      media: { kind: "image", src: "https://cdn.example.com/imgs/photo.jpg?v=2", caption: "" },
    };
    const body = buildAltTextRequest(block, "Lesson", {});
    expect(body.user_payload.filename).toBe("photo.jpg");
  });

  it("includes current_alt_text only when a non-empty alt already exists", () => {
    const withoutAlt = buildAltTextRequest(imageBlock, "Lesson", {});
    expect(withoutAlt.user_payload.current_alt_text).toBeUndefined();

    const withAlt = buildAltTextRequest(
      { ...imageBlock, media: { ...imageBlock.media, alt: "Old alt text" } },
      "Lesson",
      {}
    );
    expect(withAlt.user_payload.current_alt_text).toBe("Old alt text");
  });

  it("never includes real image bytes/base64 anywhere in the request (text-only approximation)", () => {
    const body = buildAltTextRequest(imageBlock, "Lesson", {});
    const serialized = JSON.stringify(body);
    expect(serialized).not.toMatch(/image_base64|inline_data|data:image/);
  });

  it("spreads in buildAiRequestFields()-style fields untouched (never nested)", () => {
    const aiFields = { text_provider: "anthropic", text_provider_api_key: "sk-live-1" };
    const body = buildAltTextRequest(imageBlock, "Lesson", aiFields);
    expect(body.text_provider).toBe("anthropic");
    expect(body.text_provider_api_key).toBe("sk-live-1");
  });
});

describe("extractAltText", () => {
  it("returns the trimmed alt text on a well-formed result", () => {
    expect(extractAltText({ alt_text: "  A worker assembling a widget.  " })).toBe(
      "A worker assembling a widget."
    );
  });

  it("throws when result is missing/not an object", () => {
    expect(() => extractAltText(null)).toThrow("empty");
    expect(() => extractAltText(undefined)).toThrow("empty");
    expect(() => extractAltText("just a string")).toThrow("empty");
  });

  it("throws when result.alt_text is missing or blank", () => {
    expect(() => extractAltText({})).toThrow("did not include alt text");
    expect(() => extractAltText({ alt_text: "   " })).toThrow("did not include alt text");
    expect(() => extractAltText({ alt_text: 123 })).toThrow("did not include alt text");
  });
});

// ---------------------------------------------------------------------------
// The tests below simulate the exact orchestration editor.js's
// runAltTextAiAction() performs against POST /api/ai/<sid>/generate -- build
// the request with buildAltTextRequest(), call a (mocked) fetch, apply
// extractAltText()'s result to block.media.alt IN PLACE, and push a new
// undo-stack entry via the same undo-stack.js primitives editor.js wires into
// save()/pushHistory(). editor.js itself cannot be imported into a headless
// test (see content-block-ai.test.js's identical note) -- this harness proves
// the algorithm those exports are wired into: same request builder, same
// response validator, same undo-stack push/undo calls, same in-flight guard
// shape, same "confirm before overwriting a non-empty existing alt" gate.
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
              {
                id: "cb_1",
                type: "example",
                text: "A photo of the finished product.",
                media: { kind: "image", src: "assets/media/finished.png", caption: "Finished product", alt: "" },
              },
              {
                id: "cb_2",
                type: "example",
                text: "The wiring diagram for step three.",
                media: { kind: "image", src: "assets/media/wiring.png", caption: "Wiring diagram", alt: "Old alt text" },
              },
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

function createHarness(confirmImpl) {
  const course = makeCourse();
  const undoStack = createUndoStack(50);
  pushEntry(undoStack, clone(course));
  const inFlight = {};
  const toasts = [];
  const confirmFn = confirmImpl || (() => true);

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

  function run(cbId, fetchImpl) {
    if (inFlight[cbId]) return Promise.resolve("skipped-in-flight");
    const found = findBlock(cbId);
    const existingAlt = String((found.block.media && found.block.media.alt) || "").trim();
    if (existingAlt && !confirmFn(existingAlt)) return Promise.resolve("skipped-not-confirmed");

    const body = buildAltTextRequest(found.block, found.lesson.title, {});
    inFlight[cbId] = true;
    return fetchImpl(body)
      .then((data) => {
        if (!data.ok) throw new Error(data.error || "AI request failed.");
        const text = extractAltText(data.result);
        const stillThere = findBlock(cbId);
        stillThere.block.media.alt = text; // in-place mutation, same field editor.js writes
        pushEntry(undoStack, clone(course)); // save(false)'s pushHistory()
        toasts.push("Alt text generated.");
      })
      .catch((error) => {
        toasts.push("Alt text generation failed: " + error.message);
      })
      .finally(() => {
        delete inFlight[cbId];
      });
  }

  return { course, undoStack, inFlight, toasts, run, findBlock };
}

describe("alt text AI action orchestration (simulated editor.js flow)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("a successful generation populates media.alt and pushes a genuine undo entry", async () => {
    const h = createHarness();
    const fetchImpl = () => Promise.resolve({ ok: true, result: { alt_text: "Photo of the finished product." } });

    await h.run("cb_1", fetchImpl);

    expect(h.findBlock("cb_1").block.media.alt).toBe("Photo of the finished product.");
    // Sibling block untouched.
    expect(h.findBlock("cb_2").block.media.alt).toBe("Old alt text");

    expect(canUndo(h.undoStack)).toBe(true);
    const restored = undoEntry(h.undoStack);
    const restoredBlock = restored.modules[0].lessons[0].content_blocks.find((b) => b.id === "cb_1");
    expect(restoredBlock.media.alt).toBe("");

    expect(h.toasts).toEqual(["Alt text generated."]);
  });

  it("a failed response leaves existing alt_text untouched and surfaces a visible error, with no undo entry pushed", async () => {
    const h = createHarness();
    const depthBefore = h.undoStack.entries.length;
    const fetchImpl = () => Promise.resolve({ ok: false, error: "No API key configured for provider 'openai'." });

    await h.run("cb_2", fetchImpl);

    expect(h.findBlock("cb_2").block.media.alt).toBe("Old alt text");
    expect(h.undoStack.entries.length).toBe(depthBefore);
    expect(h.toasts).toEqual(["Alt text generation failed: No API key configured for provider 'openai'."]);
  });

  it("a network error also leaves existing alt_text untouched and surfaces a visible error", async () => {
    const h = createHarness();
    const fetchImpl = () => Promise.reject(new Error("Network request failed"));

    await h.run("cb_1", fetchImpl);

    expect(h.findBlock("cb_1").block.media.alt).toBe("");
    expect(h.toasts).toEqual(["Alt text generation failed: Network request failed"]);
  });

  it("declining the overwrite confirmation for a non-empty existing alt sends no request and leaves it untouched", async () => {
    const h = createHarness(() => false); // simulates the author clicking "Cancel"
    const fetchImpl = vi.fn();

    const outcome = await h.run("cb_2", fetchImpl);

    expect(outcome).toBe("skipped-not-confirmed");
    expect(fetchImpl).not.toHaveBeenCalled();
    expect(h.findBlock("cb_2").block.media.alt).toBe("Old alt text");
    expect(h.toasts).toEqual([]);
  });

  it("accepting the overwrite confirmation proceeds with the request and replaces the existing alt", async () => {
    const h = createHarness(() => true);
    const fetchImpl = () => Promise.resolve({ ok: true, result: { alt_text: "New wiring diagram description." } });

    await h.run("cb_2", fetchImpl);

    expect(h.findBlock("cb_2").block.media.alt).toBe("New wiring diagram description.");
    expect(h.toasts).toEqual(["Alt text generated."]);
  });

  it("disables re-firing on the same block while one is already in flight", async () => {
    const h = createHarness();
    let resolveFetch;
    const fetchImpl = () => new Promise((resolve) => { resolveFetch = resolve; });

    const firstCall = h.run("cb_1", fetchImpl);
    expect(h.inFlight.cb_1).toBe(true);

    const secondCall = await h.run("cb_1", fetchImpl);
    expect(secondCall).toBe("skipped-in-flight");

    resolveFetch({ ok: true, result: { alt_text: "Done." } });
    await firstCall;
    expect(h.inFlight.cb_1).toBeUndefined();
    expect(h.findBlock("cb_1").block.media.alt).toBe("Done.");
  });

  it("a different block can still run while another block's alt-text request is in flight", async () => {
    const h = createHarness();
    let resolveFirst;
    const blockedFetch = () => new Promise((resolve) => { resolveFirst = resolve; });
    const immediateFetch = () => Promise.resolve({ ok: true, result: { alt_text: "New alt." } });

    const firstCall = h.run("cb_2", blockedFetch);
    expect(h.inFlight.cb_2).toBe(true);

    await h.run("cb_1", immediateFetch);
    expect(h.findBlock("cb_1").block.media.alt).toBe("New alt.");

    resolveFirst({ ok: true, result: { alt_text: "New wiring alt." } });
    await firstCall;
  });
});
