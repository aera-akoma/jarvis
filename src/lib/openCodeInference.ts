export const OPENCODE_INFERENCE_PROVIDER_ID = "opencode-inference";
export const OPENCODE_INFERENCE_BASE_URL = "https://opencode.ai/inference";

export const buildOpenCodeInferenceProviderConfig = () => ({
  id: OPENCODE_INFERENCE_PROVIDER_ID,
  name: "OpenCode Inference",
  type: "cloud" as const,
  apiFormat: "openai-compatible" as const,
  baseUrl: OPENCODE_INFERENCE_BASE_URL,
  enabled: true,
  autoDiscovered: false,
});
