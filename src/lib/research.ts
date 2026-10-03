const STOP_WORDS = new Set([
  "a",
  "an",
  "and",
  "are",
  "as",
  "at",
  "be",
  "by",
  "can",
  "for",
  "from",
  "how",
  "in",
  "into",
  "is",
  "it",
  "of",
  "on",
  "or",
  "that",
  "the",
  "their",
  "this",
  "to",
  "using",
  "with",
  "what",
  "when",
  "where",
  "why",
  "will",
  "you",
  "your",
]);

export const normalizeText = (value: string) =>
  String(value ?? "")
    .replace(/\s+/g, " ")
    .trim();

export const extractKeywords = (input: string, limit = 5): string[] => {
  const normalized = normalizeText(input).toLowerCase();
  if (!normalized) {
    return [];
  }

  const words = normalized
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((word) => word.length > 1 && !STOP_WORDS.has(word));

  const unique: string[] = [];
  const seen = new Set<string>();
  for (const word of words) {
    if (!seen.has(word)) {
      seen.add(word);
      unique.push(word);
    }
    if (unique.length >= limit) {
      break;
    }
  }

  return unique;
};

export const buildResearchPlan = (topic: string) => {
  const cleanTopic = normalizeText(topic) || "general research";
  const keywords = extractKeywords(cleanTopic, 5);
  const fallbackKeywords = keywords.length
    ? keywords
    : ["research", "analysis", "workflow"];
  const displayKeywords = fallbackKeywords.map((keyword) =>
    keyword === "ai" ? "AI" : keyword,
  );

  const queries = [
    `${displayKeywords.join(" ")} overview`,
    `${displayKeywords.join(" ")} best practices`,
    `${displayKeywords.join(" ")} implementation guide`,
  ];

  return {
    topic: cleanTopic,
    keywords: fallbackKeywords,
    queries,
    summary: `Research brief for "${cleanTopic}": prioritize ${displayKeywords.join(", ")}, compare current methods, and finalize with a clear recommendation grounded in evidence.`,
  };
};

export const summarizeDocument = (
  content: string,
  maxSentences = 3,
): string => {
  const normalized = normalizeText(content);
  if (!normalized) {
    return "No content available.";
  }

  const sentences = normalized
    .split(/(?<=[.!?])\s+/)
    .filter(Boolean)
    .slice(0, maxSentences)
    .join(" ");

  return sentences || normalized.slice(0, 220);
};
