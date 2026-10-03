const { app, BrowserWindow, ipcMain, safeStorage } = require("electron");
const path = require("node:path");
const fs = require("node:fs");
const os = require("node:os");
const { randomUUID } = require("node:crypto");
const { spawn, spawnSync } = require("node:child_process");
const Database = require("better-sqlite3");
const { createCredentialStore } = require("./credentialStore.cjs");
const modelProviders = require("./modelProviderRegistry.cjs");

const isDev = !app.isPackaged;

function ensureStorage() {
  const appDataDir = path.join(app.getPath("appData"), "aera-ai");
  fs.mkdirSync(appDataDir, { recursive: true });
  return appDataDir;
}

function createDb() {
  const dir = ensureStorage();
  const dbPath = path.join(dir, "aera.db");
  const db = new Database(dbPath);
  db.pragma("journal_mode = WAL");
  db.prepare(
    `
    CREATE TABLE IF NOT EXISTS app_state (
      id TEXT PRIMARY KEY,
      payload TEXT NOT NULL
    )
  `,
  ).run();
  db.prepare(
    `CREATE TABLE IF NOT EXISTS credentials (
      id TEXT PRIMARY KEY,
      provider_id TEXT NOT NULL,
      encrypted_secret BLOB NOT NULL,
      updated_at TEXT NOT NULL
    )`,
  ).run();
  return db;
}

const db = createDb();
const credentials = createCredentialStore({ db, safeStorage });

function buildDefaultState() {
  return {
    providers: [
      {
        id: "ollama",
        name: "Ollama",
        type: "local",
        apiFormat: "ollama",
        baseUrl: "http://localhost:11434",
        enabled: true,
        autoDiscovered: true,
        activeApiKeyName: undefined,
        apiKeys: [],
        createdAt: new Date().toISOString(),
      },
      {
        id: "custom-openai",
        name: "Custom Provider",
        type: "cloud",
        apiFormat: "openai-compatible",
        baseUrl: "https://example.com/v1",
        enabled: true,
        autoDiscovered: false,
        activeApiKeyId: undefined,
        apiKeys: [],
        createdAt: new Date().toISOString(),
      },
      {
        id: "opencode-zen",
        name: "OpenCode Zen",
        type: "cloud",
        apiFormat: "openai-compatible",
        baseUrl: "https://opencode.ai/zen/v1",
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
        capabilities: ["text", "Reasoning"],
        available: true,
        apiFormat: "ollama",
        baseUrl: "http://localhost:11434",
      },
      {
        id: "custom-cloud-model",
        providerId: "custom-openai",
        displayName: "Custom Cloud Model",
        category: "custom",
        free: true,
        capabilities: ["text"],
        available: true,
        apiFormat: "openai-compatible",
        baseUrl: "https://example.com/v1",
      },
    ],
    conversations: [],
    selectedModelId: "qwen3-local",
    currentConversationId: undefined,
  };
}

function loadState() {
  const row = db
    .prepare("SELECT payload FROM app_state WHERE id = ?")
    .get("main");
  if (!row) {
    const state = buildDefaultState();
    saveState(state);
    return sanitizeState(state);
  }
  const state = JSON.parse(row.payload);
  const migrated = migrateLegacyCredentials(state);
  const ensured = ensureBuiltinProviders(migrated.state);
  const sanitized = sanitizeState(ensured.state);
  if (migrated.changed || ensured.changed) {
    saveState(sanitized);
    db.pragma("secure_delete = ON");
    db.pragma("wal_checkpoint(TRUNCATE)");
    db.exec("VACUUM");
  }
  return sanitized;
}

function saveState(state) {
  const sanitized = sanitizeState(state);
  db.prepare(
    "INSERT INTO app_state (id, payload) VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET payload = excluded.payload",
  ).run("main", JSON.stringify(sanitized));
  return sanitized;
}

