export type ModelCategory = "local" | "cloud" | "custom";
export type ProviderType = "local" | "cloud";
export type ModelApiFamily =
  | "openai-chat"
  | "openai-responses"
  | "anthropic-messages"
  | "google-generative"
  | "system-one"
  | "unknown";
export type ModelAuthentication = "none" | "api-key";

export interface ApiKey {
  id: string;
  providerId: string;
  name: string;
  secureCredentialReference: string;
  createdAt: string;
  updatedAt: string;
}

export interface Provider {
  id: string;
  name: string;
  type: ProviderType;
  apiFormat: "ollama" | "lm-studio" | "openai-compatible" | "custom";
  baseUrl: string;
  enabled: boolean;
  autoDiscovered: boolean;
  activeApiKeyId?: string;
  apiKeys: ApiKey[];
  createdAt: string;
}

export interface ModelDefinition {
  id: string;
  providerId: string;
  displayName: string;
  category: ModelCategory;
  free: boolean | "unknown";
  capabilities: string[];
  available: boolean;
  apiFormat: string;
  baseUrl?: string;
  apiFamily?: ModelApiFamily;
  endpoint?: string;
  contextLength?: number;
  pricing?: Record<string, number | string | undefined>;
  metadata?: Record<string, unknown>;
  authentication?: ModelAuthentication;
}

export interface ModelRequestMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface ModelGenerationResult {
  ok: boolean;
  modelId: string;
  providerId: string;
  content: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  createdAt: string;
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  createdAt: string;
  updatedAt: string;
  modelId?: string;
}

export interface AgentTask {
  id: string;
  objective: string;
  status: "active" | "paused" | "completed";
  progress: number;
  completed: string[];
  current: string;
  remaining: string[];
  modelHistory: string[];
  fallbackOrder: string[];
  contextSummary: string;
  lastModelId?: string;
}

export interface ProviderAdapterResult {
  ok: boolean;
  modelId: string;
  providerId: string;
  content: string;
  status:
    | "ok"
    | "rate-limit"
    | "quota-exceeded"
    | "auth-error"
    | "capability-mismatch"
    | "invalid-input";
  error?: string;
}

export interface AppState {
  providers: Provider[];
  models: ModelDefinition[];
  conversations: Conversation[];
  tasks: AgentTask[];
  selectedModelId?: string;
  currentConversationId?: string;
}

export interface ProviderDraft {
  id?: string;
  name: string;
  type: ProviderType;
  apiFormat: Provider["apiFormat"];
  baseUrl: string;
}

export interface ModelDraft {
  id?: string;
  displayName: string;
  category: ModelCategory;
  free: boolean;
  capabilities: string[];
  apiFormat: string;
  baseUrl?: string;
}
