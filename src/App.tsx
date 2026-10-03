import { useEffect, useMemo, useRef, useState } from "react";
import {
  addApiKey,
  addDiscoveredModels,
  addManualModel,
  addProvider,
  buildInitialState,
  getFilteredModels,
  getProviderById,
  setActiveApiKey,
} from "./lib/modelRegistry";
import {
  buildFallbackOrder,
  createTaskState,
  runModelSwitchSequence,
  simulateProviderRequest,
  validateModelCapabilities,
} from "./lib/agentRuntime";
import { buildProviderConfig, OPENCODE_PROVIDER_ID } from "./lib/opencodeZen";
import { generateModel } from "./lib/modelRequest";
import { buildResearchPlan, summarizeDocument } from "./lib/research";
import { MemoryStore, suggestSkills } from "./lib/memory";
import {
  buildSearchUrl,
  canExecuteTool,
  type ToolRequest,
} from "./lib/tooling";
import type { AgentTask, AppState, ProviderDraft } from "./lib/types";
import "./App.css";

const uid = (prefix: string) =>
  `${prefix}-${Math.random().toString(36).slice(2, 10)}-${Date.now().toString(36)}`;

const sanitizeStateForStorage = (nextState: AppState) => {
  const clone = JSON.parse(JSON.stringify(nextState));
  clone.providers = (clone.providers ?? []).map((provider: any) => ({
    ...provider,
    apiKeys: (provider.apiKeys ?? []).map((key: any) => {
      const { value: _legacySecret, ...metadata } = key;
      return metadata;
    }),
  }));
  return clone;
};

const defaultProviderDraft: ProviderDraft = {
  name: "",
  type: "cloud",
  apiFormat: "openai-compatible",
  baseUrl: "https://example.com/v1",
};

const defaultModelDraft: {
  providerId: string;
  displayName: string;
  category: "local" | "cloud" | "custom";
  free: boolean;
  capabilities: string[];
  apiFormat: string;
  baseUrl: string;
} = {
  providerId: "",
  displayName: "",
  category: "custom",
  free: true,
  capabilities: ["text"],
  apiFormat: "openai-compatible",
  baseUrl: "https://example.com/v1",
};

const loadSavedState = async (): Promise<AppState> => {
  if (window.electronAPI) {
    const state = await window.electronAPI.loadState();
    if (state && state.providers?.length) {
      const sanitized = sanitizeStateForStorage(state);
      window.localStorage.setItem("aera-state", JSON.stringify(sanitized));
      return sanitized;
    }
  }

  const saved = window.localStorage.getItem("aera-state");
  if (saved) {
    try {
      const parsed = JSON.parse(saved) as AppState;
      return sanitizeStateForStorage(parsed);
    } catch {
      return buildInitialState();
    }
  }

  return buildInitialState();
};

