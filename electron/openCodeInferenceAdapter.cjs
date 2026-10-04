const PROVIDER_ID = "opencode-inference";
const CATALOG_URL = "https://opencode.ai/inference/v1/models";
const CHAT_ENDPOINT =
  "https://opencode.ai/inference/openai/v1/chat/completions";
const RESPONSES_ENDPOINT = "https://opencode.ai/inference/openai/v1/responses";
const ANTHROPIC_ENDPOINT =
  "https://opencode.ai/inference/anthropic/v1/messages";
const GEMINI_ENDPOINT =
  "https://opencode.ai/inference/google/v1beta/models/{model}:generateContent";

const DOCUMENTED_FREE_MODELS = new Set([
  "fledge-alpha-free",
  "mimo-v2.5-free",
  "space-bunny-free",
]);

function modelFamily(modelId) {
  if (/^gpt-/i.test(modelId)) return "openai-responses";
  if (/^(claude-|qwen)/i.test(modelId)) return "anthropic-messages";
  if (/^gemini-/i.test(modelId)) return "google-generative";
  if (
    DOCUMENTED_FREE_MODELS.has(modelId) ||
    /^(kimi-|glm-|minimax-|ling-|mimo-|fledge-|nemotron-|longcat-|space-bunny-)/i.test(
      modelId,
    ) ||
    /^muse-spark-\d+\.\d+-contributor-free$/i.test(modelId) ||
    /^jev-.+-free$/i.test(modelId)
  ) {
    return "openai-chat";
  }
  return "unknown";
}

function endpointForFamily(apiFamily) {
  switch (apiFamily) {
    case "openai-chat":
      return CHAT_ENDPOINT;
    case "openai-responses":
      return RESPONSES_ENDPOINT;
    case "anthropic-messages":
      return ANTHROPIC_ENDPOINT;
    case "google-generative":
      return GEMINI_ENDPOINT;
    default:
      return undefined;
  }
}

function normalizeInferenceModels(payload) {
  const entries = Array.isArray(payload?.data)
    ? payload.data
    : Array.isArray(payload?.models)
      ? payload.models
      : null;
  if (!entries) {
    throw new Error("OpenCode Inference returned an invalid model catalog.");
  }

  return entries.flatMap((entry) => {
    const id = typeof entry?.id === "string" ? entry.id : "";
    if (!id) return [];
    const apiFamily = modelFamily(id);
    const free = DOCUMENTED_FREE_MODELS.has(id);

    return [
      {
        id,
        providerId: PROVIDER_ID,
        displayName: id,
        category: "cloud",
        free: free ? true : "unknown",
        capabilities: apiFamily === "unknown" ? [] : ["text"],
        available: true,
        apiFormat: "openai-compatible",
        baseUrl: "https://opencode.ai/inference",
        apiFamily,
        endpoint: endpointForFamily(apiFamily),
        authentication: free ? "none" : "api-key",
        metadata: { catalog: entry },
      },
    ];
  });
}

function safeStatusMessage(status) {
  if (status === 401) return "The OpenCode service-account key was rejected.";
  if (status === 403) {
    return "This model is not available for external inference through this endpoint.";
  }
  if (status === 404)
    return "The selected model was not found by OpenCode Inference.";
  if (status === 429)
    return "OpenCode Inference rate limit reached. Try again later.";
  if (status >= 500) return "OpenCode Inference is temporarily unavailable.";
  return `OpenCode Inference rejected the request (HTTP ${status}).`;
}

async function fetchWithTimeout(fetchImpl, url, options = {}) {
  try {
    return await fetchImpl(url, {
      ...options,
      signal: AbortSignal.timeout(30_000),
    });
  } catch (error) {
    if (error?.name === "TimeoutError" || error?.name === "AbortError") {
      throw new Error("OpenCode Inference request timed out.");
    }
    throw new Error(
      "Could not reach OpenCode Inference. Check your network connection.",
    );
  }
}

async function discoverInferenceModels({ fetchImpl = fetch } = {}) {
  const response = await fetchWithTimeout(fetchImpl, CATALOG_URL, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(safeStatusMessage(response.status));
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error("OpenCode Inference returned malformed catalog data.");
  }
  return normalizeInferenceModels(payload);
}

function safeProviderMessage(message, apiKey) {
  let safeMessage = String(message ?? "");
  if (apiKey) safeMessage = safeMessage.split(apiKey).join("[REDACTED]");
  return safeMessage
    .replace(/(bearer\s+)[^\s,;"'}]+/gi, "$1[REDACTED]")
    .replace(/\b(?:sk|opk|zen)[_-][A-Za-z0-9_-]{8,}\b/gi, "[REDACTED]")
    .replace(/[\r\n\t]+/g, " ")
    .slice(0, 300);
}

async function generateInferenceModel({
  model,
  messages,
  apiKey,
  fetchImpl = fetch,
}) {
  if (!model?.available) {
    throw new Error("The selected OpenCode Inference model is unavailable.");
  }
  if (model.providerId !== PROVIDER_ID) {
    throw new Error("The selected model is not an OpenCode Inference model.");
  }
  if (model.apiFamily !== "openai-chat") {
    throw new Error(
      "This model family is discovered but not yet supported by Jarvis.",
    );
  }
  if (!Array.isArray(messages) || messages.length === 0) {
    throw new Error("Enter a message before sending.");
  }
  if (model.authentication !== "none" && !apiKey) {
    throw new Error("Add an OpenCode service-account key for this model.");
  }

  const endpoint = model.endpoint ?? CHAT_ENDPOINT;
  const endpointUrl = new URL(endpoint);
  if (
    endpointUrl.protocol !== "https:" ||
    endpointUrl.hostname !== "opencode.ai" ||
    endpoint !== CHAT_ENDPOINT
  ) {
    throw new Error(
      "The model does not have a trusted OpenAI Chat Completions endpoint.",
    );
  }

  const headers = {
    Accept: "application/json",
    "Content-Type": "application/json",
  };
  if (model.authentication !== "none") {
    headers.Authorization = `Bearer ${apiKey}`;
  }

  const response = await fetchWithTimeout(fetchImpl, endpoint, {
    method: "POST",
    headers,
    body: JSON.stringify({ model: model.id, messages }),
  });
  if (!response.ok) throw new Error(safeStatusMessage(response.status));

  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error("OpenCode Inference returned a malformed model response.");
  }

  const content = payload?.choices?.[0]?.message?.content;
  const normalizedContent = Array.isArray(content)
    ? content.map((part) => part?.text ?? "").join("")
    : content;
  if (typeof normalizedContent !== "string" || !normalizedContent.trim()) {
    throw new Error("OpenCode Inference returned no text content.");
  }

  return {
    ok: true,
    providerId: PROVIDER_ID,
    modelId: model.id,
    content: normalizedContent,
  };
}

module.exports = {
  CATALOG_URL,
  CHAT_ENDPOINT,
  PROVIDER_ID,
  discoverInferenceModels,
  generateInferenceModel,
  normalizeInferenceModels,
  safeProviderMessage,
};
