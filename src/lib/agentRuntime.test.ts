import { describe, expect, it } from "vitest";
import {
  buildFallbackOrder,
  createTaskState,
  runModelSwitchSequence,
  simulateProviderRequest,
  validateModelCapabilities,
} from "./agentRuntime";

describe("agent runtime", () => {
  it("preserves the task state while switching models", () => {
    const task = createTaskState(
      "Research and summarize this topic.",
      "qwen3-local",
    );
    const result = runModelSwitchSequence(task, ["qwen3-local", "gpt-4o-mini"]);

    expect(result).toHaveLength(2);
    expect(result.every((entry) => entry.preserved)).toBe(true);
    expect(result[result.length - 1].task.modelHistory).toContain(
      "gpt-4o-mini",
    );
  });

  it("supports capability checks and fallback routing", () => {
    const task = createTaskState(
      "Continue the current project.",
      "qwen3-local",
    );
    const ordering = buildFallbackOrder(
      "qwen3-local",
      "gpt-4o-mini",
      "claude-3-5-sonnet",
      "gemini-2-flash",
    );
    const model = {
      id: "gpt-4o-mini",
      providerId: "openai",
      displayName: "GPT-4o Mini",
      category: "cloud",
      free: false,
      capabilities: ["text", "tool-calling", "structured-output"],
      available: true,
      apiFormat: "openai-compatible",
    };

    expect(validateModelCapabilities(model, ["text", "tool-calling"])).toBe(
      true,
    );
    expect(ordering).toEqual([
      "qwen3-local",
      "gpt-4o-mini",
      "claude-3-5-sonnet",
      "gemini-2-flash",
    ]);
    expect(
      runModelSwitchSequence(task, [
        "Qwen",
        "GPT",
        "Claude",
        "Gemini",
        "Qwen",
      ]).every((entry) => entry.preserved),
    ).toBe(true);
  });

  it("rejects invalid provider requests that lack required capabilities", () => {
    const response = simulateProviderRequest(
      {
        id: "local-model",
        providerId: "ollama",
        displayName: "Local Model",
        capabilities: ["text"],
      },
      "Test prompt",
      ["tool-calling"],
    );

    expect(response.ok).toBe(false);
    expect(response.status).toBe("capability-mismatch");
  });
});
