import { describe, expect, it } from "vitest";
import { MemoryStore, suggestSkills } from "./memory";

describe("memory and skills layer", () => {
  it("stores and retrieves notes by keyword", () => {
    const memories = new MemoryStore();
    memories.remember(
      "Project A uses local Ollama models for safe offline review.",
    );

    expect(memories.search("ollama")).toHaveLength(1);
    expect(memories.search("offline")[0]).toContain("local");
  });

  it("recommends matching skills for the task context", () => {
    expect(
      suggestSkills("Research AI in education and prepare a summary")[0],
    ).toBe("research");
    expect(suggestSkills("Open browser search and analyze files")).toContain(
      "browser",
    );
  });
});
