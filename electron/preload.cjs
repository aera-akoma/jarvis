const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  loadState: async () => ipcRenderer.invoke("app:load"),
  saveState: async (state) => ipcRenderer.invoke("app:save", state),
  discoverLocalModels: async () =>
    ipcRenderer.invoke("providers:discover-local"),
  executeTool: async (request) => ipcRenderer.invoke("tools:execute", request),
});
