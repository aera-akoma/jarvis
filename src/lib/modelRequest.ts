import type { ModelGenerationResult, ModelRequestMessage } from "./types";

export const generateModel = async (
  modelId: string,
  messages: ModelRequestMessage[],
  credentialId?: string,
): Promise<ModelGenerationResult> => {
  if (!window.electronAPI) {
    throw new Error("Model requests are available in the Jarvis desktop app.");
  }

  return window.electronAPI.generateModel({ modelId, messages, credentialId });
};
