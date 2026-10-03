import type { ModelDefinition } from "./types";

export const OPENCODE_PROVIDER_ID = "opencode-zen";
export const OPENCODE_BASE_URL = "https://opencode.ai/zen/v1";

export interface OpenCodeZenModelLike {
  id?: string;
  model?: string;
  name?: string;
  free?: boolean;
  is_free?: boolean;
  pricing?: {
    prompt?: number;
    completion?: number;
    input?: number;
    output?: number;
  };
  cost?: {
    prompt?: number;
    completion?: number;
    input?: number;
    output?: number;
  };
  capabilities?: string[] | string;
  owned_by?: string;
  description?: string;
}

export const buildProviderConfig = () => ({
  id: OPENCODE_PROVIDER_ID,
  name: "OpenCode Zen",
  type: "cloud" as const,
  apiFormat: "openai-compatible" as const,
  baseUrl: OPENCODE_BASE_URL,
  enabled: true,
  autoDiscovered: false,
});

export const normalizeModelName = (value: string) =>
  String(value ?? "")
    .replace(/[-_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();

export const isOpenCodeZenFreeModel = (
  model: Partial<OpenCodeZenModelLike> = {},
): boolean => {
  if (typeof model.free === "boolean") {
    return model.free;
  }

  if (typeof model.is_free === "boolean") {
    return model.is_free;
  }

  const pricing = model.pricing ?? model.cost;
  if (pricing && typeof pricing === "object") {
    const prompt = Number(pricing.prompt ?? pricing.input ?? 0);
    const completion = Number(pricing.completion ?? pricing.output ?? 0);
    if (Number.isFinite(prompt) && Number.isFinite(completion)) {
      return prompt === 0 && completion === 0;
    }
  }

  const modelId = String(model.id ?? model.name ?? "").toLowerCase();
  return /free/i.test(modelId);
};

export const extractOpenCodeZenModels = (
  payload: any,
): Array<Partial<ModelDefinition>> => {
  const items = Array.isArray(payload?.data)
    ? payload.data
    : Array.isArray(payload?.models)
      ? payload.models
      : [];

  return items.map((item: OpenCodeZenModelLike, index: number) => {
    const rawId = String(item?.id ?? item?.model ?? `opencode-model-${index}`);
    const capabilities = Array.isArray(item?.capabilities)
      ? item.capabilities
      : typeof item?.capabilities === "string"
        ? item.capabilities
            .split(",")
            .map((capability) => capability.trim())
            .filter(Boolean)
        : ["text", "chat", "cloud"];

    return {
      id: rawId,
      providerId: OPENCODE_PROVIDER_ID,
      displayName: normalizeModelName(rawId),
      category: "cloud",
      free: isOpenCodeZenFreeModel(item),
      capabilities,
      available: true,
      apiFormat: "openai-compatible",
      baseUrl: OPENCODE_BASE_URL,
    };
  });
};

export const fetchOpenCodeZenModels = async (apiKey: string) => {
  if (!apiKey || !apiKey.trim()) {
    throw new Error("OpenCode Zen API key required.");
  }

  const response = await fetch(`${OPENCODE_BASE_URL}/models`, {
    headers: {
      Authorization: `Bearer ${apiKey}`,
      Accept: "application/json",
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    const bodyText = await response.text();
    throw new Error(
      `OpenCode Zen model fetch failed (${response.status}). ${bodyText || "Unable to load model catalog."}`,
    );
  }

  const payload = await response.json();
  return extractOpenCodeZenModels(payload);
};

export const testOpenCodeZenConnection = async (apiKey: string) => {
  const models = await fetchOpenCodeZenModels(apiKey);
  return {
    ok: models.length > 0,
    message:
      models.length > 0
        ? `OpenCode Zen is reachable and discovered ${models.length} models.`
        : "OpenCode Zen responded, but no models were returned.",
    count: models.length,
  };
};

export const executeOpenCodeZenChat = async (
  apiKey: string,
  modelId: string,
  message: string,
) => {
  if (!apiKey || !apiKey.trim()) {
    throw new Error("OpenCode Zen API key required.");
  }

  const response = await fetch(`${OPENCODE_BASE_URL}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: modelId,
      messages: [{ role: "user", content: message }],
      max_tokens: 128,
      temperature: 0.2,
    }),
  });

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(
      `OpenCode Zen chat failed (${response.status}). ${errorBody || "Model request was rejected."}`,
    );
  }

  const payload = await response.json();
  const choices = Array.isArray(payload?.choices) ? payload.choices : [];
  const first = choices[0];
  const text =
    first?.message?.content ??
    first?.delta?.content ??
    "OpenCode Zen returned a response without content.";

  return {
    ok: true,
    content: Array.isArray(text) ? text.join("") : String(text),
    raw: payload,
  };
};
