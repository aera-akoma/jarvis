/// <reference types="vite/client" />

import type {
  AppState,
  ModelDefinition,
  ModelGenerationResult,
  ModelRequestMessage,
} from "./lib/types";

declare global {
  interface Window {
    electronAPI?: {
      loadState: () => Promise<AppState>;
      saveState: (state: AppState) => Promise<AppState>;
      storeCredential: (entry: {
        credentialId: string;
        providerId: string;
        secret: string;
      }) => Promise<{ ok: boolean }>;
      deleteCredential: (entry: {
        credentialId: string;
        providerId: string;
      }) => Promise<{ ok: boolean }>;
      testProviderConnection: (request: {
        providerId: string;
        credentialId?: string;
      }) => Promise<{ ok: boolean; message: string; count?: number }>;
      discoverProviderModels: (request: {
        providerId: string;
        credentialId?: string;
      }) => Promise<Array<Partial<ModelDefinition>>>;
      generateModel: (request: {
        modelId: string;
        messages: ModelRequestMessage[];
        credentialId?: string;
      }) => Promise<ModelGenerationResult>;
      discoverLocalModels: () => Promise<Array<Partial<ModelDefinition>>>;
      executeTool: (request: any) => Promise<any>;
    };
  }
}

export {};
