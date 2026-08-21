import { describe, expect, it } from "vitest";
import {
  QUIZ_FROM_CONTENT_QUESTION_COUNT,
  QUIZ_FROM_CONTENT_SYSTEM_PROMPT,
  buildQuizFromContentRequest,
  extractQuizQuestions,
} from "../src/quiz-from-content-ai.js";

describe("QUIZ_FROM_CONTENT_SYSTEM_PROMPT", () => {
  it("is a non-trivial prompt that names the fixed question count and the QuizBank-shaped JSON contract", () => {
    expect(QUIZ_FROM_CONTENT_QUESTION_COUNT).toBe(4);
    expect(QUIZ_FROM_CONTENT_SYSTEM_PROMPT.length).toBeGreaterThan(100);
    expect(QUIZ_FROM_CONTENT_SYSTEM_PROMPT).toContain("4");
    expect(QUIZ_FROM_CONTENT_SYSTEM_PROMPT).toContain("options");
    expect(QUIZ_FROM_CONTENT_SYSTEM_PROMPT).toContain("answer");
  });
});

describe("buildQuizFromContentRequest", () => {
  const blockA = { id: "cb_1", type: "intro", text: "Widgets are small mechanical parts." };
  const blockB = { id: "cb_2", type: "explanation", text: "Widgets connect to gadgets via a socket." };
  const emptyBlock = { id: "cb_3", type: "example", text: "   " };

  it("throws on an unknown scope", () => {
    expect(() => buildQuizFromContentRequest("course", "Lesson", [blockA], {})).toThrow("Unknown quiz scope");
  });

  it("throws when there is no usable text in scope", () => {
    expect(() => buildQuizFromContentRequest("block", "Lesson", [emptyBlock], {})).toThrow("no text here");
    expect(() => buildQuizFromContentRequest("lesson", "Lesson", [], {})).toThrow("no text here");
  });

  it("builds a request carrying the fixed system prompt and schema_name", () => {
    const body = buildQuizFromContentRequest("block", "Intro to Widgets", [blockA], {});
    expect(body.system_prompt).toBe(QUIZ_FROM_CONTENT_SYSTEM_PROMPT);
    expect(body.schema_name).toBe("quiz_from_content");
    expect(body.user_payload.scope).toBe("block");
    expect(body.user_payload.lesson_title).toBe("Intro to Widgets");
    expect(body.user_payload.question_count).toBe(QUIZ_FROM_CONTENT_QUESTION_COUNT);
  });

  it("concatenates every scoped block's text with a role label, in order, for lesson scope", () => {
    const body = buildQuizFromContentRequest("lesson", "Lesson", [blockA, blockB], {});
    expect(body.user_payload.content).toBe(
      "[intro] Widgets are small mechanical parts.\n\n[explanation] Widgets connect to gadgets via a socket."
    );
  });

  it("skips blank blocks when concatenating", () => {
    const body = buildQuizFromContentRequest("lesson", "Lesson", [blockA, emptyBlock, blockB], {});
    expect(body.user_payload.content).not.toContain("example");
    expect(body.user_payload.content).toBe(
      "[intro] Widgets are small mechanical parts.\n\n[explanation] Widgets connect to gadgets via a socket."
    );
  });

  it("uses only the single scoped block's text for block scope", () => {
    const body = buildQuizFromContentRequest("block", "Lesson", [blockB], {});
    expect(body.user_payload.content).toBe("[explanation] Widgets connect to gadgets via a socket.");
  });

  it("spreads in buildAiRequestFields()-style fields untouched (never nested)", () => {
    const aiFields = { text_provider: "openrouter", text_provider_api_key: "sk-live-1" };
    const body = buildQuizFromContentRequest("block", "Lesson", [blockA], aiFields);
    expect(body.text_provider).toBe("openrouter");
    expect(body.text_provider_api_key).toBe("sk-live-1");
  });
});

describe("extractQuizQuestions", () => {
  it("returns one plain question object per valid question, mapping answer -> correct_answers", () => {
    const result = {
      course_title: "T",
      questions: [
        {
          id: "q1",
          type: "mcq",
          difficulty: "beginner",
          objective: "Recall the widget-socket relationship.",
          question: "How do widgets connect to gadgets?",
          options: ["Via a socket", "Via glue", "Via magnets"],
          answer: "Via a socket",
          explanation: "The text says widgets connect via a socket.",
        },
        {
          id: "q2",
          type: "true_false",
          difficulty: "beginner",
          objective: "Recall widget size.",
          question: "Widgets are small.",
          options: ["True", "False"],
          answer: "True",
          explanation: "The text says widgets are small.",
        },
      ],
    };
    const questions = extractQuizQuestions(result);
    expect(questions).toHaveLength(2);
    expect(questions[0]).toEqual({
      question: "How do widgets connect to gadgets?",
      options: ["Via a socket", "Via glue", "Via magnets"],
      correct_answers: ["Via a socket"],
      explanation: "The text says widgets connect via a socket.",
    });
    expect(questions[1].correct_answers).toEqual(["True"]);
  });

  it("throws when result is missing/not an object", () => {
    expect(() => extractQuizQuestions(null)).toThrow("empty");
    expect(() => extractQuizQuestions(undefined)).toThrow("empty");
    expect(() => extractQuizQuestions("just a string")).toThrow("empty");
  });

  it("throws when there are no questions", () => {
    expect(() => extractQuizQuestions({ questions: [] })).toThrow("did not include any quiz questions");
    expect(() => extractQuizQuestions({})).toThrow("did not include any quiz questions");
  });

  it("throws on a malformed question (fewer than 2 options)", () => {
    const result = { questions: [{ question: "Q?", options: ["Only one"], answer: "Only one", explanation: "E" }] };
    expect(() => extractQuizQuestions(result)).toThrow("malformed quiz question (#1)");
  });

  it("throws when the answer is not one of the listed options", () => {
    const result = {
      questions: [{ question: "Q?", options: ["A", "B"], answer: "Not an option", explanation: "E" }],
    };
    expect(() => extractQuizQuestions(result)).toThrow("malformed quiz question (#1)");
  });

  it("throws when the question text is blank", () => {
    const result = { questions: [{ question: "  ", options: ["A", "B"], answer: "A", explanation: "E" }] };
    expect(() => extractQuizQuestions(result)).toThrow("malformed quiz question (#1)");
  });

  it("defaults a missing explanation rather than throwing", () => {
    const result = { questions: [{ question: "Q?", options: ["A", "B"], answer: "A" }] };
    const questions = extractQuizQuestions(result);
    expect(questions[0].explanation).toBe("Explain why this answer is correct.");
  });
});
