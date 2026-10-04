import { createRequire } from "node:module";
import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);
const { discoverModels, generateModel } =
  require("./modelProviderRegistry.cjs") as {
    discoverModels: (request: any) => Promise<any[]>;
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

  it("discovers Inference models without sending Authorization", async () => {
    let requestUrl = "";
    let requestHeaders: Record<string, string> = {};
    const models = await discoverModels({
      provider: {
        id: "opencode-inference",
        name: "OpenCode Inference",
        enabled: true,
      },
      fetchImpl: async (url: string, options: any) => {
        requestUrl = url;
        requestHeaders = options.headers;
        return {
          ok: true,
          status: 200,
          json: async () => ({
            data: [{ id: "fledge-alpha-free", object: "model" }],
          }),
        };
      },
    });

    expect(requestUrl).toBe("https://opencode.ai/inference/v1/models");
    expect(requestHeaders.Authorization).toBeUndefined();
    expect(models[0].id).toBe("fledge-alpha-free");
  });

  it("dispatches Inference chat without an API key and leaves Zen routing separate", async () => {
    let requestUrl = "";
    let requestHeaders: Record<string, string> = {};
    const result = await generateModel({
      provider: {
        id: "opencode-inference",
        name: "OpenCode Inference",
        type: "cloud",
        enabled: true,
      },
      model: {
        id: "fledge-alpha-free",
        providerId: "opencode-inference",
        available: true,
        apiFamily: "openai-chat",
        authentication: "none",
      },
      messages: [{ role: "user", content: "Hello" }],
      fetchImpl: async (url: string, options: any) => {
        requestUrl = url;
        requestHeaders = options.headers;
        return {
          ok: true,
          status: 200,
          json: async () => ({
            choices: [{ message: { content: "Inference response" } }],
          }),
        };
      },
    });

    expect(requestUrl).toBe(
      "https://opencode.ai/inference/openai/v1/chat/completions",
    );
    expect(requestHeaders.Authorization).toBeUndefined();
    expect(result.content).toBe("Inference response");
  });
});
