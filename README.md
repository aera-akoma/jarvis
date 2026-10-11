# Jarvis

[![CI](https://github.com/aera-akoma/jarvis/actions/workflows/ci.yml/badge.svg)](https://github.com/aera-akoma/jarvis/actions/workflows/ci.yml)

Jarvis is a local-first Windows desktop AI assistant built with Python and PySide6. It runs as a native desktop app, stores data locally, supports secure credentials, maintains chat sessions and memory, and can be packaged into a standalone Windows executable.

## What this project is

This repository is not a React/Electron web app. It is a Python desktop application designed for Windows users who want a simple AI agent with:

- a native Qt desktop interface
- local SQLite-backed sessions and memory
- secure credential storage using the OS credential store
- startup toggle support for Windows session startup
- OpenCode-compatible model integration hooks
- PyInstaller packaging for a standalone .exe

## Features

- Desktop UI with PySide6
- Conversation/session management, with per-chat rename/delete and one-go deletion of multiple selected chats
- Local memory store with search
- Learning: relevance-ranked memories with categories in every prompt, session-wide memory suggestions after successful tasks, and a user-approved `remember_memory` tool for the agent
- Many free model providers: built-in presets for the "awesome-free-llm-apis" list, three keyless presets, custom OpenAI-compatible endpoints, and automatic retry across a fallback-model list on retryable errors
- Browser sign-in (OAuth) for Azure OpenAI / AI Foundry (device code) and Google Gemini (installed-app PKCE), with no pasted long-lived secret
- Managed-browser automation: navigate, click, type, history, named-key presses, scroll, wait-for-load, link extraction, and page screenshots
- Desktop control: screenshots, mouse/keyboard input, window focus/move/resize, and application launch
- Document reading: PDF, Word (.docx), Excel (.xlsx), and plain-text extraction for analysis
- Local knowledge/memory/conversation search plus optional web search
- Voice input and spoken output
- Undo for the last reversible action (file writes, created files/directories, window geometry)
- Self-describing skills auto-discovered from `app/skills/`, with an authoring template
- Workflow and settings persistence
- Secure API key storage
- Encrypted portable backups for conversations, memories, workflows, and selected settings
- Windows startup integration scaffold
- Standalone desktop packaging with PyInstaller
- Installer scaffold for Windows deployment

## Project structure

- `app/` — application code
- `tests/` — pytest regression tests
- `docs/` — setup guides (for example [docs/oauth_setup.md](docs/oauth_setup.md))
- `installer/` — Windows installer scripts
- `jarvis.spec` — PyInstaller build specification
- `requirements.txt` — Python dependencies
- `pyproject.toml` — project metadata

## Requirements

- Python 3.10+
- Windows 10/11 recommended
- PySide6
- PyInstaller

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app
```

This starts the desktop app from the project source tree.

## Configure a model provider

Open **Settings** from Jarvis, choose a **Provider** preset, and enter that provider's API key. The preset fills the Runtime URL (still editable). Each provider's key is stored **separately** with Windows DPAPI, so adding a Groq key never overwrites your OpenCode key. Leaving the key box empty keeps the saved key for the selected provider; **Clear key** removes only the selected provider's key. The key box intentionally stays empty after saving, and the status below it confirms whether a key is stored for that provider.

Jarvis currently uses the OpenAI-compatible Chat Completions API. For an OpenCode Console service-account key, set Runtime URL to `https://opencode.ai/inference/openai/v1`; Jarvis fetches the public model catalog from `https://opencode.ai/inference/v1/models` and sends chat requests to `https://opencode.ai/inference/openai/v1/chat/completions`. The Console catalog contains model IDs but does not identify each model's API family, so Jarvis matches those IDs against OpenCode's documented Console model-family table. This checks protocol compatibility only; it does not prove that the configured account can use a model. The **Test connection** action checks the catalog in a background worker and does not send a chat request or validate the saved key.

For an OpenCode key obtained from the TUI's `/connect` command, use `https://opencode.ai/zen/v1`. For an OpenCode Console service-account key (Console > Keys > Add Service Account > Add API Key), use `https://opencode.ai/inference/openai/v1`. These are two separate OpenCode routes that use **different keys**; picking the wrong one returns `HTTP 403` at the chat-completions POST. Jarvis does not switch between them or guess alternate paths. The default model `deepseek-v4-flash` and the previously common `kimi-k2.6` are both listed in the public catalog and documented for Chat Completions; workspace/account access is checked by the provider when a chat request is sent. Models offered only through `/responses`, `/messages`, Gemini, or System One endpoints are reported as unsupported because this client implements Chat Completions only. The local `opencode serve` session API is a different protocol and is not a compatible URL for this version of Jarvis.

Model discovery runs in a background worker with a six-second request timeout. If the model list is unavailable, Jarvis shows a provider error and keeps the chat window responsive. Logs are stored at `%APPDATA%\Jarvis\logs\jarvis.log`.

Provider errors show whether the catalog GET or Chat Completions POST failed, along with a sanitized endpoint and HTTP status. When the provider returns a structured error (for example OpenCode's `{"type":"error","error":{"type":"...","message":"..."}}`), Jarvis shows that type and message, redacted and length-bounded, because it is the most accurate diagnostic available. Jarvis never logs authorization headers, key values, or arbitrary unredacted response bodies; each request is recorded in `%APPDATA%\Jarvis\logs\jarvis.log` as `stage`, sanitized `endpoint`, `status`, `edge_blocked`, and provider `error_type` only.

**Known cause of `HTTP 403`.** OpenCode sits behind a CDN edge rule that rejects Python's default `Python-urllib/3.x` signature with `HTTP 403` (Cloudflare error `1010`, `browser_signature_banned`) *before* authentication is evaluated. Jarvis therefore sends an honest, non-browser `User-Agent: Jarvis/1.0` on every request, which matches OpenCode's own documented `curl https://opencode.ai/inference/v1/models` usage. Jarvis does not impersonate a browser, alter credentials, or bypass authentication. When this happens Jarvis reports it explicitly as an edge block and states that it is **not** an API-key, workspace, model, or quota problem — regenerating a key will not change it. Any other `403` comes from the OpenCode API itself and means the request was refused after the edge. The most common cause is pairing a key with the wrong route (`/connect` key on the Console URL, or a Console service-account key on the Zen URL); Jarvis now reports the provider's own error type and message and names both routes in that case. A `401` means the credential itself was rejected.

**Free-tier policy.** OpenCode restricts its free models to the official client: a request from any third-party tool is refused with `HTTP 403` `FreeTierError: OpenCode's free tier can only be used from within OpenCode`. This is a server-side policy, not a Jarvis bug, and Jarvis will not impersonate the official client to avoid it. Free models therefore cannot be used through Jarvis; choose a paid model, which needs Console credits or an OpenCode Go/Go Plus subscription. A request with a missing, empty, or unrecognised key is also treated as free tier, so this error can appear when the saved key has been rotated or revoked and Jarvis still holds the old one — re-enter the current key in Settings and press **Save** (the key box stays blank on purpose, so leaving it blank keeps the *old* key).

**Test model access.** The public catalog can succeed even when the account cannot use a model, so the **Test model access** button in Settings sends one tiny Chat Completions request with the saved key and the configured model and reports the provider's exact response (including any `error.type`). **Test connection** only checks the catalog. Use **Test model access** to confirm the saved key really reaches a model.

## Free providers and automatic model failover

Jarvis supports any OpenAI Chat Completions-compatible provider. The built-in **Provider** presets cover the full "awesome-free-llm-apis" list — Groq, Google Gemini, Mistral, Z AI (Zhipu), Cohere, Aion Labs, OpenRouter, NVIDIA NIM, Hugging Face Router, ModelScope, Kilo Code, LLM7.io, OVHcloud AI Endpoints, Ollama Cloud, SiliconFlow, Cloudflare Workers AI — plus Cerebras, Together AI, GitHub Models, the two OpenCode routes (Zen `/connect` key and Console service-account key) and a **Custom** option that keeps your existing setup. Providers that OpenCode's own catalog also supports (14 of the 16 free ones) are marked in the Settings hint. The Runtime URL remains editable, so a changed endpoint can always be corrected. Each provider stores its own key (see above). Two presets need an edit before use: Cloudflare (`{account_id}` must be replaced with your account id) and Cohere (uses the OpenAI-compatible `/compatibility/v1` endpoint). Three presets are keyless and work immediately with no sign-up or key: **Kilo Code** (default model `kilo-auto/free`), **LLM7.io** (default `DeepSeek-V4-Flash-0731`), and **OVHcloud** (default `Mistral-7B-Instruct-v0.3`); these defaults were verified live with no API key sent.

If a provider does not expose a `/models` catalog, Jarvis still lets you send using the models you configured instead of blocking the chat window.

### Browser sign-in (OAuth)

Some providers accept a browser sign-in instead of a pasted key. **Sign in with browser…** in Settings opens the sign-in dialog, which currently supports:

- **Microsoft Entra ID (Azure OpenAI / AI Foundry)** — device code flow (RFC 8628): Jarvis shows a code and opens the provider page; you approve there; the token is stored securely. You need a **public-client app registration**, your directory (tenant) id, and a **Cognitive Services OpenAI User** role for your identity on the Azure AI resource. After sign-in Jarvis selects the **Azure OpenAI / AI Foundry — browser sign-in** preset; replace `<resource-name>` in its Runtime URL and enter your **deployment name** as the model.
- **Google (Gemini)** — installed-app authorization code + PKCE on a loopback redirect, using a **Desktop app** OAuth client you create (only the client id is needed). After sign-in Jarvis selects the **Google Gemini — free tier** preset automatically.

Full step-by-step setup for both providers, including the two developer consoles, role assignment, and troubleshooting: **[docs/oauth_setup.md](docs/oauth_setup.md)**.

Jarvis implements only the standard OAuth flows (device authorization grant and RFC 7636 PKCE) and never performs a private or undocumented token exchange, so it does not impersonate GitHub Copilot's internal client or any other official client. Tokens are written straight to the Windows DPAPI credential store and are never displayed, logged, or backed up. A stored token expires like the provider's own token; sign in again (or use an API key) once it stops being accepted. Tests use a fake transport only — no live sign-in is ever performed by the test suite.

**Fallback models.** The **Fallback models** field in Settings takes a comma-separated, ordered list. When the selected model returns a **retryable** error — rate limit or quota (`429`), billing/insufficient-quota, resource-exhausted, capacity/overloaded, or OpenCode's `FreeTierError` — Jarvis automatically retries the request on the next model in the list and reports which model answered. **Non-retryable** errors (invalid key, unknown model, malformed request) are surfaced immediately instead of being retried. The primary model is always tried first on each new request, so a quota that resets is picked up automatically.

Note: free models hosted by OpenCode itself remain blocked to third-party clients by OpenCode's server policy (see **Free-tier policy** above). Use the upstream free providers directly instead.

## Capabilities ported from Mark-LV

Three assistant capabilities are adapted from Mark-LV's design (see **Credits and licensing**):

- **UI-issued confirmations.** Risky actions (`moderate`, `dangerous`) are approved by a real permission dialog in the UI thread; the model cannot grant its own approval because the confirmation state lives in the interface, not in the tool output.
- **Undo.** Jarvis keeps one shared undo stack per session. State-changing tools (`write_file`, `create_file`, `create_directory`, `move_window`, `resize_window`) snapshot their "before" state when they run, and the model can reverse its most recent change with the `undo` tool ("undo that"). Undoing a file write restores the previous content; undoing a created file/directory removes it; undoing a window move/resize restores the prior geometry. A failed undo is kept on the stack so it can be retried, and `undo` itself requires the same `moderate` approval as the actions it reverses.
- **Self-describing skills.** Any `*.py` module in `app/skills/` that declares a `TOOL` dict (name, description, permission level, handler) is auto-discovered and registered at startup — the registry never needs a code change to pick up a new skill. Modules with invalid or missing declarations are logged and skipped instead of breaking startup. Two example skills ship with Jarvis: `disk_free` and `uptime`.

  A commented authoring template ships as `app/skills/_template.py`; the leading underscore keeps it out of discovery. Copy it to `app/skills/your_skill.py` and fill in the `TOOL` dict plus a `handler` function:

  ```python
  TOOL = {
      "name": "hello",
      "description": "Say hello to someone.",
      "permission_level": "safe",  # safe | moderate | dangerous
      "parameters": {"name": "who to greet"},
  }

  def handler(name: str = "world") -> dict:
      return {"ok": True, "message": f"Hello, {name}!"}
  ```

  Choose the permission level carefully: `safe` runs without a prompt, while `moderate` and `dangerous` skills always surface the normal approval dialog before they run.

## Run tests

```powershell
python -m pytest -q
```

The same suite runs on GitHub Actions for every push and pull request to `main` (`.github/workflows/ci.yml`): Windows runner, Python 3.13, headless Qt, and pip caching.

## Build the standalone Windows executable

```powershell
python -m PyInstaller jarvis.spec
```

The output is generated under `dist/Jarvis/` as `Jarvis.exe` plus its required bundled runtime files. Keep the app folder together; the NSIS installer packages the complete folder. The PyInstaller spec resolves files relative to itself, so the command works from the repository root without a developer-specific absolute path.

## Windows installer

After building `dist/Jarvis/`, install the Nullsoft Scriptable Install System (NSIS) and compile the script from the repository root:

```powershell
makensis installer\installer.nsi
```

This creates `dist\Jarvis-Setup.exe`. For a release snapshot, copy `dist\Jarvis\` to `dist_<label>_<yyyymmdd>\Jarvis\` and point the build at it with the `DIST_ROOT` NSIS define so the working `dist/` output stays untouched:

```powershell
makensis /DDIST_ROOT=dist_release_20261011 installer\installer.nsi
``` The installer is a user-scoped install and does not require elevation; it installs into `%LOCALAPPDATA%\Programs\Jarvis` and registers its uninstall entry under the current user.

Uninstall removes application files and startup integration but keeps the user's database, logs, attachments, credentials, and backups in their profile under `%APPDATA%\Jarvis`. Updates are currently manual: build and install the newer release to the same location. Automatic update delivery is not implemented.

The standalone executable bundles Python dependencies, not a browser installation. Browser actions require Edge or Chrome installed on the machine; Playwright Chromium is an optional separate install. Voice input also depends on a working microphone and audio backend.

## Security notes

- API keys are stored in a secure OS credential flow rather than plaintext in app state.
- OAuth tokens from browser sign-in are stored in the same DPAPI store as JSON bundles; they are never logged or included in backups, and the UI never displays a token.
- Local data is handled with SQLite and stays on the machine.
- The app is designed for local-first use instead of browser-only execution.

## Credits and licensing

Jarvis draws design inspiration from existing open-source desktop agents; in particular [FatihMakes/Mark-LV](https://github.com/FatihMakes/Mark-LV) (Python, PyQt6) informs the assistant-concepts work (model fallback, UI-issued confirmations, undo, self-describing skills). Mark-LV is released under **CC BY-NC 4.0 (non-commercial, attribution required)**, so Jarvis uses it only for personal, non-commercial use, keeps this attribution, and adapts (ports) code rather than vendoring it wholesale. The ported pieces are `app/undo.py` (the shared undo stack), the `TOOL`-dict auto-discovery loader (`app/tool_loader.py`), and the existing UI-issued confirmation flow (already part of Jarvis, matching Mark-LV's "interface, not the model, issues approval" idea). Free-model listings follow [mnfst/awesome-free-llm-apis](https://github.com/mnfst/awesome-free-llm-apis).

## Encrypted backup and migration

Open **Settings** and choose **Export encrypted backup…** to save a `.jarvisbackup` file. Create and confirm a passphrase of at least 12 characters; Jarvis cannot recover a lost passphrase. The backup contains conversations, messages, durable memories, saved workflows, and the selected safe settings. OS credentials and secret settings are excluded, so configure credentials again on a new PC.

To move data, transfer the backup file to the other PC, open **Settings → Import / restore backup…**, enter the passphrase, and review the contents. **Merge** keeps existing data and adds the backup. **Replace personal data** deletes the existing conversations, messages, memories, and workflows after a separate confirmation; it preserves credentials and other settings.

Jarvis redacts common credential patterns found in exported text, but pattern-based detection cannot identify every secret. Avoid putting passwords or tokens in conversations, memories, or workflows, and inspect sensitive content before sharing a backup. Project and workflow paths may refer to folders that do not exist on the destination PC.

## Current status

This project is a working, shippable Windows desktop AI assistant. Everything in **Features** above is implemented and covered by a pytest suite (`python -m pytest -q`, 187 tests). The standalone executable and the NSIS installer are built and verified (silent install, launch, and uninstall all confirmed on Windows 10/11). Version `0.1.0`.

Honest limits:

- Model access is Chat Completions only; providers that expose only other protocols are reported as unsupported rather than emulated.
- OpenCode's own free tier is blocked to third-party clients by their server policy; use the upstream free providers instead.
- No local LLM is bundled, and no provider restrictions are bypassed.
- Updates are manual: build and install a newer release over the same location.
- Automatic update delivery, code signing, and crash reporting are not implemented.
