export type SkillName =
  | "research"
  | "browser"
  | "files"
  | "terminal"
  | "model"
  | "planning";

export interface MemoryEntry {
  id: string;
  content: string;
  createdAt: string;
  tags: string[];
}

export class MemoryStore {
  entries: MemoryEntry[] = [];

  remember(content: string): MemoryEntry {
    const text = String(content ?? "").trim();
    if (!text) {
      return {
        id: "empty",
        content: "",
        createdAt: new Date().toISOString(),
        tags: [],
      };
    }

    const entry: MemoryEntry = {
      id: `memory-${Math.random().toString(36).slice(2, 10)}`,
      content: text,
      createdAt: new Date().toISOString(),
      tags: [
        ...new Set(
          text
            .toLowerCase()
            .split(/[^a-z0-9]+/)
            .filter(Boolean),
        ),
      ],
    };

    this.entries = [entry, ...this.entries].slice(0, 8);
    return entry;
  }

  search(term: string): string[] {
    const query = String(term ?? "")
      .trim()
      .toLowerCase();
    if (!query) {
      return this.entries.map((entry) => entry.content);
    }

    return this.entries
      .filter(
        (entry) =>
          entry.content.toLowerCase().includes(query) ||
          entry.tags.includes(query),
      )
      .map((entry) => entry.content);
  }
}

export const suggestSkills = (prompt: string): SkillName[] => {
  const text = String(prompt ?? "").toLowerCase();
  const suggestions: SkillName[] = [];

  if (/(research|study|analysis|summary|read|document)/.test(text)) {
    suggestions.push("research");
  }
  if (/(browser|web|search|google|website|navigate)/.test(text)) {
    suggestions.push("browser");
  }
  if (/(file|folder|document|notes|csv|pdf|save)/.test(text)) {
    suggestions.push("files");
  }
  if (/(terminal|powershell|command|shell|run)/.test(text)) {
    suggestions.push("terminal");
  }
  if (/(model|ollama|provider|llm|ai|chat)/.test(text)) {
    suggestions.push("model");
  }
  if (/(plan|strategy|workflow|next steps|timeline)/.test(text)) {
    suggestions.push("planning");
  }

  return suggestions.length ? suggestions.slice(0, 3) : ["planning"];
};
