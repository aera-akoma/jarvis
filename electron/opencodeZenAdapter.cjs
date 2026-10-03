const BASE_URL = "https://opencode.ai/zen/v1";
const DOCS_URL = "https://opencode.ai/docs/zen/";

function htmlText(value) {
  return String(value ?? "")
    .replace(/<[^>]*>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .replace(/\s+/g, " ")
    .trim();
}

function familyForEndpoint(endpoint) {
  const path = String(endpoint ?? "")
    .toLowerCase()
    .replace(/\/$/, "");
  if (path.endsWith("/chat/completions")) return "openai-chat";
  if (path.endsWith("/responses")) return "openai-responses";
  if (path.endsWith("/messages")) return "anthropic-messages";
  if (path.includes("/models/")) return "google-generative";
  if (path.endsWith("/systemone")) return "system-one";
  return "unknown";
}

function modelNameKey(value) {
  return String(value ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");
}

function parsePrice(value) {
  const normalized = String(value ?? "").trim();
  if (/^free$/i.test(normalized)) return 0;
  const match = normalized.replace(/,/g, "").match(/^\$\s*(\d+(?:\.\d+)?)$/);
  return match ? Number(match[1]) : undefined;
}

function parseZenProtocolDocumentation(document) {
  const protocols = new Map();
  const pricingByName = new Map();
  const rows = String(document ?? "").matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/gi);

  for (const row of rows) {
    const cells = [
      ...row[1].matchAll(/<t[dh]\b[^>]*>([\s\S]*?)<\/t[dh]>/gi),
    ].map((cell) => htmlText(cell[1]));
    if (cells.length >= 3) {
      const inputPrice = parsePrice(cells[1]);
      const outputPrice = parsePrice(cells[2]);
      if (inputPrice !== undefined && outputPrice !== undefined) {
        pricingByName.set(modelNameKey(cells[0]), {
          input: inputPrice,
          output: outputPrice,
        });
      }
    }
    if (cells.length < 3) continue;

    const endpointCell = cells.find((cell) =>
      /^https:\/\/opencode\.ai\/zen\/v1\//i.test(cell),
    );
    if (!endpointCell) continue;

    const endpoint = endpointCell.match(
      /https:\/\/opencode\.ai\/zen\/v1\/[^\s|]*/i,
    )?.[0];
    if (!endpoint) continue;

    const modelId = cells.find(
      (cell) => /^[a-z0-9][a-z0-9._-]*$/i.test(cell) && cell !== "Model",
    );
    if (!modelId) continue;

    protocols.set(modelId, {
      apiFamily: familyForEndpoint(endpoint),
      endpoint,
      displayName: cells[0] || modelId,
    });
  }

  for (const [modelId, protocol] of protocols) {
    const pricing =
      pricingByName.get(modelNameKey(modelId)) ??
      pricingByName.get(modelNameKey(protocol.displayName));
    if (pricing) {
      protocol.pricing = pricing;
      protocol.free = pricing.input === 0 && pricing.output === 0;
    }
  }

  return protocols;
}

function freeFromMetadata(model) {
  if (typeof model.free === "boolean") return model.free;
  if (typeof model.is_free === "boolean") return model.is_free;
  const pricing = model.pricing ?? model.cost;
  if (!pricing || typeof pricing !== "object") return "unknown";
  const input = pricing.prompt ?? pricing.input;
  const output = pricing.completion ?? pricing.output;
  if (input === undefined || output === undefined) return "unknown";
  const inputCost = Number(input);
  const outputCost = Number(output);
  if (!Number.isFinite(inputCost) || !Number.isFinite(outputCost))
    return "unknown";
  return inputCost === 0 && outputCost === 0;
}

function normalizeZenModels(payload, protocols = new Map()) {
  const items = Array.isArray(payload?.data)
    ? payload.data
    : Array.isArray(payload?.models)
      ? payload.models
      : null;
  if (!items)
    throw new Error("OpenCode Zen returned an invalid model catalog.");

  return items.flatMap((item) => {
    const id = typeof item?.id === "string" ? item.id : "";
    if (!id) return [];
    const documented = protocols.get(id) ?? {};
    const endpoint = item.endpoint ?? documented.endpoint;
    const apiFamily =
      item.api_family ??
      item.apiFamily ??
      (endpoint
        ? familyForEndpoint(endpoint)
        : (documented.apiFamily ?? "unknown"));
    const rawCapabilities = item.capabilities ?? item.supported_capabilities;
    const capabilities = Array.isArray(rawCapabilities)
      ? rawCapabilities.map(String)
      : typeof rawCapabilities === "string"
        ? rawCapabilities.split(/[\s,]+/).filter(Boolean)
        : apiFamily === "system-one"
          ? ["structured-decision"]
          : apiFamily === "unknown"
            ? []
            : ["text"];
    const contextLength = Number(
      item.context_length ?? item.contextLength ?? item.max_input_tokens,
    );
    const pricing = item.pricing ?? item.cost ?? documented.pricing;

    return [
      {
        id,
        providerId: "opencode-zen",
        displayName:
          item.display_name ?? item.name ?? documented.displayName ?? id,
        category: "cloud",
        free:
          freeFromMetadata(item) === "unknown"
            ? (documented.free ?? "unknown")
            : freeFromMetadata(item),
        capabilities,
        available: true,
        apiFormat: "openai-compatible",
        baseUrl: BASE_URL,
        apiFamily,
        ...(endpoint ? { endpoint } : {}),
        ...(Number.isSafeInteger(contextLength) && contextLength > 0
          ? { contextLength }
          : {}),
        ...(pricing && typeof pricing === "object" ? { pricing } : {}),
        metadata: { catalog: item, documentation: documented },
      },
    ];
  });
}

function safeHttpError(status) {
  if (status === 401 || status === 403)
    return "Authentication failed. Check this API key and its access.";
  if (status === 404) return "The selected model or endpoint was not found.";
  if (status === 402)
    return "OpenCode Zen reports a billing or quota limitation.";
  if (status === 429)
    return "OpenCode Zen rate limit reached. Try again later.";
  if (status >= 500) return "OpenCode Zen is temporarily unavailable.";
  return `OpenCode Zen rejected the request (HTTP ${status}).`;
}

async function fetchWithTimeout(fetchImpl, url, options = {}) {
  try {
    return await fetchImpl(url, {
      ...options,
      signal: AbortSignal.timeout(30_000),
    });
  } catch (error) {
    if (error?.name === "TimeoutError" || error?.name === "AbortError") {
      throw new Error("OpenCode Zen request timed out.");
    }
    throw new Error(
      "Could not reach OpenCode Zen. Check your network connection.",
    );
  }
}

async function fetchZenModels({ apiKey, fetchImpl = fetch }) {
  const response = await fetchWithTimeout(fetchImpl, `${BASE_URL}/models`, {
    headers: { Authorization: `Bearer ${apiKey}`, Accept: "application/json" },
  });
  if (!response.ok) throw new Error(safeHttpError(response.status));
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error("OpenCode Zen returned malformed model data.");
  }

  let protocols = new Map();
  try {
    const docsResponse = await fetchWithTimeout(fetchImpl, DOCS_URL, {
      headers: { Accept: "text/html" },
    });
    if (docsResponse.ok) {
      protocols = parseZenProtocolDocumentation(await docsResponse.text());
    }
  } catch {
    // Catalog discovery remains useful if official protocol documentation is unavailable.
  }

  return normalizeZenModels(payload, protocols);
}

