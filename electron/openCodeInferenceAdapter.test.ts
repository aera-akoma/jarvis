import { createRequire } from "node:module";
import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);
const { generateInferenceModel, normalizeInferenceModels } =
  require("./openCodeInferenceAdapter.cjs") as {
    generateInferenceModel: (input: any) => Promise<any>;
    normalizeInferenceModels: (payload: any) => any[];
  };

describe("OpenCode Inference adapter", () => {
  it("normalizes live IDs without assuming free status or capabilities", () => {
    const models = normalizeInferenceModels({
      object: "list",
      data: [
        { id: "fledge-alpha-free", object: "model", owned_by: "opencode" },
        { id: "mimo-v2.5-free", object: "model", owned_by: "opencode" },
        { id: "space-bunny-free", object: "model", owned_by: "opencode" },
        { id: "big-pickle", object: "model", owned_by: "opencode" },
        { id: "gpt-5", object: "model", owned_by: "opencode" },
        { id: "claude-sonnet-4-6", object: "model", owned_by: "opencode" },
        { id: "gemini-3.1-pro", object: "model", owned_by: "opencode" },
        { id: "unmapped-model", object: "model", owned_by: "opencode" },
      ],
    });

    expect(models).toHaveLength(8);
    expect(models[0]).toMatchObject({
      id: "fledge-alpha-free",
      providerId: "opencode-inference",
      free: true,
      authentication: "none",
      apiFamily: "openai-chat",
      endpoint: "https://opencode.ai/inference/openai/v1/chat/completions",
    });
    expect(models[1]).toMatchObject({ free: true, apiFamily: "openai-chat" });
    expect(models[2]).toMatchObject({ free: true, apiFamily: "openai-chat" });
    expect(models[3]).toMatchObject({ free: "unknown", apiFamily: "unknown" });
    expect(models[4].apiFamily).toBe("openai-responses");
    expect(models[5].apiFamily).toBe("anthropic-messages");
    expect(models[6].apiFamily).toBe("google-generative");
    expect(models[7]).toMatchObject({
      apiFamily: "unknown",
      free: "unknown",
      capabilities: [],
    });
  });

  it("sends a free chat request without Authorization and normalizes its response", async () => {
    let requestUrl = "";
    let requestHeaders: Record<string, string> = {};
    let requestBody: any;
    const result = await generateInferenceModel({
      model: {
        id: "fledge-alpha-free",
        providerId: "opencode-inference",
        apiFamily: "openai-chat",
        authentication: "none",
        available: true,
        endpoint: "https://opencode.ai/inference/openai/v1/chat/completions",
      },
      messages: [
        {
          role: "user",
          content: "Reply with exactly: JARVIS INFERENCE TEST SUCCESS",
        },
      ],
      fetchImpl: async (url: string, options: any) => {
        requestUrl = url;
        requestHeaders = options.headers;
        requestBody = JSON.parse(options.body);
        return {
          ok: true,
          status: 200,
          json: async () => ({
            choices: [
              { message: { content: "JARVIS INFERENCE TEST SUCCESS" } },
            ],
          }),
        };
      },
    });

    expect(requestUrl).toBe(
      "https://opencode.ai/inference/openai/v1/chat/completions",
    );
    expect(requestHeaders.Authorization).toBeUndefined();
    expect(requestBody).toEqual({
      model: "fledge-alpha-free",
      messages: [
        {
          role: "user",
          content: "Reply with exactly: JARVIS INFERENCE TEST SUCCESS",
        },
      ],
    });
    expect(requestBody.stream).toBeUndefined();
    expect(result).toMatchObject({
      ok: true,
      providerId: "opencode-inference",
      modelId: "fledge-alpha-free",
      content: "JARVIS INFERENCE TEST SUCCESS",
    });
  });

  it("does not route unsupported API families through Chat Completions", async () => {
    let requestSent = false;
    await expect(
      generateInferenceModel({
        model: {
          id: "gpt-5",
          providerId: "opencode-inference",
          apiFamily: "openai-responses",
          authentication: "api-key",
          available: true,
          endpoint: "https://opencode.ai/inference/openai/v1/responses",
        },
        messages: [{ role: "user", content: "Hello" }],
        apiKey: "service-account-key",
        fetchImpl: async () => {
          requestSent = true;
          return { ok: true, status: 200, json: async () => ({}) };
        },
      }),
    ).rejects.toThrow(
      "This model family is discovered but not yet supported by Jarvis.",
    );
    expect(requestSent).toBe(false);
  });

  it("adds a bearer key only for a model marked as requiring authentication", async () => {
    let authorization = "";
    await generateInferenceModel({
      model: {
        id: "glm-5.1",
        providerId: "opencode-inference",
        apiFamily: "openai-chat",
        authentication: "api-key",
        available: true,
      },
      messages: [{ role: "user", content: "Hello" }],
      apiKey: "service-account-test-value",
      fetchImpl: async (_url: string, options: any) => {
        authorization = options.headers.Authorization;
        return {
          ok: true,
          status: 200,
          json: async () => ({ choices: [{ message: { content: "Hello" } }] }),
        };
      },
    });

    expect(authorization).toBe("Bearer service-account-test-value");
  });

  it("maps an external free-tier 403 to a safe policy error", async () => {
    await expect(
      generateInferenceModel({
        model: {
          id: "fledge-alpha-free",
          providerId: "opencode-inference",
          apiFamily: "openai-chat",
          authentication: "none",
          available: true,
        },
        messages: [{ role: "user", content: "Hello" }],
        fetchImpl: async () => ({ ok: false, status: 403 }),
      }),
    ).rejects.toThrow(
      "This model is not available for external inference through this endpoint.",
    );
  });
});
