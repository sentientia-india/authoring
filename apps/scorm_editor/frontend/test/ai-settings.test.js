import { afterEach, describe, expect, it } from "vitest";
import {
  KNOWN_TEXT_PROVIDERS,
  buildAiRequestFields,
  getAiSettings,
  requiresCustomEndpointFields,
  resetAiSettings,
  setAiSettings,
} from "../src/ai-settings.js";

afterEach(() => {
  resetAiSettings();
});

describe("KNOWN_TEXT_PROVIDERS", () => {
  it("lists exactly the six text_providers/ registry adapters", () => {
    expect(KNOWN_TEXT_PROVIDERS.map((entry) => entry.id)).toEqual([
      "openrouter",
      "deepseek",
      "openai",
      "anthropic",
      "gemini",
      "openai_compatible",
    ]);
  });
});

describe("getAiSettings / setAiSettings", () => {
  it("defaults to openrouter with no key", () => {
    expect(getAiSettings()).toEqual({ provider: "openrouter", apiKey: "", baseUrl: "", model: "" });
  });

  it("updates only the fields provided", () => {
    setAiSettings({ provider: "openai", apiKey: "sk-test" });
    expect(getAiSettings()).toEqual({ provider: "openai", apiKey: "sk-test", baseUrl: "", model: "" });
  });

  it("rejects an unknown provider id", () => {
    expect(() => setAiSettings({ provider: "made-up" })).toThrow("Unknown text provider");
  });

  it("returns a defensive copy that cannot mutate module state", () => {
    var snapshot = getAiSettings();
    snapshot.apiKey = "mutated";
    expect(getAiSettings().apiKey).toBe("");
  });

  it("resetAiSettings clears everything back to defaults", () => {
    setAiSettings({ provider: "gemini", apiKey: "secret", baseUrl: "https://x", model: "m" });
    resetAiSettings();
    expect(getAiSettings()).toEqual({ provider: "openrouter", apiKey: "", baseUrl: "", model: "" });
  });
});

describe("requiresCustomEndpointFields", () => {
  it("is true only for openai_compatible", () => {
    expect(requiresCustomEndpointFields("openai_compatible")).toBe(true);
    expect(requiresCustomEndpointFields("openrouter")).toBe(false);
    expect(requiresCustomEndpointFields("anthropic")).toBe(false);
  });
});

describe("buildAiRequestFields", () => {
  it("omits the api key field entirely when no key was entered", () => {
    expect(buildAiRequestFields()).toEqual({ text_provider: "openrouter" });
  });

  it("includes the key only under text_provider_api_key", () => {
    setAiSettings({ apiKey: "sk-live-123" });
    var fields = buildAiRequestFields();
    expect(fields.text_provider_api_key).toBe("sk-live-123");
    expect(Object.keys(fields).sort()).toEqual(["text_provider", "text_provider_api_key"]);
  });

  it("includes base_url and model for openai_compatible even if the model field is blank", () => {
    setAiSettings({ provider: "openai_compatible", baseUrl: "https://api.example.com/v1", apiKey: "k" });
    expect(buildAiRequestFields()).toEqual({
      text_provider: "openai_compatible",
      text_provider_api_key: "k",
      text_provider_base_url: "https://api.example.com/v1",
      text_provider_model: "",
    });
  });

  it("includes model as an override for non-custom providers only when set", () => {
    setAiSettings({ provider: "anthropic", model: "claude-x" });
    expect(buildAiRequestFields()).toEqual({ text_provider: "anthropic", text_provider_model: "claude-x" });
  });

  it("never includes baseUrl/apiKey/model under any key resembling course content", () => {
    setAiSettings({ provider: "deepseek", apiKey: "topsecret" });
    var fields = buildAiRequestFields();
    var serialized = JSON.stringify(fields);
    // Guard against a future accidental rename that would make this collide with course.json's
    // own field names (course_title, modules, ...).
    expect(serialized).not.toMatch(/course_title|modules|"course"/);
  });
});