async function testZenConnection({ apiKey, fetchImpl = fetch }) {
  const response = await fetchWithTimeout(
    fetchImpl,
    `${BASE_URL}/chat/completions`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "jarvis-credential-check-nonexistent-model",
        messages: [{ role: "user", content: "Connection check" }],
        max_tokens: 1,
      }),
    },
  );
  if (response.status === 401 || response.status === 403) {
    throw new Error(
      "Authentication failed. Check this API key and its access.",
    );
  }
  if (response.status === 404) {
    return {
      ok: true,
      message:
        "OpenCode Zen connected successfully. Authentication was accepted.",
    };
  }
  if (!response.ok) throw new Error(safeHttpError(response.status));
  throw new Error(
    "OpenCode Zen accepted the probe unexpectedly. Run a normal model request to confirm connectivity.",
  );
}

function buildFamilyRequest(model, messages) {
  const endpoint = model.endpoint;
  if (!endpoint)
    throw new Error(
      "No supported endpoint metadata is available for this model.",
    );
  const url = endpoint.replace("{model}", encodeURIComponent(model.id));
  const parsed = new URL(url);
  if (parsed.protocol !== "https:" || parsed.hostname !== "opencode.ai") {
    throw new Error(
      "The model endpoint is not a trusted OpenCode Zen HTTPS endpoint.",
    );
  }

  switch (model.apiFamily) {
    case "openai-chat":
      return { url, headers: {}, body: { model: model.id, messages } };
    case "openai-responses":
      return { url, headers: {}, body: { model: model.id, input: messages } };
    case "anthropic-messages": {
      const system = messages
        .filter((message) => message.role === "system")
        .map((message) => message.content)
        .join("\n");
      return {
        url,
        headers: { "anthropic-version": "2023-06-01" },
        body: {
          model: model.id,
          max_tokens: 2048,
          ...(system ? { system } : {}),
          messages: messages.filter((message) => message.role !== "system"),
        },
      };
    }
    case "google-generative": {
      const system = messages
        .filter((message) => message.role === "system")
        .map((message) => message.content)
        .join("\n");
      return {
        url: url.endsWith(":generateContent") ? url : `${url}:generateContent`,
        headers: {},
        body: {
          contents: messages
            .filter((message) => message.role !== "system")
            .map((message) => ({
              role: message.role === "assistant" ? "model" : "user",
              parts: [{ text: message.content }],
            })),
          ...(system
            ? { systemInstruction: { parts: [{ text: system }] } }
            : {}),
        },
      };
    }
    case "system-one":
      throw new Error(
        "This model requires structured decision questions and cannot be used in text chat.",
      );
    default:
      throw new Error(
        "OpenCode Zen has not published a supported API family for this model yet.",
      );
  }
}

