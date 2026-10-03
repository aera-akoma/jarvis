import { describe, expect, it } from "vitest";
import { buildProviderConfig } from "./opencodeZen";

describe("opencode zen provider", () => {
  it("builds the provider config with the OpenCode Zen endpoints", () => {
    expect(buildProviderConfig()).toMatchObject({
      id: "opencode-zen",
      name: "OpenCode Zen",
      type: "cloud",
      apiFormat: "openai-compatible",
      baseUrl: "https://opencode.ai/zen/v1",
    });
  });

  it("does not seed a hard-coded Zen model before catalog discovery", async () => {
    const { buildInitialState } = await import("./modelRegistry");
    const state = buildInitialState();

    expect(
      state.models.filter((model) => model.providerId === "opencode-zen"),
    ).toEqual([]);
  });
});
