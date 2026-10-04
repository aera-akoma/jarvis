import type {
  AppState,
  ApiKey,
  ModelDefinition,
  ModelDraft,
  Provider,
  ProviderDraft,
} from "./types";
import { buildProviderConfig } from "./opencodeZen";
import { buildOpenCodeInferenceProviderConfig } from "./openCodeInference";

const uid = (prefix: string) =>
  `${prefix}-${Math.random().toString(36).slice(2, 10)}-${Date.now().toString(36)}`;

export const buildInitialState = (): AppState => ({
  providers: [
    {
      id: "ollama",
      name: "Ollama",
      type: "local",
      apiFormat: "ollama",
      baseUrl: "http://localhost:11434",
      enabled: true,
      autoDiscovered: true,
      apiKeys: [],
      createdAt: new Date().toISOString(),
    },
    {
      id: "openai",
      name: "OpenAI",
      type: "cloud",
      apiFormat: "openai-compatible",
      baseUrl: "https://api.openai.com/v1",
      enabled: true,
      autoDiscovered: false,
      activeApiKeyId: undefined,
      apiKeys: [],
      createdAt: new Date().toISOString(),
    },
    {
      ...buildProviderConfig(),
      enabled: true,
      autoDiscovered: false,
      activeApiKeyId: undefined,
      apiKeys: [],
      createdAt: new Date().toISOString(),
    },
    {
      ...buildOpenCodeInferenceProviderConfig(),
      enabled: true,
      autoDiscovered: false,
      activeApiKeyId: undefined,
      apiKeys: [],
      createdAt: new Date().toISOString(),
    },
  ],
  models: [
    {
      id: "qwen3-local",
      providerId: "ollama",
      displayName: "Qwen 3",
      category: "local",
      free: true,
      capabilities: ["text", "reasoning", "local"],
      available: true,
      apiFormat: "ollama",
      baseUrl: "http://localhost:11434",
    },
    {
      id: "gpt-4o-mini",
      providerId: "openai",
      displayName: "GPT-4o Mini",
      category: "cloud",
      free: false,
      capabilities: ["text", "tool-calling", "structured-output"],
      available: true,
      apiFormat: "openai-compatible",
      baseUrl: "https://api.openai.com/v1",
    },
  ],
  conversations: [],
  tasks: [],
  selectedModelId: "qwen3-local",
  currentConversationId: undefined,
});

export const addProvider = (
  state: AppState,
  providerDraft: ProviderDraft,
): Provider => {
  const provider: Provider = {
    id: providerDraft.id ?? uid("provider"),
    name: providerDraft.name,
    type: providerDraft.type,
    apiFormat: providerDraft.apiFormat,
    baseUrl: providerDraft.baseUrl,
    enabled: true,
    autoDiscovered: false,
    apiKeys: [],
    createdAt: new Date().toISOString(),
  };

  state.providers.push(provider);
  return provider;
};

export const addApiKey = (
  state: AppState,
  providerId: string,
  keyDraft: { id: string; name: string; secureCredentialReference: string },
): ApiKey => {
  const provider = state.providers.find((entry) => entry.id === providerId);

  if (!provider) {
    throw new Error(`Provider ${providerId} was not found`);
  }

  const apiKey: ApiKey = {
    id: keyDraft.id,
    providerId,
    name: keyDraft.name,
    secureCredentialReference: keyDraft.secureCredentialReference,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };

  provider.apiKeys.push(apiKey);
  if (!provider.activeApiKeyId) {
    provider.activeApiKeyId = apiKey.id;
  }

  return apiKey;
};

export const setActiveApiKey = (
  state: AppState,
  providerId: string,
  apiKeyId: string,
) => {
  const provider = state.providers.find((entry) => entry.id === providerId);
  if (!provider) {
    throw new Error(`Provider ${providerId} was not found`);
  }

  if (!provider.apiKeys.some((key) => key.id === apiKeyId)) {
    throw new Error(
      `Credential ${apiKeyId} was not found for provider ${providerId}`,
    );
  }

  provider.activeApiKeyId = apiKeyId;
};

export const addManualModel = (
  state: AppState,
  providerId: string,
  draft: ModelDraft,
): ModelDefinition => {
  const normalized: ModelDefinition = {
    id: draft.id ?? uid("model"),
    providerId,
    displayName: draft.displayName,
    category: draft.category,
    free: draft.free,
    capabilities: draft.capabilities,
    available: true,
    apiFormat: draft.apiFormat,
    baseUrl: draft.baseUrl,
  };

  state.models.push(normalized);
  if (!state.selectedModelId) {
    state.selectedModelId = normalized.id;
  }

  return normalized;
};

export const getFilteredModels = (
  state: AppState,
  options: {
    freeOnly?: boolean;
    category?: ModelDefinition["category"];
    providerId?: string;
  } = {},
) => {
  let models = [...state.models];

  if (options.freeOnly) {
    models = models.filter((model) => model.free === true);
  }

  if (options.category) {
    models = models.filter((model) => model.category === options.category);
  }

  if (options.providerId) {
    models = models.filter((model) => model.providerId === options.providerId);
  }

  return models;
};

export const getProviderById = (state: AppState, providerId: string) =>
  state.providers.find((provider) => provider.id === providerId);

export const addDiscoveredModels = (
  state: AppState,
  providerId: string,
  discovered: Array<Partial<ModelDefinition>>,
) => {
  const provider = getProviderById(state, providerId);
  if (!provider) {
    throw new Error(`Provider ${providerId} was not found`);
  }

  const discoveredIds = new Set(
    discovered
      .map((model) => model.id)
      .filter((entry): entry is string => typeof entry === "string"),
  );

  state.models = state.models.map((model) =>
    model.providerId === providerId
      ? { ...model, available: discoveredIds.has(model.id) }
      : model,
  );

  for (const discoveredModel of discovered) {
    const model: ModelDefinition = {
      id: discoveredModel.id ?? uid("local-model"),
      providerId,
      displayName: discoveredModel.displayName ?? discoveredModel.id ?? "Model",
      category:
        discoveredModel.category ??
        (provider.type === "local" ? "local" : "cloud"),
      free: discoveredModel.free ?? "unknown",
      capabilities: discoveredModel.capabilities ?? [],
      available: discoveredModel.available ?? true,
      apiFormat: discoveredModel.apiFormat ?? provider.apiFormat,
      baseUrl: discoveredModel.baseUrl ?? provider.baseUrl,
      ...discoveredModel,
    };

    const existingIndex = state.models.findIndex(
      (entry) => entry.providerId === providerId && entry.id === model.id,
    );

    if (existingIndex >= 0) {
      state.models[existingIndex] = {
        ...state.models[existingIndex],
        ...model,
        available: discoveredModel.available ?? true,
      };
    } else {
      state.models.push(model);
    }
  }

  if (!state.selectedModelId && state.models.length) {
    state.selectedModelId = state.models[0].id;
  }
};