function sanitizeState(nextState) {
  const clone = JSON.parse(JSON.stringify(nextState ?? buildDefaultState()));
  clone.providers = (clone.providers ?? []).map((provider) => {
    const { activeApiKeyName: _legacyActiveKeyName, ...providerMetadata } =
      provider;
    return {
      ...providerMetadata,
      apiKeys: (provider.apiKeys ?? []).map((key) => ({
        id: key.id ?? randomUUID(),
        providerId: provider.id,
        name: String(key.name ?? "Credential"),
        secureCredentialReference:
          key.secureCredentialReference ?? key.id ?? "",
        createdAt: key.createdAt ?? new Date().toISOString(),
        updatedAt: key.updatedAt ?? key.createdAt ?? new Date().toISOString(),
      })),
      activeApiKeyId: provider.activeApiKeyId,
    };
  });
  return clone;
}

function ensureBuiltinProviders(nextState) {
  const state = JSON.parse(JSON.stringify(nextState ?? buildDefaultState()));
  if (!state.providers.some((provider) => provider.id === "opencode-zen")) {
    state.providers.push({
      id: "opencode-zen",
      name: "OpenCode Zen",
      type: "cloud",
      apiFormat: "openai-compatible",
      baseUrl: "https://opencode.ai/zen/v1",
      enabled: true,
      autoDiscovered: false,
      activeApiKeyId: undefined,
      apiKeys: [],
      createdAt: new Date().toISOString(),
    });
    return { state, changed: true };
  }
  return { state, changed: false };
}

function decodeLegacySecret(value) {
  let secret = String(value ?? "");
  for (let attempt = 0; attempt < 3; attempt += 1) {
    if (
      !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(
        secret,
      )
    ) {
      break;
    }
    const decoded = Buffer.from(secret, "base64").toString("utf8");
    const containsControlCharacter = [...decoded].some((character) => {
      const code = character.charCodeAt(0);
      return (
        (code >= 0 && code <= 8) || (code >= 14 && code <= 31) || code === 127
      );
    });
    if (!decoded || decoded.includes("\uFFFD") || containsControlCharacter) {
      break;
    }
    secret = decoded;
  }
  return secret;
}

function migrateLegacyCredentials(nextState) {
  let changed = false;
  const migrated = JSON.parse(JSON.stringify(nextState ?? buildDefaultState()));
  migrated.providers = (migrated.providers ?? []).map((provider) => {
    let migratedActiveKeyId = provider.activeApiKeyId;
    const apiKeys = (provider.apiKeys ?? []).flatMap((key) => {
      if (typeof key.value !== "string" || !key.value) {
        return key.secureCredentialReference
          ? [{ ...key, providerId: provider.id }]
          : [];
      }

      changed = true;
      const credentialId =
        key.secureCredentialReference ?? key.id ?? randomUUID();
      if (key.name === provider.activeApiKeyName)
        migratedActiveKeyId = credentialId;
      try {
        credentials.store({
          credentialId,
          providerId: provider.id,
          secret: decodeLegacySecret(key.value),
        });
      } catch {
        return [];
      }

      return [
        {
          id: credentialId,
          providerId: provider.id,
          name: key.name ?? "Imported credential",
          secureCredentialReference: credentialId,
          createdAt: key.createdAt ?? new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        },
      ];
    });
    return {
      ...provider,
      activeApiKeyId: migratedActiveKeyId,
      apiKeys,
    };
  });
  return { state: migrated, changed };
}

function findProviderCredential(provider, requestedId) {
  const keyId = requestedId ?? provider.activeApiKeyId;
  if (!keyId) return "";
  const metadata = provider.apiKeys.find(
    (key) => key.id === keyId || key.secureCredentialReference === keyId,
  );
  if (!metadata?.secureCredentialReference) return "";
  return credentials.getSecret({
    credentialId: metadata.secureCredentialReference,
    providerId: provider.id,
  });
}

