import { afterEach, describe, expect, it, vi } from "vitest";
import {
  buildTranslateBlockRequest,
  buildTranslateSystemPrompt,
  extractTranslatedText,
} from "../src/translate-block-ai.js";
import { createUndoStack, pushEntry, undoEntry, canUndo } from "../src/undo-stack.js";

describe("buildTranslateSystemPrompt", () => {
  it("embeds the target language and states the faithful-translation constraints", () => {
    const prompt = buildTranslateSystemPrompt("Spanish");
    expect(prompt).toContain("Spanish");
    expect(prompt.length).toBeGreaterThan(40);
    expect(prompt).toContain("without adding, omitting");
  });
});

describe("buildTranslateBlockRequest", () => {
  const block = { id: "cb_2", type: "explanation", text: "Original explanation text." };
  const siblings = [
    { id: "cb_1", type: "intro", text: "Intro block text that is reasonably long for an excerpt." },
    block,
    { id: "cb_3", type: "example", text: "Example block text that follows the target block." },
  ];

  it("throws when no target language is given", () => {
    expect(() => buildTranslateBlockRequest(block, "Lesson", "", siblings, {})).toThrow(
      "Choose a target language"
    );
    expect(() => buildTranslateBlockRequest(block, "Lesson", "   ", siblings, {})).toThrow(
      "Choose a target language"
    );
  });

  it("throws when the block has no text", () => {
    expect(() => buildTranslateBlockRequest({ id: "cb_0", type: "intro", text: "" }, "Lesson", "French", [], {})).toThrow(
      "no text to translate"
    );
  });

  it("builds a request with a language-specific system prompt, schema_name, and the block's own role/text", () => {
    const body = buildTranslateBlockRequest(block, "Intro to Widgets", "German", siblings, {});
    expect(body.system_prompt).toBe(buildTranslateSystemPrompt("German"));
    expect(body.system_prompt).toContain("German");
    expect(body.schema_name).toBe("content_block_translate");
    expect(body.user_payload.role).toBe("explanation");
    expect(body.user_payload.text).toBe("Original explanation text.");
    expect(body.user_payload.lesson_title).toBe("Intro to Widgets");
    expect(body.user_payload.target_language).toBe("German");
  });

  it("trims the target language", () => {
    const body = buildTranslateBlockRequest(block, "Lesson", "  Japanese  ", siblings, {});
    expect(body.user_payload.target_language).toBe("Japanese");
    expect(body.system_prompt).toContain("Japanese");
  });

  it("includes previous/next sibling block context when present", () => {
    const body = buildTranslateBlockRequest(block, "Lesson", "French", siblings, {});
    expect(body.user_payload.previous_block).toEqual({ role: "intro", excerpt: siblings[0].text });
    expect(body.user_payload.next_block).toEqual({ role: "example", excerpt: siblings[2].text });
  });

  it("omits previous/next block context when the block is first/last or alone", () => {
    const body = buildTranslateBlockRequest(block, "Lesson", "French", [block], {});
    expect(body.user_payload.previous_block).toBeUndefined();
    expect(body.user_payload.next_block).toBeUndefined();
  });

  it("spreads in buildAiRequestFields()-style fields untouched (never nested)", () => {
    const aiFields = { text_provider: "openrouter", text_provider_api_key: "sk-live-1" };
    const body = buildTranslateBlockRequest(block, "Lesson", "French", siblings, aiFields);
    expect(body.text_provider).toBe("openrouter");
    expect(body.text_provider_api_key).toBe("sk-live-1");
  });
});

describe("extractTranslatedText", () => {
  it("returns the trimmed text on a well-formed result", () => {
    expect(extractTranslatedText({ text: "  Texto traducido.  " })).toBe("Texto traducido.");
  });

  it("throws when result is missing/not an object", () => {
    expect(() => extractTranslatedText(null)).toThrow("empty");
    expect(() => extractTranslatedText(undefined)).toThrow("empty");
    expect(() => extractTranslatedText("just a string")).toThrow("empty");
  });

  it("throws when result.text is missing or blank", () => {
    expect(() => extractTranslatedText({})).toThrow("did not include translated text");
    expect(() => extractTranslatedText({ text: "   " })).toThrow("did not include translated text");
    expect(() => extractTranslatedText({ text: 123 })).toThrow("did not include translated text");
  });
});

