const zen = require("./opencodeZenAdapter.cjs");

function safeStatusMessage(status) {
  if (status === 401 || status === 403)
    return "Authentication failed. Check the selected API key.";
  if (status === 404) return "The model or provider endpoint was not found.";
  if (status === 402)
    return "The provider reports a billing or quota limitation.";
  if (status === 429)
    return "The provider rate limit was reached. Try again later.";
  if (status >= 500) return "The provider is temporarily unavailable.";
  return `The provider rejected the request (HTTP ${status}).`;
}

async function request(fetchImpl, url, options = {}) {
  let response;
  try {
    response = await fetchImpl(url, {
      ...options,
      signal: AbortSignal.timeout(30_000),
    });
  } catch (error) {
    if (error?.name === "TimeoutError" || error?.name === "AbortError") {
      throw new Error("The provider request timed out.");
    }
    throw new Error("Could not reach the provider. Check the connection.");
  }
  if (!response.ok) throw new Error(safeStatusMessage(response.status));
  return response;
}

function providerBaseUrl(provider, model) {
  const value = model.baseUrl ?? provider.baseUrl;
  const url = new URL(value);
  if (provider.type === "cloud" && url.protocol !== "https:") {
    throw new Error("Cloud provider connections must use HTTPS.");
  }
  if (
    provider.type === "local" &&
    !["http:", "https:"].includes(url.protocol)
  ) {
    throw new Error("The local provider URL is invalid.");
  }
  return value.replace(/\/$/, "");
}

function openAIChatUrl(baseUrl) {
  return `${baseUrl}/chat/completions`;
}

async function testConnection({ provider, apiKey, fetchImpl = fetch }) {
  if (!provider?.enabled) throw new Error("This provider is disabled.");
  if (provider.id === "opencode-zen") {
    if (!apiKey) throw new Error("Add an OpenCode Zen API key first.");
    return zen.testZenConnection({ apiKey, fetchImpl });
  }

  const baseUrl = provider.baseUrl.replace(/\/$/, "");
  const url =
    provider.apiFormat === "ollama"
      ? `${baseUrl}/api/tags`
      : `${baseUrl}/models`;
  await request(fetchImpl, url, {
    headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : {},
  });
  return { ok: true, message: `${provider.name} connected successfully.` };
}

async function discoverModels({ provider, apiKey, fetchImpl = fetch }) {
  if (provider.id !== "opencode-zen") {
    throw new Error(
      "Dynamic cloud discovery is not supported for this provider.",
    );
  }
  if (!apiKey) throw new Error("Add an OpenCode Zen API key first.");
  return zen.fetchZenModels({ apiKey, fetchImpl });
}

async function generateModel({
  provider,
  model,
  messages,
  apiKey,
  fetchImpl = fetch,
}) {
  if (!provider?.enabled) throw new Error("This provider is disabled.");
  if (!model?.available)
    throw new Error("The selected model is currently unavailable.");
  if (!Array.isArray(messages) || !messages.length)
    throw new Error("Enter a message before sending.");

  if (provider.id === "opencode-zen") {
    if (!apiKey)
      throw new Error("Add or select an OpenCode Zen API key first.");
    return zen.generateZen({ apiKey, model, messages, fetchImpl });
  }

  const baseUrl = providerBaseUrl(provider, model);
  if (provider.apiFormat === "ollama") {
    const response = await request(fetchImpl, `${baseUrl}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: model.id.replace(/^ollama:/, ""),
        messages,
        stream: false,
      }),
    });
    let payload;
    try {
      payload = await response.json();
    } catch {
      throw new Error("The local model returned malformed data.");
    }
    const content = payload?.message?.content;
    if (typeof content !== "string" || !content.trim()) {
      throw new Error("The selected model returned no text content.");
    }
    return { ok: true, content, modelId: model.id, providerId: provider.id };
  }

  if (provider.type === "cloud" && !apiKey) {
    throw new Error(
      `Add an API key for ${provider.name} before sending a message.`,
    );
  }
  const response = await request(fetchImpl, openAIChatUrl(baseUrl), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
    },
    body: JSON.stringify({ model: model.id, messages }),
  });
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error("The provider returned malformed model data.");
  }
  const content = payload?.choices?.[0]?.message?.content;
  if (typeof content !== "string" || !content.trim()) {
    throw new Error("The selected model returned no text content.");
  }
  return { ok: true, content, modelId: model.id, providerId: provider.id };
}

module.exports = { discoverModels, generateModel, testConnection };
