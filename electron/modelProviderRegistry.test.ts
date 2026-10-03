import { createRequire } from "node:module";
import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);
const { generateModel } = require("./modelProviderRegistry.cjs") as {
  generateModel: (request: any) => Promise<any>;
};

describe("provider-neutral model adapter registry", () => {
  it("routes Zen models by catalog API family without returning credentials", async () => {
    let calledUrl = "";
    let sentAuthorization = "";
    const result = await generateModel({
      provider: {
        id: "opencode-zen",
        name: "OpenCode Zen",
        type: "cloud",
        enabled: true,
      },
      model: {
        id: "dynamic-model",
        providerId: "opencode-zen",
        available: true,
        apiFamily: "openai-chat",
        endpoint: "https://opencode.ai/zen/v1/chat/completions",
      },
      messages: [{ role: "user", content: "Hello" }],
      apiKey: "secret-token",
      fetchImpl: async (url: string, options: any) => {
        calledUrl = url;
        sentAuthorization = options.headers.Authorization;
        return {
          ok: true,
          json: async () => ({
            choices: [{ message: { content: "Hello back" } }],
          }),
        };
      },
    });

    expect(calledUrl).toBe("https://opencode.ai/zen/v1/chat/completions");
    expect(sentAuthorization).toBe("Bearer secret-token");
    expect(result).toMatchObject({
      content: "Hello back",
      modelId: "dynamic-model",
    });
    expect(JSON.stringify(result)).not.toContain("secret-token");
  });

  it("keeps existing Ollama requests on the local adapter", async () => {
    let requestUrl = "";
    const result = await generateModel({
      provider: {
        id: "ollama",
        name: "Ollama",
        type: "local",
        apiFormat: "ollama",
        baseUrl: "http://localhost:11434",
        enabled: true,
      },
      model: {
        id: "ollama:qwen3",
        providerId: "ollama",
        available: true,
      },
      messages: [{ role: "user", content: "Hello" }],
      fetchImpl: async (url: string) => {
        requestUrl = url;
        return {
          ok: true,
          json: async () => ({ message: { content: "Local response" } }),
        };
      },
    });

    expect(requestUrl).toBe("http://localhost:11434/api/chat");
    expect(result.content).toBe("Local response");
  });
});
