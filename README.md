# Jarvis

Jarvis is an Electron desktop AI workspace with a React/TypeScript renderer, a SQLite-backed app state store, and a main-process model provider layer.

## Development

```powershell
npm install
npm test
npm run build
npm run electron:dev
```

`npm run dev` starts the Vite renderer at `http://localhost:5173/`. Provider credential storage and model execution require the Electron desktop runtime; the browser-only renderer intentionally cannot retrieve stored credentials or send provider requests.

## OpenCode Zen

OpenCode Zen is registered as a cloud provider with the OpenAI-compatible provider format. The renderer stores only credential metadata (`id`, provider ID, name, and secure reference). The actual key is submitted once through the preload IPC bridge and encrypted in the existing SQLite database using Electron `safeStorage`, which uses the operating system's protected storage on Windows. Keys are never returned by `app:load`; connection tests, discovery, and inference resolve the selected credential only in the Electron main process.

To configure it, open Settings, choose OpenCode Zen, enter a key name and API key, and select **Add API Key**. Use **Test Connection** to check authentication, then **Refresh Models** to load the current catalog. Additional keys can be added, selected, tested, renamed, or deleted independently. No automatic key rotation is performed.

### Discovery and execution

The Electron Zen adapter fetches the live catalog from `https://opencode.ai/zen/v1/models`. It consults the official [Zen endpoint and pricing documentation](https://opencode.ai/docs/zen/) to associate model IDs with documented API families/endpoints and current published pricing; model names and a static catalog are not used to select protocols or infer free access. The provider-neutral registry normalizes those results into Jarvis models and preserves capability, pricing, context, family, and source metadata when available. Missing free/pricing data remains `unknown`; refresh marks models no longer returned by the catalog unavailable rather than deleting their history.

The model selector groups entries by provider. The normal Go action sends conversation messages through `src/lib/modelRequest.ts`, the provider-neutral IPC interface, and `electron/modelProviderRegistry.cjs`. Provider-specific network logic belongs in `electron/opencodeZenAdapter.cjs`. That adapter supports documented OpenAI Chat Completions, OpenAI Responses, Anthropic Messages, and Google Generative Language request families when the official docs provide a matching endpoint. Structured System One models are discovered but are not treated as text-chat models.

Streaming is not currently implemented; the existing chat interface and IPC are request/response based. Unsupported or undocumented model protocols fail with a user-safe message rather than being forced through Chat Completions.

### Security

- `safeStorage` must report OS encryption available before a credential is stored or read; Jarvis does not fall back to plaintext or Base64 storage.
- SQLite stores encrypted credential bytes in the existing database and only credential metadata in app state.
- Credential IPC is scoped by provider and credential ID. The renderer cannot retrieve a stored secret.
- Provider HTTP errors do not include response bodies, authorization headers, or keys in UI messages.
- Legacy app-state key values are migrated to secure storage when possible and removed from persisted state; localStorage is overwritten with secret-free metadata on desktop load.
- The key being entered is necessarily present briefly in the password input and passed to the main process for secure storage. Do not use browser-only mode for provider credentials.

### Adding another provider

Add the provider metadata and normalized models to the existing `Provider` and `ModelDefinition` contracts, then implement provider-specific HTTP in a main-process adapter. Register the adapter in `electron/modelProviderRegistry.cjs`, expose only narrowly scoped operations through `electron/preload.cjs`, and keep secrets in the Electron credential store. The React layer should use the unified request interface and must not contain provider URLs, protocol payloads, or stored credentials. Add adapter/registry tests for metadata normalization, request routing, safe errors, and credential isolation.