// ---------------------------------------------------------------------------
// The tests below simulate editor.js's runTranslateAiAction() orchestration -- build one request
// per block in scope with buildTranslateBlockRequest(), call a (mocked) fetch per block, and only
// once EVERY request in the batch has resolved successfully, insert a brand-new sibling block
// (tagged with `language`/`translated_from`) right after the block it came from, then push one
// undo-stack entry -- mirroring runContentBlockAiTransform's own orchestration test harness
// (content-block-ai.test.js) since editor.js itself cannot be imported headlessly (top-level IIFE
// bound to document.getElementById(...) at import time -- see that file's header comment).
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

function findBlockIn(course, cbId) {
  for (const module of course.modules) {
    for (const lesson of module.lessons) {
      for (const block of lesson.content_blocks) {
        if (block.id === cbId) return { block, lesson };
      }
    }
  }
  return null;
}

// Mirrors editor.js's runTranslateAiAction(): builds one request per target, fires them all, and
// only inserts anything once every one of them has resolved successfully.
function createHarness() {
  const course = makeCourse();
  const undoStack = createUndoStack(50);
  pushEntry(undoStack, clone(course));
  const inFlight = {};
  const toasts = [];

  function run(flightKey, targets, language, fetchImpl) {
    if (inFlight[flightKey]) return Promise.resolve("skipped-in-flight");
    const bodies = targets.map((t) =>
      buildTranslateBlockRequest(t.block, t.lesson.title, language, t.lesson.content_blocks, {})
    );
    inFlight[flightKey] = true;
    return Promise.all(bodies.map((body) => fetchImpl(body).then((data) => {
      if (!data.ok) throw new Error(data.error || "AI request failed.");
      return extractTranslatedText(data.result);
    })))
      .then((translatedTexts) => {
        targets.forEach((target, i) => {
          const blocks = target.lesson.content_blocks;
          const index = blocks.indexOf(target.block);
          blocks.splice(index + 1, 0, {
            id: "cb_new_" + i,
            type: target.block.type,
            text: translatedTexts[i],
            language,
            translated_from: target.block.id,
          });
        });
        pushEntry(undoStack, clone(course));
        toasts.push("Translated " + targets.length + " block(s) into " + language + ".");
      })
      .catch((error) => {
        toasts.push("Translation failed: " + error.message);
      })
      .finally(() => {
        delete inFlight[flightKey];
      });
  }

  return { course, undoStack, inFlight, toasts, run };
}

