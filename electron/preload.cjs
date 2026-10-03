const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  loadState: async () => ipcRenderer.invoke("app:load"),
  saveState: async (state) => ipcRenderer.invoke("app:save", state),
  storeCredential: async (entry) =>
    ipcRenderer.invoke("credentials:store", entry),
  deleteCredential: async (entry) =>
    ipcRenderer.invoke("credentials:delete", entry),
  testProviderConnection: async (request) =>
    ipcRenderer.invoke("providers:test-connection", request),
  discoverProviderModels: async (request) =>
    ipcRenderer.invoke("providers:discover-models", request),
  generateModel: async (request) =>
    ipcRenderer.invoke("models:generate", request),
  discoverLocalModels: async () =>
    ipcRenderer.invoke("providers:discover-local"),
  executeTool: async (request) => ipcRenderer.invoke("tools:execute", request),
});