function extractResponseText(apiFamily, payload) {
  if (apiFamily === "openai-chat") {
    const content = payload?.choices?.[0]?.message?.content;
    return Array.isArray(content)
      ? content.map((part) => part.text ?? "").join("")
      : content;
  }
  if (apiFamily === "openai-responses") {
    return (
      payload?.output_text ??
      payload?.output
        ?.flatMap((entry) => entry.content ?? [])
        .filter((part) => part.type === "output_text" || part.type === "text")
        .map((part) => part.text ?? "")
        .join("")
    );
  }
  if (apiFamily === "anthropic-messages") {
    return payload?.content
      ?.filter((part) => part.type === "text")
      .map((part) => part.text ?? "")
      .join("");
  }
  if (apiFamily === "google-generative") {
    return payload?.candidates?.[0]?.content?.parts
      ?.map((part) => part.text ?? "")
      .join("");
  }
  return "";
}

async function generateZen({ apiKey, model, messages, fetchImpl = fetch }) {
  const request = buildFamilyRequest(model, messages);
  const response = await fetchWithTimeout(fetchImpl, request.url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(model.apiFamily === "anthropic-messages"
        ? { "x-api-key": apiKey }
        : {}),
      ...(model.apiFamily === "google-generative"
        ? { "x-goog-api-key": apiKey }
        : {}),
      ...request.headers,
    },
    body: JSON.stringify(request.body),
  });
  if (!response.ok) throw new Error(safeHttpError(response.status));
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error("OpenCode Zen returned a malformed model response.");
  }
  const content = extractResponseText(model.apiFamily, payload);
  if (typeof content !== "string" || !content.trim()) {
    throw new Error("The selected model returned no text content.");
  }
  return { ok: true, content, modelId: model.id, providerId: "opencode-zen" };
}

module.exports = {
  BASE_URL,
  buildFamilyRequest,
  familyForEndpoint,
  fetchZenModels,
  generateZen,
  normalizeZenModels,
  parseZenProtocolDocumentation,
  testZenConnection,
};
