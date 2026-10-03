export const OPENCODE_PROVIDER_ID = "opencode-zen";
export const OPENCODE_BASE_URL = "https://opencode.ai/zen/v1";

export const buildProviderConfig = () => ({
  id: OPENCODE_PROVIDER_ID,
  name: "OpenCode Zen",
  type: "cloud" as const,
  apiFormat: "openai-compatible" as const,
  baseUrl: OPENCODE_BASE_URL,
  enabled: true,
  autoDiscovered: false,
});