function validatePowerShellCommand(command) {
  const normalized = String(command ?? "").trim();
  if (!normalized) {
    return false;
  }

  const blocked = [
    /remove-item/i,
    /delete/i,
    /stop-process/i,
    /start-process/i,
    /invoke-webrequest/i,
    /curl\s+/i,
    /wget\s+/i,
    /reg\s+delete/i,
    /del\s+\/s\s*\/q/i,
    /rmdir\s+\/s\s*\/q/i,
    /format-volume/i,
    /shutdown/i,
  ];

  if (blocked.some((pattern) => pattern.test(normalized))) {
    return false;
  }

  return /^(Get-|Test-|Write-|Out-|Select-|Where-|Sort-|Measure-|Compare-|Resolve-|Split-|Join-|Set-Location|cd\s|echo\s|Write-Output\s)/i.test(
    normalized,
  );
}

function getDesktopDirectory() {
  const desktopDir = path.join(os.homedir(), "Desktop");
  fs.mkdirSync(desktopDir, { recursive: true });
  return desktopDir;
}

function walkFiles(rootPath, extensions = [], maxResults = 25, collected = []) {
  if (collected.length >= maxResults || !rootPath) {
    return collected;
  }

  try {
    const entries = fs.readdirSync(rootPath, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(rootPath, entry.name);
      if (entry.isDirectory()) {
        walkFiles(fullPath, extensions, maxResults, collected);
      } else {
        const ext = path.extname(entry.name).slice(1).toLowerCase();
        if (!extensions.length || extensions.includes(ext)) {
          collected.push(fullPath);
        }
        if (collected.length >= maxResults) {
          return collected;
        }
      }
    }
  } catch {
    // Ignore unreadable directories.
  }

  return collected;
}

