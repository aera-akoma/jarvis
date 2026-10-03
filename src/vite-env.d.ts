/// <reference types="vite/client" />

declare global {
  interface Window {
    electronAPI?: {
      loadState: () => Promise<any>;
      saveState: (state: any) => Promise<void>;
      discoverLocalModels: () => Promise<any[]>;
      executeTool: (request: any) => Promise<any>;
    };
  }
}

export {};