function App() {
  const [state, setState] = useState<AppState>(buildInitialState());
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [providerDraft, setProviderDraft] =
    useState<ProviderDraft>(defaultProviderDraft);
  const [selectedProviderId, setSelectedProviderId] = useState("openai");
  const [apiKeyName, setApiKeyName] = useState("Personal GPT");
  const apiKeyValueRef = useRef<HTMLInputElement>(null);
  const [modelDraft, setModelDraft] = useState({
    ...defaultModelDraft,
    providerId: "openai",
  });
  const [messageDraft, setMessageDraft] = useState(
    "Analyze this PDF and prepare detailed notes.",
  );
  const [freeOnly, setFreeOnly] = useState(false);
  const [modelFilter, setModelFilter] = useState<
    "all" | "free" | "local" | "cloud" | "vision" | "tools" | "reasoning"
  >("all");
  const [modelSearch, setModelSearch] = useState("");
  const [zenConnectionStatus, setZenConnectionStatus] = useState("Not tested");
  const [status, setStatus] = useState("Ready");
  const [toolApproved, setToolApproved] = useState(false);
  const [toolConsole, setToolConsole] = useState<string[]>(["Tooling ready."]);
  const [researchDraft, setResearchDraft] = useState(
    "AI in education and research workflows",
  );
  const [researchPlan, setResearchPlan] = useState(() =>
    buildResearchPlan("AI in education and research workflows"),
  );
  const [memoryDraft, setMemoryDraft] = useState(
    "Local Ollama is the default safe model for offline review.",
  );
  const [memoryStore, setMemoryStore] = useState(() => new MemoryStore());
  const [task, setTask] = useState<AgentTask>(() =>
    createTaskState(
      "Continue the research and reporting workflow without restarting the task.",
      "qwen3-local",
    ),
  );

  useEffect(() => {
    void (async () => {
      const initial = await loadSavedState();
      setState(initial);
      setSelectedProviderId(initial.providers[0]?.id ?? "openai");
      setModelDraft((current) => ({
        ...current,
        providerId: initial.providers[0]?.id ?? "openai",
      }));
    })();
  }, []);

  const persistState = async (nextState: AppState) => {
    const safeState = sanitizeStateForStorage(nextState);
    setState(safeState);
    window.localStorage.setItem("aera-state", JSON.stringify(safeState));
    if (window.electronAPI) {
      await window.electronAPI.saveState(safeState);
    }
  };

  const currentConversation =
    state.conversations.find(
      (conversation) => conversation.id === state.currentConversationId,
    ) ?? state.conversations[state.conversations.length - 1];

  const selectedModel =
    state.models.find((model) => model.id === state.selectedModelId) ??
    state.models[0] ??
    null;

  const filteredModels = useMemo(() => {
    const current =
      modelFilter === "free"
        ? getFilteredModels(state, { freeOnly: true })
        : modelFilter === "local"
          ? getFilteredModels(state, { category: "local" })
          : modelFilter === "cloud"
            ? getFilteredModels(state, { category: "cloud" })
            : getFilteredModels(state);
    const withCapability = ["vision", "tools", "reasoning"].includes(
      modelFilter,
    )
      ? current.filter((model) =>
          model.capabilities.some((capability) => {
            const normalized = capability.toLowerCase();
            return modelFilter === "tools"
              ? normalized.includes("tool") || normalized.includes("function")
              : normalized.includes(modelFilter);
          }),
        )
      : current;

    const trimmed = modelSearch.trim().toLowerCase();
    if (!trimmed) {
      return withCapability;
    }

    return withCapability.filter((model) =>
      model.displayName.toLowerCase().includes(trimmed),
    );
  }, [modelFilter, modelSearch, state]);

  const ensureOpenCodeZenProvider = async () => {
    const existing = getProviderById(state, "opencode-zen");
    if (existing) {
      return existing;
    }

    const nextState = { ...state };
    const provider = addProvider(nextState, {
      ...buildProviderConfig(),
      id: "opencode-zen",
      name: "OpenCode Zen",
      type: "cloud",
      apiFormat: "openai-compatible",
      baseUrl: "https://opencode.ai/zen/v1",
    });

    await persistState(nextState);
    setSelectedProviderId(provider.id);
    return provider;
  };

  const handleRefreshOpenCodeModels = async () => {
    const provider = await ensureOpenCodeZenProvider();
    if (!window.electronAPI) {
      setStatus(
        "OpenCode Zen discovery is available in the Jarvis desktop app.",
      );
      return;
    }
    if (!provider.activeApiKeyId) {
      setStatus("Add an OpenCode Zen API key before refreshing the catalog.");
      return;
    }

    try {
      const discovered = await window.electronAPI.discoverProviderModels({
        providerId: provider.id,
        credentialId: provider.activeApiKeyId,
      });
      const nextState = { ...state };
      addDiscoveredModels(nextState, provider.id, discovered);
      await persistState(nextState);
      setZenConnectionStatus("Connected");
      setStatus(`Loaded ${discovered.length} OpenCode Zen models.`);
    } catch (error) {
      setZenConnectionStatus("Disconnected");
      setStatus(
        error instanceof Error
          ? error.message
          : "OpenCode Zen discovery failed.",
      );
    }
  };

  const handleOpenCodeTest = async () => {
    const provider = await ensureOpenCodeZenProvider();
    if (!window.electronAPI) {
      setStatus("Connection testing is available in the Jarvis desktop app.");
      return;
    }
    if (!provider.activeApiKeyId) {
      setStatus("Add an OpenCode Zen API key to test connectivity.");
      return;
    }

    try {
      const result = await window.electronAPI.testProviderConnection({
        providerId: provider.id,
        credentialId: provider.activeApiKeyId,
      });
      setZenConnectionStatus("Connected");
      setStatus(result.message);
    } catch (error) {
      setZenConnectionStatus("Disconnected");
      setStatus(
        error instanceof Error
          ? error.message
          : "OpenCode Zen connection test failed.",
      );
    }
  };

  const addProviderEntry = async () => {
    if (!providerDraft.name.trim()) {
      setStatus("Provider name is required.");
      return;
    }

    const nextState = { ...state };
    const provider = addProvider(nextState, {
      ...providerDraft,
      name: providerDraft.name.trim(),
      baseUrl: providerDraft.baseUrl.trim() || "https://example.com/v1",
    });
    setSelectedProviderId(provider.id);
    setModelDraft((current) => ({
      ...current,
      providerId: provider.id,
      apiFormat: provider.apiFormat,
      baseUrl: provider.baseUrl,
    }));
    await persistState(nextState);
    setProviderDraft(defaultProviderDraft);
    setStatus(`Added provider: ${provider.name}`);
  };

  const addApiKeyEntry = async () => {
    const provider = getProviderById(state, selectedProviderId);
    if (!provider) {
      setStatus("Select a provider before adding the key.");
      return;
    }

    const secret = apiKeyValueRef.current?.value.trim() ?? "";
    if (!apiKeyName.trim() || !secret) {
      setStatus("Key name and value are required.");
      return;
    }
    if (!window.electronAPI) {
      setStatus(
        "Secure API-key storage is available in the Jarvis desktop app.",
      );
      return;
    }

    const credentialId = uid("credential");
    if (apiKeyValueRef.current) apiKeyValueRef.current.value = "";
    try {
      await window.electronAPI.storeCredential({
        credentialId,
        providerId: provider.id,
        secret,
      });
      const nextState = { ...state };
      addApiKey(nextState, provider.id, {
        id: credentialId,
        name: apiKeyName.trim(),
        secureCredentialReference: credentialId,
      });
      await persistState(nextState);
      setApiKeyName("Personal Key");
      setStatus(`Stored ${provider.name} credential securely.`);
    } catch (error) {
      await window.electronAPI.deleteCredential({
        credentialId,
        providerId: provider.id,
      });
      setStatus(
        error instanceof Error
          ? error.message
          : "Could not store API key securely.",
      );
    }
  };

  const updateActiveKey = async (providerId: string, keyId: string) => {
    const nextState = { ...state };
    setActiveApiKey(nextState, providerId, keyId);
    await persistState(nextState);
    setStatus("Active API key updated.");
  };

  const testApiKey = async (providerId: string, credentialId: string) => {
    if (!window.electronAPI) {
      setStatus("Connection testing is available in the Jarvis desktop app.");
      return;
    }
    try {
      const result = await window.electronAPI.testProviderConnection({
        providerId,
        credentialId,
      });
      if (providerId === OPENCODE_PROVIDER_ID) {
        setZenConnectionStatus("Connected");
      }
      setStatus(result.message);
    } catch (error) {
      if (providerId === OPENCODE_PROVIDER_ID) {
        setZenConnectionStatus("Disconnected");
      }
      setStatus(
        error instanceof Error ? error.message : "Connection test failed.",
      );
    }
  };

  const renameApiKey = async (providerId: string, credentialId: string) => {
    const nextState = { ...state };
    const provider = getProviderById(nextState, providerId);
    const credential = provider?.apiKeys.find((key) => key.id === credentialId);
    if (!provider || !credential) return;
    const name = window.prompt("Credential name", credential.name)?.trim();
    if (!name) return;
    credential.name = name;
    credential.updatedAt = new Date().toISOString();
    await persistState(nextState);
    setStatus("Credential name updated.");
  };

  const deleteApiKey = async (providerId: string, credentialId: string) => {
    const provider = getProviderById(state, providerId);
    if (!provider || !window.electronAPI) return;
    await window.electronAPI.deleteCredential({
      credentialId:
        provider.apiKeys.find((key) => key.id === credentialId)
          ?.secureCredentialReference ?? credentialId,
      providerId,
    });
    const nextState = { ...state };
    const nextProvider = getProviderById(nextState, providerId);
    if (!nextProvider) return;
    nextProvider.apiKeys = nextProvider.apiKeys.filter(
      (key) => key.id !== credentialId,
    );
    if (nextProvider.activeApiKeyId === credentialId) {
      nextProvider.activeApiKeyId = nextProvider.apiKeys[0]?.id;
    }
    await persistState(nextState);
    setStatus("Credential deleted.");
  };

  const handleRefreshLocalModels = async () => {
    if (!window.electronAPI) {
      const nextState = { ...state };
      const provider =
        getProviderById(nextState, "ollama") ??
        addProvider(nextState, {
          name: "Ollama",
          type: "local",
          apiFormat: "ollama",
          baseUrl: "http://localhost:11434",
        });
      addDiscoveredModels(nextState, provider.id, [
        {
          id: "qwen3",
          displayName: "Qwen 3",
          category: "local",
          free: true,
          capabilities: ["text"],
        },
      ]);
      await persistState(nextState);
      setStatus("Refreshed local model list.");
      return;
    }

    const discovered = await window.electronAPI.discoverLocalModels();
    const nextState = { ...state };
    const provider =
      getProviderById(nextState, "ollama") ??
      addProvider(nextState, {
        name: "Ollama",
        type: "local",
        apiFormat: "ollama",
        baseUrl: "http://localhost:11434",
      });
    addDiscoveredModels(nextState, provider.id, discovered);
    await persistState(nextState);
    setStatus(`Discovered ${discovered.length || 0} local models.`);
  };

  const addCustomModelEntry = async () => {
    if (!modelDraft.displayName.trim()) {
      setStatus("Model display name is required.");
      return;
    }

    const nextState = { ...state };
    addManualModel(nextState, modelDraft.providerId, {
      id: modelDraft.displayName.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
      displayName: modelDraft.displayName.trim(),
      category: modelDraft.category,
      free: modelDraft.free,
      capabilities: modelDraft.capabilities,
      apiFormat: modelDraft.apiFormat,
      baseUrl: modelDraft.baseUrl,
    });
    await persistState(nextState);
    setModelDraft({ ...defaultModelDraft, providerId: selectedProviderId });
    setStatus(`Added model: ${modelDraft.displayName.trim()}`);
  };

  const runScenario = (scenario: string[]) => {
    const nextTask =
      runModelSwitchSequence(task, scenario)[scenario.length - 1]?.task ?? task;
    setTask(nextTask);
    setStatus(
      `Task continued through ${scenario.join(" → ")}. Context preserved without restart.`,
    );
  };

  const handleModelTest = () => {
    const currentModel =
      state.models.find((model) => model.id === state.selectedModelId) ??
      state.models[0];

    if (!currentModel) {
      setStatus("No model is selected for the capability check.");
      return;
    }

    const result = simulateProviderRequest(
      currentModel,
      "Create a short progress update for the current task.",
      ["text"],
    );

    if (!result.ok) {
      setStatus(result.error ?? "Model request failed.");
      return;
    }

    setStatus(result.content);
  };

  const sendMessage = async () => {
    const text = messageDraft.trim();
    if (!text) {
      setStatus("Type a message to continue the conversation.");
      return;
    }

    const nextState = { ...state };
    const conversationId =
      nextState.currentConversationId ?? uid("conversation");
    const conversation = nextState.conversations.find(
      (entry) => entry.id === conversationId,
    ) ?? {
      id: conversationId,
      title: "New conversation",
      messages: [],
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    const userMessage = {
      id: uid("message"),
      role: "user" as const,
      content: text,
      createdAt: new Date().toISOString(),
    };

    if (!selectedModel) {
      setStatus("Select a model before sending a message.");
      return;
    }
    if (!window.electronAPI) {
      setStatus("Model execution is available in the Jarvis desktop app.");
      return;
    }

    conversation.messages.push(userMessage);
    conversation.updatedAt = new Date().toISOString();
    conversation.title =
      conversation.messages[0]?.content?.slice(0, 40) ?? "New conversation";

    nextState.currentConversationId = conversationId;
    if (!nextState.conversations.find((entry) => entry.id === conversationId)) {
      nextState.conversations.push(conversation);
    }

    await persistState(nextState);
    setMessageDraft("");
    setStatus(`Sending to ${selectedModel.displayName}...`);

    try {
      const result = await generateModel(
        selectedModel.id,
        conversation.messages.map(({ role, content }) => ({ role, content })),
      );
      const assistantMessage = {
        id: uid("assistant"),
        role: "assistant" as const,
        content: result.content,
        createdAt: new Date().toISOString(),
      };
      const responseConversation = {
        ...conversation,
        messages: [...conversation.messages, assistantMessage],
        updatedAt: new Date().toISOString(),
        modelId: selectedModel.id,
      };
      const responseState = {
        ...nextState,
        conversations: nextState.conversations.map((entry) =>
          entry.id === conversationId ? responseConversation : entry,
        ),
      };
      await persistState(responseState);
      setStatus(`${selectedModel.displayName} responded.`);
    } catch (error) {
      setStatus(
        error instanceof Error ? error.message : "Model request failed.",
      );
    }
  };

  const executeToolAction = async (request: ToolRequest) => {
    if (!window.electronAPI) {
      setStatus("Desktop tools are unavailable in this environment.");
      return;
    }

    const confirmedRequest = {
      ...request,
      confirmed: request.requiresConfirmation ? toolApproved : true,
    };

    const authorized = canExecuteTool(confirmedRequest, toolApproved);

    if (!authorized) {
      setStatus("Action blocked: explicit approval is required.");
      setToolConsole((prev) => [
        ...prev,
        `Blocked: ${request.name} requires confirmation before execution.`,
      ]);
      return;
    }

    const result = await window.electronAPI.executeTool(confirmedRequest);
    setToolConsole((prev) =>
      [...prev, result?.message ?? "Tool finished."].slice(-8),
    );
    setStatus(result?.message ?? "Tool execution completed.");
  };

  const handleResearchPlan = () => {
    const nextPlan = buildResearchPlan(researchDraft);
    setResearchPlan(nextPlan);
    setStatus(`Research brief ready for: ${nextPlan.topic}`);
  };

  const handleDocumentDigest = () => {
    const digest = summarizeDocument(
      "Machine learning helps teams reason faster. It can summarize large documents and support careful review. This improves workflows for knowledge workers in everyday practice.",
      2,
    );
    setToolConsole((prev) => [...prev, `Document digest: ${digest}`].slice(-8));
    setStatus("Document digest refreshed.");
  };

  const handleMemorySave = () => {
    const nextStore = new MemoryStore();
    nextStore.entries = [...memoryStore.entries];
    const entry = nextStore.remember(memoryDraft);
    setMemoryStore(nextStore);
    setMemoryDraft("");
    setStatus(
      entry.content
        ? "Memory saved to the local knowledge base."
        : "Nothing to save.",
    );
  };

  const suggestedSkills = useMemo(
    () => suggestSkills(messageDraft || task.objective),
    [messageDraft, task.objective],
  );
  const availableCapabilityFilters = ["vision", "tools", "reasoning"].filter(
    (filter) =>
      state.models.some((model) =>
        model.capabilities.some((capability) => {
          const normalized = capability.toLowerCase();
          return filter === "tools"
            ? normalized.includes("tool") || normalized.includes("function")
            : normalized.includes(filter);
        }),
      ),
  );

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">LOCAL-FIRST • MODEL-AGNOSTIC</p>
          <h1>AERA AI</h1>
        </div>
        <button
          type="button"
          className="settings-button"
          onClick={() => setSettingsOpen((open) => !open)}
        >
          Settings ⚙
        </button>
      </header>

      <main className="content-grid">
        <section className="chat-panel">
          <div className="composer">
            <textarea
              value={messageDraft}
              onChange={(event) => setMessageDraft(event.target.value)}
              rows={3}
              placeholder="What do you want me to do?"
            />
            <div className="composer-controls">
              <button type="button" className="secondary">
                📎 Attach
              </button>
              <div className="field-row stacked">
                <input
                  value={modelSearch}
                  onChange={(event) => setModelSearch(event.target.value)}
                  placeholder="Search model"
                />
                <select
                  value={modelFilter}
                  onChange={(event) =>
                    setModelFilter(
                      event.target.value as
                        | "all"
                        | "free"
                        | "local"
                        | "cloud"
                        | "vision"
                        | "tools"
                        | "reasoning",
                    )
                  }
                >
                  <option value="all">All</option>
                  <option value="free">Free</option>
                  <option value="local">Local</option>
                  <option value="cloud">Cloud</option>
                  {availableCapabilityFilters.map((filter) => (
                    <option key={filter} value={filter}>
                      {filter[0].toUpperCase() + filter.slice(1)}
                    </option>
                  ))}
                </select>
              </div>
              <label className="model-picker">
                <span>Model</span>
                <select
                  value={selectedModel?.id ?? ""}
                  onChange={(event) => {
                    setState((prev) => ({
                      ...prev,
                      selectedModelId: event.target.value,
                    }));
                  }}
                >
                  {state.providers.map((provider) => {
                    const providerModels = filteredModels.filter(
                      (model) => model.providerId === provider.id,
                    );
                    return providerModels.length ? (
                      <optgroup key={provider.id} label={provider.name}>
                        {providerModels.map((model) => (
                          <option
                            key={model.id}
                            value={model.id}
                            disabled={!model.available}
                          >
                            {model.displayName}
                            {model.available ? "" : " (Unavailable)"}
                          </option>
                        ))}
                      </optgroup>
                    ) : null;
                  })}
                </select>
              </label>
              <button type="button" className="primary" onClick={sendMessage}>
                GO
              </button>
            </div>
          </div>

          <div className="status-row">
            <span className="pill success">
              {selectedModel?.displayName ?? "No model selected"}
            </span>
            <span className="pill neutral">{status}</span>
          </div>

          <div className="task-panel">
            <div className="task-header-row">
              <h3>Task state</h3>
              <span>{task.progress}%</span>
            </div>
            <p>
              <strong>Objective:</strong> {task.objective}
            </p>
            <p>
              <strong>Current:</strong> {task.current}
            </p>
            <p>
              <strong>Fallback:</strong>{" "}
              {buildFallbackOrder(
                task.lastModelId ?? "qwen3-local",
                "gpt-4o-mini",
                "claude-3-5-sonnet",
                "gemini-2-flash",
              ).join(" → ")}
            </p>
            <div className="task-progress-bar">
              <span style={{ width: `${task.progress}%` }} />
            </div>
            <div className="task-actions">
              <button
                type="button"
                className="secondary"
                onClick={() =>
                  runScenario([
                    "qwen3-local",
                    "gpt-4o-mini",
                    "claude-3-5-sonnet",
                    "gemini-2-flash",
                    "qwen3-local",
                  ])
                }
              >
                Test Qwen → GPT → Claude → Gemini → Qwen
              </button>
              <button
                type="button"
                className="secondary"
                onClick={handleModelTest}
              >
                Check model capability
              </button>
            </div>
          </div>

          <div className="tool-panel">
            <div className="task-header-row">
              <h3>Desktop tool layer</h3>
              <span>Step 3</span>
            </div>
            <label className="check-row tool-approval">
              <input
                type="checkbox"
                checked={toolApproved}
                onChange={() => setToolApproved((value) => !value)}
              />
              I approve medium-risk desktop actions.
            </label>
            <div className="tool-actions">
              <button
                type="button"
                className="secondary"
                onClick={() =>
                  executeToolAction({
                    name: "open-browser-search",
                    risk: "LOW",
                    requiresConfirmation: false,
                    params: {
                      query: "AI education research",
                      url: buildSearchUrl("AI education research"),
                    },
                  })
                }
              >
                Open browser search
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() =>
                  executeToolAction({
                    name: "create-folder",
                    risk: "LOW",
                    requiresConfirmation: false,
                    params: { folderName: "Aera AI" },
                  })
                }
              >
                Create Desktop folder
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() =>
                  executeToolAction({
                    name: "open-notepad",
                    risk: "MEDIUM",
                    requiresConfirmation: true,
                    params: {
                      fileName: "Aera AI Notes.txt",
                      content:
                        "Project status: ready for browser and desktop automation.",
                    },
                  })
                }
              >
                Open Notepad
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() =>
                  executeToolAction({
                    name: "find-files",
                    risk: "LOW",
                    requiresConfirmation: false,
                    params: { rootPath: "C:/Users", extensions: "txt" },
                  })
                }
              >
                Find text files
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() =>
                  executeToolAction({
                    name: "run-powershell",
                    risk: "MEDIUM",
                    requiresConfirmation: true,
                    params: {
                      command: "Get-ChildItem Env:Temp",
                    },
                  })
                }
              >
                Run approved PowerShell
              </button>
            </div>
            <div className="tool-console">
              {toolConsole.map((entry, index) => (
                <div key={`${entry}-${index}`} className="tool-log-entry">
                  {entry}
                </div>
              ))}
            </div>
          </div>

          <div className="research-panel">
            <div className="task-header-row">
              <h3>Research + document layer</h3>
              <span>Step 4</span>
            </div>
            <textarea
              value={researchDraft}
              onChange={(event) => setResearchDraft(event.target.value)}
              rows={2}
              placeholder="Topic for the research brief"
            />
            <div className="tool-actions">
              <button
                type="button"
                className="secondary"
                onClick={handleResearchPlan}
              >
                Build research brief
              </button>
              <button
                type="button"
                className="secondary"
                onClick={handleDocumentDigest}
              >
                Digest notes
              </button>
            </div>
            <div className="research-summary">
              <strong>Summary:</strong> {researchPlan.summary}
            </div>
            <ul className="research-list">
              {researchPlan.queries.map((query) => (
                <li key={query}>{query}</li>
              ))}
            </ul>
          </div>

          <div className="memory-panel">
            <div className="task-header-row">
              <h3>Memory + skills</h3>
              <span>Step 5</span>
            </div>
            <textarea
              value={memoryDraft}
              onChange={(event) => setMemoryDraft(event.target.value)}
              rows={2}
              placeholder="Store a useful fact or preference"
            />
            <div className="tool-actions">
              <button
                type="button"
                className="secondary"
                onClick={handleMemorySave}
              >
                Save memory
              </button>
            </div>
            <div className="skill-row">
              {suggestedSkills.map((skill) => (
                <span key={skill} className="skill-pill">
                  {skill}
                </span>
              ))}
            </div>
            <ul className="research-list">
              {memoryStore.entries.slice(0, 4).map((entry) => (
                <li key={entry.id}>{entry.content}</li>
              ))}
            </ul>
          </div>

          <div className="conversation-box">
            <h2>Conversation</h2>
            {currentConversation?.messages.length ? (
              currentConversation.messages.map((message) => (
                <div key={message.id} className={`message ${message.role}`}>
                  <div className="role">
                    {message.role === "assistant" ? "AI" : "User"}
                  </div>
                  <p>{message.content}</p>
                </div>
              ))
            ) : (
              <p className="empty-state">
                No messages yet. Start a conversation.
              </p>
            )}
          </div>

          <div className="toolbar">
            <button
              type="button"
              className="secondary"
              onClick={() => sendMessage()}
            >
              Save conversation
            </button>
            <button
              type="button"
              className="secondary"
              onClick={handleRefreshLocalModels}
            >
              Refresh local models
            </button>
            <button
              type="button"
              className="secondary"
              onClick={handleRefreshOpenCodeModels}
            >
              Refresh OpenCode Zen
            </button>
            <button
              type="button"
              className="secondary"
              onClick={handleOpenCodeTest}
            >
              Test OpenCode Zen
            </button>
          </div>
        </section>

        {settingsOpen && (
          <aside className="settings-panel">
            <h2>Settings</h2>

            <div className="settings-section">
              <h3>Providers</h3>
              <div className="field-row">
                <input
                  value={providerDraft.name}
                  onChange={(event) =>
                    setProviderDraft((prev) => ({
                      ...prev,
                      name: event.target.value,
                    }))
                  }
                  placeholder="Provider name"
                />
                <select
                  value={providerDraft.type}
                  onChange={(event) =>
                    setProviderDraft((prev) => ({
                      ...prev,
                      type: event.target.value as "local" | "cloud",
                    }))
                  }
                >
                  <option value="local">Local</option>
                  <option value="cloud">Cloud</option>
                </select>
              </div>
              <div className="field-row">
                <select
                  value={providerDraft.apiFormat}
                  onChange={(event) =>
                    setProviderDraft((prev) => ({
                      ...prev,
                      apiFormat: event.target
                        .value as ProviderDraft["apiFormat"],
                    }))
                  }
                >
                  <option value="ollama">Ollama</option>
                  <option value="lm-studio">LM Studio</option>
                  <option value="openai-compatible">OpenAI-compatible</option>
                  <option value="custom">Custom</option>
                </select>
                <input
                  value={providerDraft.baseUrl}
                  onChange={(event) =>
                    setProviderDraft((prev) => ({
                      ...prev,
                      baseUrl: event.target.value,
                    }))
                  }
                  placeholder="https://example.com/v1"
                />
              </div>
              <button
                type="button"
                className="primary"
                onClick={addProviderEntry}
              >
                + Add Provider
              </button>
            </div>

            <div className="settings-section">
              <h3>API Keys</h3>
              <select
                value={selectedProviderId}
                onChange={(event) => setSelectedProviderId(event.target.value)}
              >
                {state.providers.map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.name}
                  </option>
                ))}
              </select>

              <div className="field-row stacked">
                <input
                  value={apiKeyName}
                  onChange={(event) => setApiKeyName(event.target.value)}
                  placeholder="Key name"
                />
                <input
                  type="password"
                  ref={apiKeyValueRef}
                  placeholder="Secret API key"
                  autoComplete="new-password"
                />
              </div>
              <button
                type="button"
                className="primary"
                onClick={addApiKeyEntry}
              >
                + Add API Key
              </button>

              {state.providers
                .find((provider) => provider.id === selectedProviderId)
                ?.apiKeys.map((key) => (
                  <div key={key.id} className="key-row">
                    <div>
                      <strong>{key.name}</strong>
                      <span>••••••••••••</span>
                    </div>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() =>
                        updateActiveKey(selectedProviderId, key.id)
                      }
                    >
                      {state.providers.find(
                        (provider) => provider.id === selectedProviderId,
                      )?.activeApiKeyId === key.id
                        ? "Active"
                        : "Use"}
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => testApiKey(selectedProviderId, key.id)}
                    >
                      Test
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => renameApiKey(selectedProviderId, key.id)}
                    >
                      Rename
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => deleteApiKey(selectedProviderId, key.id)}
                    >
                      Delete
                    </button>
                  </div>
                ))}
            </div>

            {selectedProviderId === OPENCODE_PROVIDER_ID && (
              <div className="settings-section">
                <h3>OpenCode Zen</h3>
                <p>Status: {zenConnectionStatus}</p>
                <p>
                  {
                    state.models.filter(
                      (model) => model.providerId === OPENCODE_PROVIDER_ID,
                    ).length
                  }{" "}
                  models discovered
                </p>
                <div className="tool-actions">
                  <button
                    type="button"
                    className="secondary"
                    onClick={handleOpenCodeTest}
                  >
                    Test Connection
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    onClick={handleRefreshOpenCodeModels}
                  >
                    Refresh Models
                  </button>
                </div>
              </div>
            )}

            <div className="settings-section">
              <h3>Manage Models</h3>
              <div className="field-row stacked">
                <select
                  value={modelDraft.providerId}
                  onChange={(event) =>
                    setModelDraft((prev) => ({
                      ...prev,
                      providerId: event.target.value,
                    }))
                  }
                >
                  {state.providers.map((provider) => (
                    <option key={provider.id} value={provider.id}>
                      {provider.name}
                    </option>
                  ))}
                </select>
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={validateModelCapabilities(
                      {
                        capabilities: state.models.find(
                          (model) => model.id === state.selectedModelId,
                        )?.capabilities ?? ["text"],
                      },
                      ["text"],
                    )}
                    readOnly
                  />
                  Capability check: text supported
                </label>
                <input
                  value={modelDraft.displayName}
                  onChange={(event) =>
                    setModelDraft((prev) => ({
                      ...prev,
                      displayName: event.target.value,
                    }))
                  }
                  placeholder="Model display name"
                />
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={modelFilter === "free" || freeOnly}
                    onChange={() => {
                      setFreeOnly((value) => !value);
                      setModelFilter((current) =>
                        current === "free" ? "all" : "free",
                      );
                    }}
                  />
                  Free only
                </label>
              </div>
              <div className="field-row">
                <select
                  value={modelDraft.category}
                  onChange={(event) =>
                    setModelDraft((prev) => ({
                      ...prev,
                      category: event.target.value as
                        | "local"
                        | "cloud"
                        | "custom",
                    }))
                  }
                >
                  <option value="local">Local</option>
                  <option value="cloud">Cloud</option>
                  <option value="custom">Custom</option>
                </select>
                <select
                  value={modelDraft.apiFormat}
                  onChange={(event) =>
                    setModelDraft((prev) => ({
                      ...prev,
                      apiFormat: event.target.value,
                    }))
                  }
                >
                  <option value="ollama">Ollama</option>
                  <option value="lm-studio">LM Studio</option>
                  <option value="openai-compatible">OpenAI-compatible</option>
                  <option value="custom">Custom</option>
                </select>
              </div>
              <input
                value={modelDraft.baseUrl}
                onChange={(event) =>
                  setModelDraft((prev) => ({
                    ...prev,
                    baseUrl: event.target.value,
                  }))
                }
                placeholder="https://api.example.com/v1"
              />
              <button
                type="button"
                className="primary"
                onClick={addCustomModelEntry}
              >
                + Add Custom Model
              </button>
            </div>

            <div className="settings-section">
              <h3>Registry</h3>
              <div className="model-list">
                {state.models.map((model) => (
                  <button
                    type="button"
                    key={model.id}
                    className={`model-chip ${model.id === selectedModel?.id ? "selected" : ""}`}
                    onClick={() => {
                      setState((prev) => ({
                        ...prev,
                        selectedModelId: model.id,
                      }));
                    }}
                  >
                    {model.displayName}
                    <span>{model.category}</span>
                  </button>
                ))}
              </div>
            </div>
          </aside>
        )}
      </main>
    </div>
  );
}

export default App;
