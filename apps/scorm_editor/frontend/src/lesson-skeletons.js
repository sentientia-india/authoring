// P5-5e: pre-built lesson/module starting-point skeletons usable INSIDE Course Studio's own
// canvas, once a course already exists -- distinct from the pre-generation discovery-flow
// concept the MCP server already exposes (list_course_templates / select_course_template /
// recommend_course_templates in src/course_mcp_server/tools.py). Those tools run before a
// course is even created and hand back a *course-level* shape -- theme, recommended
// interactions, quality rules (see TemplateSelectionResult/TemplateListResult in schemas.py) --
// never individual lesson/module block-and-activity trees, and there is no code path from them
// into a single lesson's content_blocks/activities/quiz_questions. This module fills that gap:
// a small registry of ready-made *lesson* skeletons an author can drop into an existing module
// from the "+ Add lesson" flow (editor.js's module inspector), instead of always starting from
// the single blank "New lesson" content block.
//
// Pure module, no DOM access -- same pattern as quiz-from-content-ai.js / undo-stack.js /
// move-item.js: unit-testable on its own, editor.js owns wiring it into the DOM and the existing
// save(true)/pushHistory() undo-stack path (buildLessonFromSkeleton() returns a plain lesson
// object shaped exactly like the blank-lesson object editor.js's "+ Add lesson" button already
// pushes into module.lessons, so insertion is a single array push, same as today).
//
// All body text below is deliberately generic/placeholder -- labeled as such in each block/
// question's own text -- exactly like TEMPLATES/ACTIVITY_TEMPLATE_REGISTRY's existing "Write the
// learner-facing explanation here." placeholders in editor.js, never fake specific content an
// author might mistake for real course material.

// `idFactory` is injected rather than this module generating its own ids, matching editor.js's
// own `uid(prefix)` helper (e.g. uid("lesson"), uid("cb"), uid("act"), uid("q")) so ids produced
// here are indistinguishable in shape from ids the rest of the editor already mints, and so this
// module stays deterministic/testable without depending on editor.js's Math.random-based uid.
function introBlock(idFactory, text) {
  return { id: idFactory("cb"), type: "intro", text: text };
}

function explanationBlock(idFactory, text) {
  return { id: idFactory("cb"), type: "explanation", text: text };
}

function summaryBlock(idFactory, text) {
  return { id: idFactory("cb"), type: "summary", text: text };
}

function checklistBlock(idFactory, text) {
  return { id: idFactory("cb"), type: "checklist", text: text };
}

function mcqQuestion(idFactory, question, options, correctIndex, explanation) {
  return {
    id: idFactory("q"),
    type: "mcq",
    objective_ids: [],
    question: question,
    options: options,
    correct_answers: [options[correctIndex]],
    explanation: explanation,
  };
}

function decisionActivity(idFactory, title, objective, scenarioText) {
  return {
    activity_id: idFactory("act"),
    activity_type: "scenario_decision_tree",
    title: title,
    objective: objective,
    items: [
      {
        scenario: scenarioText,
        choices: [
          { label: "Best action", result: "best", feedback: "Why this is right." },
          { label: "Risky action", result: "risk", feedback: "Why this backfires." },
        ],
      },
    ],
  };
}

