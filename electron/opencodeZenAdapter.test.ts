import { createRequire } from "node:module";
import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);
const {
  buildFamilyRequest,
  normalizeZenModels,
  parseZenProtocolDocumentation,
  generateZen,
  testZenConnection,
} = require("./opencodeZenAdapter.cjs") as {
  buildFamilyRequest: (model: any, messages: any[]) => any;
  normalizeZenModels: (payload: any, protocols?: Map<string, any>) => any[];
  parseZenProtocolDocumentation: (document: string) => Map<string, any>;
  generateZen: (request: any) => Promise<any>;
  testZenConnection: (request: any) => Promise<any>;
};

describe("OpenCode Zen main-process adapter", () => {
  it("uses model IDs and endpoint families from the live catalog and official docs", () => {
    const protocols = parseZenProtocolDocumentation(`
      <table><tbody>
        <tr><td>New Model</td><td><code>new-model-v2</code></td>
          <td><code>https://opencode.ai/zen/v1/responses</code></td>
          <td><code>@ai-sdk/openai</code></td></tr>
      </tbody></table>
    `);
    const models = normalizeZenModels(
      {
        object: "list",
        data: [
          {
            id: "new-model-v2",
            object: "model",
            created: 123,
            owned_by: "opencode",
          },
        ],
      },
      protocols,
    );

    expect(models).toHaveLength(1);
    expect(models[0]).toMatchObject({
      id: "new-model-v2",
      displayName: "New Model",
      apiFamily: "openai-responses",
      endpoint: "https://opencode.ai/zen/v1/responses",
      free: "unknown",
    });
  });

  it("does not infer free access from an ID suffix", () => {
    const [model] = normalizeZenModels({ data: [{ id: "future-free-model" }] });
    expect(model.free).toBe("unknown");
    expect(model.capabilities).toEqual([]);
  });

  it("uses current published pricing metadata instead of model-name heuristics", () => {
    const protocols = parseZenProtocolDocumentation(`
      <table><tbody>
        <tr><td>Alpha Model</td><td>alpha-model</td>
          <td>https://opencode.ai/zen/v1/chat/completions</td>
          <td>@ai-sdk/openai-compatible</td></tr>
      </tbody></table>
      <table><tbody>
        <tr><td>Alpha Model</td><td>Free</td><td>Free</td><td>Free</td><td>-</td></tr>
      </tbody></table>
    `);
    const [model] = normalizeZenModels(
      { data: [{ id: "alpha-model" }] },
      protocols,
    );

    expect(model.free).toBe(true);
    expect(model.pricing).toEqual({ input: 0, output: 0 });
  });

  it("builds protocol-specific requests rather than sending every model to chat completions", () => {
    const request = buildFamilyRequest(
      {
        id: "claude-new",
        apiFamily: "anthropic-messages",
        endpoint: "https://opencode.ai/zen/v1/messages",
      },
      [
        { role: "system", content: "Be concise." },
        { role: "user", content: "Hello" },
      ],
    );

    expect(request.url).toBe("https://opencode.ai/zen/v1/messages");
    expect(request.body).toMatchObject({
      model: "claude-new",
      system: "Be concise.",
      messages: [{ role: "user", content: "Hello" }],
    });
    expect(request.headers["anthropic-version"]).toBeTruthy();
  });

  it("routes documented per-model Google endpoints to generateContent", () => {
    const protocols = parseZenProtocolDocumentation(`
      <table><tbody><tr>
        <td>Gemini Preview</td><td>gemini-preview</td>
        <td>https://opencode.ai/zen/v1/models/gemini-preview</td>
        <td>@ai-sdk/google</td>
      </tr></tbody></table>
    `);
    const [model] = normalizeZenModels(
      { data: [{ id: "gemini-preview" }] },
      protocols,
    );
    const request = buildFamilyRequest(model, [
      { role: "user", content: "Hello" },
    ]);

    expect(model.apiFamily).toBe("google-generative");
    expect(request.url).toBe(
      "https://opencode.ai/zen/v1/models/gemini-preview:generateContent",
    );
  });

  it("verifies authentication without accepting the public models list as proof", async () => {
    let probeUrl = "";
    let probeBody: any;
    const result = await testZenConnection({
      apiKey: "test-key",
      fetchImpl: async (url: string, options: any) => {
        probeUrl = url;
        probeBody = JSON.parse(options.body);
        return { ok: false, status: 404 };
      },
    });

    expect(probeUrl).toBe("https://opencode.ai/zen/v1/chat/completions");
    expect(probeBody.model).toBe("jarvis-credential-check-nonexistent-model");
    expect(result.ok).toBe(true);
  });

  it("reports authentication failure without returning raw provider details", async () => {
    await expect(
      testZenConnection({
        apiKey: "must-not-appear",
        fetchImpl: async () => ({ ok: false, status: 401 }),
      }),
    ).rejects.toThrow(
      "Authentication failed. Check this API key and its access.",
    );
  });

  it("returns unified text from an OpenAI-compatible response", async () => {
    const result = await generateZen({
      apiKey: "must-not-be-returned",
      model: {
        id: "dynamic-model",
        apiFamily: "openai-chat",
        endpoint: "https://opencode.ai/zen/v1/chat/completions",
      },
      messages: [{ role: "user", content: "Hello" }],
      fetchImpl: async () => ({
        ok: true,
        json: async () => ({
          choices: [{ message: { content: "Hi there." } }],
        }),
      }),
    });

    expect(result).toMatchObject({
      content: "Hi there.",
      providerId: "opencode-zen",
    });
    expect(JSON.stringify(result)).not.toContain("must-not-be-returned");
  });
});