describe("translate AI action orchestration (simulated editor.js flow)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("a successful single-block translation inserts a NEW sibling block right after the original, leaves the original byte-for-byte untouched, and is undoable", async () => {
    const h = createHarness();
    const originalBeforeSnapshot = clone(findBlockIn(h.course, "cb_2").block);
    const fetchImpl = () => Promise.resolve({ ok: true, result: { text: "Texto de explicación traducido." } });

    await h.run("block:cb_2", [{ lesson: h.course.modules[0].lessons[0], block: findBlockIn(h.course, "cb_2").block }], "Spanish", fetchImpl);

    const lesson = h.course.modules[0].lessons[0];
    // Original block is genuinely untouched -- byte-for-byte identical to before the call, not
    // just "still present with the same id".
    const originalNow = lesson.content_blocks.find((b) => b.id === "cb_2");
    expect(JSON.stringify(originalNow)).toBe(JSON.stringify(originalBeforeSnapshot));

    // A NEW block was inserted immediately after the original, tagged as a translation -- not
    // merged into cb_2, not overwriting anything.
    expect(lesson.content_blocks).toHaveLength(4);
    const inserted = lesson.content_blocks[2];
    expect(inserted.id).not.toBe("cb_2");
    expect(inserted.text).toBe("Texto de explicación traducido.");
    expect(inserted.language).toBe("Spanish");
    expect(inserted.translated_from).toBe("cb_2");
    expect(inserted.type).toBe("explanation"); // same role as the block it translates

    // Sibling blocks (never targeted) are untouched.
    expect(lesson.content_blocks[0].text).toBe("Intro text.");
    expect(lesson.content_blocks[3].text).toBe("Example text.");

    expect(canUndo(h.undoStack)).toBe(true);
    const restored = undoEntry(h.undoStack);
    expect(restored.modules[0].lessons[0].content_blocks).toHaveLength(3); // the insertion is undone

    expect(h.toasts).toEqual(["Translated 1 block(s) into Spanish."]);
  });

  it("a failed translation (provider error) leaves the original untouched and inserts nothing", async () => {
    const h = createHarness();
    const lesson = h.course.modules[0].lessons[0];
    const originalBeforeSnapshot = clone(findBlockIn(h.course, "cb_2").block);
    const lengthBefore = lesson.content_blocks.length;
    const fetchImpl = () => Promise.resolve({ ok: false, error: "No API key configured for provider 'openai'." });

    await h.run("block:cb_2", [{ lesson, block: findBlockIn(h.course, "cb_2").block }], "Spanish", fetchImpl);

    expect(lesson.content_blocks).toHaveLength(lengthBefore); // nothing inserted
    expect(JSON.stringify(findBlockIn(h.course, "cb_2").block)).toBe(JSON.stringify(originalBeforeSnapshot));
    expect(h.toasts).toEqual(["Translation failed: No API key configured for provider 'openai'."]);
  });

  it("a network error also leaves the original untouched and inserts nothing", async () => {
    const h = createHarness();
    const lesson = h.course.modules[0].lessons[0];
    const lengthBefore = lesson.content_blocks.length;
    const fetchImpl = () => Promise.reject(new Error("Network request failed"));

    await h.run("block:cb_2", [{ lesson, block: findBlockIn(h.course, "cb_2").block }], "Spanish", fetchImpl);

    expect(lesson.content_blocks).toHaveLength(lengthBefore);
    expect(h.toasts).toEqual(["Translation failed: Network request failed"]);
  });

  it("a multi-block (lesson scope) batch where ONE block fails inserts NOTHING for the whole batch -- no partial insert", async () => {
    const h = createHarness();
    const lesson = h.course.modules[0].lessons[0];
    const lengthBefore = lesson.content_blocks.length;
    const targets = [
      { lesson, block: findBlockIn(h.course, "cb_1").block },
      { lesson, block: findBlockIn(h.course, "cb_2").block }, // this one will fail
      { lesson, block: findBlockIn(h.course, "cb_3").block },
    ];
    let call = 0;
    const fetchImpl = () => {
      call += 1;
      if (call === 2) return Promise.resolve({ ok: false, error: "Provider timeout." });
      return Promise.resolve({ ok: true, result: { text: "Translated." } });
    };

    await h.run("lesson:0:0", targets, "Spanish", fetchImpl);

    // Even though two of the three requests "succeeded", nothing was inserted because the batch
    // as a whole failed.
    expect(lesson.content_blocks).toHaveLength(lengthBefore);
    expect(h.toasts).toEqual(["Translation failed: Provider timeout."]);
  });

  it("a multi-block (lesson scope) batch where every block succeeds inserts one new block after each original, in one undo step", async () => {
    const h = createHarness();
    const lesson = h.course.modules[0].lessons[0];
    const targets = [
      { lesson, block: findBlockIn(h.course, "cb_1").block },
      { lesson, block: findBlockIn(h.course, "cb_3").block },
    ];
    const fetchImpl = () => Promise.resolve({ ok: true, result: { text: "Translated." } });

    await h.run("lesson:0:0", targets, "French", fetchImpl);

    expect(lesson.content_blocks).toHaveLength(5);
    expect(lesson.content_blocks.map((b) => b.id)).toEqual(["cb_1", "cb_new_0", "cb_2", "cb_3", "cb_new_1"]);
    expect(canUndo(h.undoStack)).toBe(true);
    const restored = undoEntry(h.undoStack);
    expect(restored.modules[0].lessons[0].content_blocks).toHaveLength(3);
  });

  it("disables re-firing the same target while a translation is already in flight", async () => {
    const h = createHarness();
    const lesson = h.course.modules[0].lessons[0];
    let resolveFetch;
    const fetchImpl = () => new Promise((resolve) => { resolveFetch = resolve; });

    const firstCall = h.run("block:cb_2", [{ lesson, block: findBlockIn(h.course, "cb_2").block }], "Spanish", fetchImpl);
    expect(h.inFlight["block:cb_2"]).toBe(true);

    const secondCall = await h.run("block:cb_2", [{ lesson, block: findBlockIn(h.course, "cb_2").block }], "Spanish", fetchImpl);
    expect(secondCall).toBe("skipped-in-flight");

    resolveFetch({ ok: true, result: { text: "Traducido." } });
    await firstCall;
    expect(h.inFlight["block:cb_2"]).toBeUndefined();
  });
});
