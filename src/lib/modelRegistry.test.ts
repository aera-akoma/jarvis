import { describe, expect, it } from "vitest";
import {
  addApiKey,
  addManualModel,
  addProvider,
  buildInitialState,
  getFilteredModels,
  setActiveApiKey,
} from "./modelRegistry";

describe("model registry", () => {
  it("stores multiple keys per provider and keeps one active key selected", () => {
    const state = buildInitialState();

    const provider = addProvider(state, {
      name: "OpenAI",
      type: "cloud",
      apiFormat: "openai-compatible",
      baseUrl: "https://api.openai.com/v1",
    });

    addApiKey(state, provider.id, { name: "Personal GPT", value: "secret-1" });
    addApiKey(state, provider.id, { name: "Backup GPT", value: "secret-2" });
    setActiveApiKey(state, provider.id, "Personal GPT");

    expect(provider.apiKeys).toHaveLength(2);
    expect(provider.activeApiKeyName).toBe("Personal GPT");
  });

  it("supports custom models and free-only filtering", () => {
    const state = buildInitialState();

    const provider = addProvider(state, {
      name: "Custom Cloud",
      type: "cloud",
      apiFormat: "openai-compatible",
      baseUrl: "https://example.com/v1",
    });

    addManualModel(state, provider.id, {
      id: "free-model",
      displayName: "Free Model",
      category: "cloud",
      free: true,
      capabilities: ["text"],
      apiFormat: "openai-compatible",
    });
    addManualModel(state, provider.id, {
      id: "paid-model",
      displayName: "Paid Model",
      category: "cloud",
      free: false,
      capabilities: ["text"],
      apiFormat: "openai-compatible",
    });

    const freeOnly = getFilteredModels(state, {
      freeOnly: true,
      providerId: provider.id,
    });

    expect(freeOnly).toHaveLength(1);
    expect(freeOnly[0].displayName).toBe("Free Model");
  });
});