// Each skeleton's `build(idFactory)` returns a plain lesson object (title, duration_minutes,
// objective_ids, objective, content_blocks, activities, quiz_questions) -- the same shape editor.js
// already pushes into module.lessons for a blank lesson, just pre-populated. `objectiveIds` (the
// module's own objective_ids, if any) is threaded through so a skeleton-created lesson inherits
// the module's objectives exactly like the existing blank-lesson creation does.
export var LESSON_SKELETONS = {
  standard_onboarding: {
    name: "Standard onboarding module",
    icon: "🚪",
    note: "Intro, two explanation blocks, a knowledge-check quiz, and a summary.",
    build: function (idFactory, objectiveIds) {
      return {
        id: idFactory("lesson"),
        title: "New onboarding lesson",
        duration_minutes: 12,
        objective_ids: objectiveIds || [],
        objective: "Describe what the learner will be able to do after this lesson. (placeholder -- edit me)",
        content_blocks: [
          introBlock(idFactory, "Open with why this lesson matters to a new hire. (placeholder -- edit me)"),
          explanationBlock(idFactory, "Explain the first key concept here, in plain language. (placeholder -- edit me)"),
          explanationBlock(idFactory, "Explain the second key concept here, building on the first. (placeholder -- edit me)"),
          summaryBlock(idFactory, "Recap the key points from this lesson in one or two sentences. (placeholder -- edit me)"),
        ],
        activities: [],
        quiz_questions: [
          mcqQuestion(
            idFactory,
            "Write a knowledge-check question about the first concept. (placeholder -- edit me)",
            ["Correct answer (placeholder)", "Distractor (placeholder)"],
            0,
            "Explain why the correct answer is right. (placeholder -- edit me)"
          ),
          mcqQuestion(
            idFactory,
            "Write a knowledge-check question about the second concept. (placeholder -- edit me)",
            ["Correct answer (placeholder)", "Distractor (placeholder)"],
            0,
            "Explain why the correct answer is right. (placeholder -- edit me)"
          ),
        ],
      };
    },
  },

  compliance_training: {
    name: "Compliance training module",
    icon: "📋",
    note: "Intro, policy explanation, a decision scenario, a mandatory quiz, and a summary.",
    build: function (idFactory, objectiveIds) {
      return {
        id: idFactory("lesson"),
        title: "New compliance lesson",
        duration_minutes: 15,
        objective_ids: objectiveIds || [],
        objective: "Describe the policy or requirement the learner must be able to follow. (placeholder -- edit me)",
        content_blocks: [
          introBlock(idFactory, "Open with why this policy exists and who it applies to. (placeholder -- edit me)"),
          explanationBlock(idFactory, "State the policy requirement in plain language. (placeholder -- edit me)"),
          explanationBlock(idFactory, "Explain the consequences of not following the policy. (placeholder -- edit me)"),
          summaryBlock(idFactory, "Recap the policy requirement and where to go with questions. (placeholder -- edit me)"),
        ],
        activities: [
          decisionActivity(
            idFactory,
            "Choose the compliant response",
            "Pick the action that follows policy.",
            "Describe a realistic situation where this policy applies. (placeholder -- edit me)"
          ),
        ],
        quiz_questions: [
          mcqQuestion(
            idFactory,
            "Write a mandatory quiz question checking understanding of this policy. (placeholder -- edit me)",
            ["Correct answer (placeholder)", "Distractor (placeholder)"],
            0,
            "Explain why the correct answer is right. (placeholder -- edit me)"
          ),
        ],
      };
    },
  },

  quick_reference: {
    name: "Quick reference module",
    icon: "📎",
    note: "A single dense explanation block plus a checklist.",
    build: function (idFactory, objectiveIds) {
      return {
        id: idFactory("lesson"),
        title: "New quick reference lesson",
        duration_minutes: 5,
        objective_ids: objectiveIds || [],
        objective: "Describe what the learner will be able to look up or do after this lesson. (placeholder -- edit me)",
        content_blocks: [
          explanationBlock(idFactory, "Write the dense reference content here -- steps, definitions, or a quick summary of what to remember. (placeholder -- edit me)"),
          checklistBlock(idFactory, "- First item to check (placeholder -- edit me)\n- Second item to check (placeholder -- edit me)\n- Third item to check (placeholder -- edit me)"),
        ],
        activities: [],
        quiz_questions: [],
      };
    },
  },
};

export var LESSON_SKELETON_IDS = Object.keys(LESSON_SKELETONS);

// Builds a full lesson object from a skeleton id, or throws if the id is unknown -- mirrors
// editor.js's own templatePayload()'s "unknown template" handling (returns null there since it
// has a DOM toast to report through; this module has no DOM, so it throws and lets the caller
// decide how to surface the error).
export function buildLessonFromSkeleton(skeletonId, idFactory, objectiveIds) {
  var skeleton = LESSON_SKELETONS[skeletonId];
  if (!skeleton) throw new Error("Unknown lesson skeleton: " + skeletonId);
  if (typeof idFactory !== "function") throw new Error("buildLessonFromSkeleton requires an idFactory function.");
  return skeleton.build(idFactory, objectiveIds);
}