async function fetchJson(url) {
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

async function discoverLocalModels() {
  const discovered = [];

  try {
    const ollamaResponse = await fetchJson("http://localhost:11434/api/tags");
    const rawModels = ollamaResponse?.models ?? [];
    for (const model of rawModels) {
      discovered.push({
        id: `ollama:${model.name}`,
        displayName: model.name,
        category: "local",
        free: true,
        capabilities: ["text", "local"],
        available: true,
        apiFormat: "ollama",
        baseUrl: "http://localhost:11434",
      });
    }
  } catch (error) {
    console.warn("Ollama discovery failed", error);
  }

  try {
    const lmStudioResponse = await fetchJson("http://localhost:1234/v1/models");
    const rawModels = lmStudioResponse?.data ?? [];
    for (const model of rawModels) {
      discovered.push({
        id: `lmstudio:${model.id}`,
        displayName: model.id,
        category: "local",
        free: true,
        capabilities: ["text", "local"],
        available: true,
        apiFormat: "lm-studio",
        baseUrl: "http://localhost:1234/v1",
      });
    }
  } catch (error) {
    console.warn("LM Studio discovery failed", error);
  }

  return discovered;
}

ipcMain.handle("app:load", () => {
  return loadState();
});

ipcMain.handle("app:save", (_, state) => {
  return saveState(state);
});

ipcMain.handle("credentials:store", (_, entry) => {
  const state = loadState();
  if (!state.providers.some((provider) => provider.id === entry?.providerId)) {
    throw new Error("Provider was not found.");
  }
  credentials.store(entry ?? {});
  return { ok: true };
});

ipcMain.handle("credentials:delete", (_, entry) => {
  credentials.delete(entry ?? {});
  return { ok: true };
});

ipcMain.handle("providers:test-connection", async (_, request) => {
  const state = loadState();
  const provider = state.providers.find(
    (entry) => entry.id === request?.providerId,
  );
  if (!provider) throw new Error("Provider was not found.");
  const apiKey = findProviderCredential(provider, request?.credentialId);
  return modelProviders.testConnection({ provider, apiKey });
});

ipcMain.handle("providers:discover-models", async (_, request) => {
  const state = loadState();
  const provider = state.providers.find(
    (entry) => entry.id === request?.providerId,
  );
  if (!provider) throw new Error("Provider was not found.");
  const apiKey = findProviderCredential(provider, request?.credentialId);
  return modelProviders.discoverModels({ provider, apiKey });
});

ipcMain.handle("models:generate", async (_, request) => {
  const state = loadState();
  const model = state.models.find((entry) => entry.id === request?.modelId);
  if (!model)
    throw new Error("The selected model is no longer in the registry.");
  const provider = state.providers.find(
    (entry) => entry.id === model.providerId,
  );
  if (!provider) throw new Error("The selected model provider was not found.");
  const apiKey = findProviderCredential(provider, request?.credentialId);
  return modelProviders.generateModel({
    provider,
    model,
    messages: request?.messages,
    apiKey,
  });
});

ipcMain.handle("providers:discover-local", async () => discoverLocalModels());

ipcMain.handle("tools:execute", async (_, request) => {
  const action = request?.name ?? "open-browser-search";
  const params = request?.params ?? {};

  if (
    request?.risk !== "LOW" &&
    request?.requiresConfirmation &&
    !request?.confirmed
  ) {
    return {
      ok: false,
      action,
      message: "This action requires explicit confirmation before execution.",
    };
  }

  switch (action) {
    case "open-browser-search": {
      const query = String(params.query ?? "AI automation");
      const resolvedQuery = String(query).trim() || "AI automation";
      const targetUrl = String(
        params.url ??
          `https://www.google.com/search?q=${encodeURIComponent(resolvedQuery).replace(/%20/g, "+")}`,
      );
      spawn("cmd", ["/c", "start", "", targetUrl], {
        detached: true,
        windowsHide: true,
      });
      return {
        ok: true,
        action,
        message: `Opened browser search for ${query}.`,
      };
    }
    case "create-folder": {
      const folderName = String(params.folderName ?? "Aera AI");
      const targetDir = path.join(getDesktopDirectory(), folderName);
      fs.mkdirSync(targetDir, { recursive: true });
      return {
        ok: true,
        action,
        message: `Created folder: ${targetDir}`,
      };
    }
    case "open-notepad": {
      const fileName = String(params.fileName ?? "Aera AI Notes.txt");
      const content = String(
        params.content ??
          "Project status: ready for browser and desktop automation.",
      );
      const filePath = path.join(getDesktopDirectory(), fileName);
      fs.writeFileSync(filePath, content, "utf8");
      spawn("notepad.exe", [filePath], {
        detached: true,
        stdio: "ignore",
      });
      return {
        ok: true,
        action,
        message: `Opened notes file at ${filePath}.`,
      };
    }
    case "find-files": {
      const rootPath = String(params.rootPath ?? getDesktopDirectory());
      const extensions = String(params.extensions ?? "")
        .split(",")
        .map((entry) => entry.trim().toLowerCase())
        .filter(Boolean);
      const matches = walkFiles(rootPath, extensions, 25);
      return {
        ok: true,
        action,
        message: `Found ${matches.length} matching files in ${rootPath}.`,
        output: matches.slice(0, 10),
      };
    }
    case "run-powershell": {
      const command = String(params.command ?? "Get-ChildItem Env:Temp");
      if (!validatePowerShellCommand(command)) {
        return {
          ok: false,
          action,
          message: "PowerShell command blocked by the safety policy.",
        };
      }

      const result = spawnSync(
        "powershell",
        ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        { encoding: "utf8" },
      );

      if (result.error) {
        return {
          ok: false,
          action,
          message: `PowerShell failed: ${result.error.message}`,
        };
      }

      if (result.status !== 0) {
        return {
          ok: false,
          action,
          message: String(result.stderr || "PowerShell command failed."),
        };
      }

      return {
        ok: true,
        action,
        message: "PowerShell command completed successfully.",
        output: (result.stdout || "")
          .split(/\r?\n/)
          .filter(Boolean)
          .slice(0, 10),
      };
    }
    default:
      return {
        ok: false,
        action,
        message: `Unknown tool action: ${action}`,
      };
  }
});

function createWindow() {
  const win = new BrowserWindow({
    width: 1400,
    height: 960,
    title: "Aera AI",
    backgroundColor: "#0f172a",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const startUrl = isDev
    ? "http://localhost:5173"
    : `file://${path.join(__dirname, "../dist/index.html")}`;
  win.loadURL(startUrl);

  if (isDev) {
    win.webContents.openDevTools({ mode: "detach" });
  }
}

app.whenReady().then(() => {
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
