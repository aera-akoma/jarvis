import { describe, expect, it } from "vitest";
import {
  buildProviderConfig,
  extractOpenCodeZenModels,
  isOpenCodeZenFreeModel,
} from "./opencodeZen";

describe("opencode zen provider", () => {
  it("parses the provider catalog into registry-friendly models", () => {
    const models = extractOpenCodeZenModels({
      data: [
        {
          id: "big-pickle",
          object: "model",
          created: 1710000000,
          owned_by: "opencode",
          free: true,
          description: "Core reasoning model",
          capabilities: ["text", "reasoning"],
        },
        {
          id: "mimo-v2.6-flash",
          object: "model",
          created: 1710000001,
          owned_by: "opencode",
          free: false,
          pricing: { prompt: 0.0001, completion: 0.0002 },
        },
      ],
    });

    expect(models).toHaveLength(2);
    expect(models[0]).toMatchObject({
      id: "big-pickle",
      free: true,
      category: "cloud",
      providerId: "opencode-zen",
    });
    expect(models[1].free).toBe(false);
  });

  it("marks free models from provider metadata without hard-coding names", () => {
    expect(
      isOpenCodeZenFreeModel({
        id: "space-bunny-free",
        free: true,
        pricing: { prompt: 0, completion: 0 },
      }),
    ).toBe(true);
    expect(
      isOpenCodeZenFreeModel({
        id: "longcat-pro",
        free: false,
        pricing: { prompt: 0.001, completion: 0.002 },
      }),
    ).toBe(false);
  });

  it("builds the provider config with the OpenCode Zen endpoints", () => {
    expect(buildProviderConfig()).toMatchObject({
      id: "opencode-zen",
      name: "OpenCode Zen",
      type: "cloud",
      apiFormat: "openai-compatible",
      baseUrl: "https://opencode.ai/zen/v1",
    });
  });
});
