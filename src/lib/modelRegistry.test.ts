import { describe, expect, it } from "vitest";
import {
  addApiKey,
  addDiscoveredModels,
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

    addApiKey(state, provider.id, {
      id: "credential-personal",
      name: "Personal GPT",
      secureCredentialReference: "credential-personal",
    });
    addApiKey(state, provider.id, {
      id: "credential-backup",
      name: "Backup GPT",
      secureCredentialReference: "credential-backup",
    });
    setActiveApiKey(state, provider.id, "credential-personal");

    expect(provider.apiKeys).toHaveLength(2);
    expect(provider.activeApiKeyId).toBe("credential-personal");
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

  it("marks removed discovered models unavailable and excludes unknown pricing from free", () => {
    const state = buildInitialState();
    const zen = state.providers.find(
      (provider) => provider.id === "opencode-zen",
    );
    if (!zen)
      throw new Error("OpenCode Zen provider missing from initial state");

    addDiscoveredModels(state, zen.id, [
      {
        id: "dynamic-model-a",
        displayName: "Dynamic Model A",
        free: "unknown",
        apiFamily: "openai-chat",
      },
      {
        id: "dynamic-model-b",
        displayName: "Dynamic Model B",
        free: true,
      },
    ]);
    addDiscoveredModels(state, zen.id, [
      {
        id: "dynamic-model-b",
        displayName: "Dynamic Model B",
        free: true,
      },
    ]);

    expect(
      state.models.find((model) => model.id === "dynamic-model-a")?.available,
    ).toBe(false);
    expect(
      getFilteredModels(state, { freeOnly: true }).some(
        (model) => model.id === "dynamic-model-a",
      ),
    ).toBe(false);
    expect(
      state.models.find((model) => model.id === "dynamic-model-a")?.apiFamily,
    ).toBe("openai-chat");
  });
});
