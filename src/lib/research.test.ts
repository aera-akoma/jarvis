import { describe, expect, it } from "vitest";
import {
  buildResearchPlan,
  extractKeywords,
  summarizeDocument,
} from "./research";

describe("research and document layer", () => {
  it("extracts relevant keywords from a research prompt", () => {
    expect(
      extractKeywords("How can AI improve education and research in schools?"),
    ).toEqual(["ai", "improve", "education", "research", "schools"]);
  });

  it("creates a focused research plan from a topic", () => {
    const plan = buildResearchPlan("AI in education and research workflows");

    expect(plan.summary).toContain("AI");
    expect(plan.queries[0]).toContain("AI");
    expect(plan.queries.length).toBeGreaterThan(0);
  });

  it("summarizes a long document into a compact digest", () => {
    const summary = summarizeDocument(
      "Machine learning helps teams reason faster. It can summarize large documents and support careful review. This improves workflows for knowledge workers in everyday practice.",
      2,
    );

    expect(summary).toContain("Machine learning");
    expect(summary.split(" ").length).toBeLessThan(30);
  });
});
