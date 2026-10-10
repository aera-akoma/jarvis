# Jarvis

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
- Conversation/session management
- Local memory store with search
- Workflow and settings persistence
- Secure API key storage
- Encrypted portable backups for conversations, memories, workflows, and selected settings
- Windows startup integration scaffold
- Standalone desktop packaging with PyInstaller
- Installer scaffold for Windows deployment

## Project structure

- `app/` — application code
- `tests/` — pytest regression tests
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

Open **Settings** from Jarvis and enter the provider's API base URL and API key. The key is stored with Windows DPAPI. Entering a non-empty key replaces the saved credential store with exactly that one key; leaving the box empty keeps the saved key. The key box intentionally stays empty after saving, and the status below it confirms whether a key is stored.

Jarvis currently uses the OpenAI-compatible Chat Completions API. For an OpenCode Console service-account key, set Runtime URL to `https://opencode.ai/inference/openai/v1`; Jarvis fetches the public model catalog from `https://opencode.ai/inference/v1/models` and sends chat requests to `https://opencode.ai/inference/openai/v1/chat/completions`. The Console catalog contains model IDs but does not identify each model's API family, so Jarvis matches those IDs against OpenCode's documented Console model-family table. This checks protocol compatibility only; it does not prove that the configured account can use a model. The **Test connection** action checks the catalog in a background worker and does not send a chat request or validate the saved key.

For an OpenCode key obtained from the TUI's `/connect` command, use `https://opencode.ai/zen/v1`. For an OpenCode Console service-account key (Console > Keys > Add Service Account > Add API Key), use `https://opencode.ai/inference/openai/v1`. These are two separate OpenCode routes that use **different keys**; picking the wrong one returns `HTTP 403` at the chat-completions POST. Jarvis does not switch between them or guess alternate paths. The default model `deepseek-v4-flash` and the previously common `kimi-k2.6` are both listed in the public catalog and documented for Chat Completions; workspace/account access is checked by the provider when a chat request is sent. Models offered only through `/responses`, `/messages`, Gemini, or System One endpoints are reported as unsupported because this client implements Chat Completions only. The local `opencode serve` session API is a different protocol and is not a compatible URL for this version of Jarvis.

Model discovery runs in a background worker with a six-second request timeout. If the model list is unavailable, Jarvis shows a provider error and keeps the chat window responsive. Logs are stored at `%APPDATA%\Jarvis\logs\jarvis.log`.

Provider errors show whether the catalog GET or Chat Completions POST failed, along with a sanitized endpoint and HTTP status. When the provider returns a structured error (for example OpenCode's `{"type":"error","error":{"type":"...","message":"..."}}`), Jarvis shows that type and message, redacted and length-bounded, because it is the most accurate diagnostic available. Jarvis never logs authorization headers, key values, or arbitrary unredacted response bodies; each request is recorded in `%APPDATA%\Jarvis\logs\jarvis.log` as `stage`, sanitized `endpoint`, `status`, `edge_blocked`, and provider `error_type` only.

**Known cause of `HTTP 403`.** OpenCode sits behind a CDN edge rule that rejects Python's default `Python-urllib/3.x` signature with `HTTP 403` (Cloudflare error `1010`, `browser_signature_banned`) *before* authentication is evaluated. Jarvis therefore sends an honest, non-browser `User-Agent: Jarvis/1.0` on every request, which matches OpenCode's own documented `curl https://opencode.ai/inference/v1/models` usage. Jarvis does not impersonate a browser, alter credentials, or bypass authentication. When this happens Jarvis reports it explicitly as an edge block and states that it is **not** an API-key, workspace, model, or quota problem — regenerating a key will not change it. Any other `403` comes from the OpenCode API itself and means the request was refused after the edge. The most common cause is pairing a key with the wrong route (`/connect` key on the Console URL, or a Console service-account key on the Zen URL); Jarvis now reports the provider's own error type and message and names both routes in that case. A `401` means the credential itself was rejected.

**Free-tier policy.** OpenCode restricts its free models to the official client: a request from any third-party tool is refused with `HTTP 403` `FreeTierError: OpenCode's free tier can only be used from within OpenCode`. This is a server-side policy, not a Jarvis bug, and Jarvis will not impersonate the official client to avoid it. Free models therefore cannot be used through Jarvis; choose a paid model, which needs Console credits or an OpenCode Go/Go Plus subscription. A request with a missing, empty, or unrecognised key is also treated as free tier, so this error can appear when the saved key has been rotated or revoked and Jarvis still holds the old one — re-enter the current key in Settings and press **Save** (the key box stays blank on purpose, so leaving it blank keeps the *old* key).

**Test model access.** The public catalog can succeed even when the account cannot use a model, so the **Test model access** button in Settings sends one tiny Chat Completions request with the saved key and the configured model and reports the provider's exact response (including any `error.type`). **Test connection** only checks the catalog. Use **Test model access** to confirm the saved key really reaches a model.

## Run tests

```powershell
python -m pytest -q
```

## Build the standalone Windows executable

```powershell
python -m PyInstaller jarvis.spec
```

The output is generated under `dist/Jarvis/` as `Jarvis.exe` plus its required bundled runtime files. Keep the app folder together; the NSIS installer packages the complete folder. The PyInstaller spec resolves files relative to itself, so the command works from the repository root without a developer-specific absolute path.

## Windows installer

After building `dist/Jarvis/`, install the Nullsoft Scriptable Install System (NSIS) and run `cd installer; makensis installer.nsi` from the repository root. This creates `dist/Jarvis-Setup.exe`. The installer accepts an optional `DIST_ROOT` NSIS define so a fresh build can be packaged without replacing another output. The installer is a user-scoped install and does not require elevation; it installs into `%LOCALAPPDATA%\Programs\Jarvis` and registers its uninstall entry under the current user.

Uninstall removes application files and startup integration but keeps the user's database, logs, attachments, credentials, and backups in their profile under `%APPDATA%\Jarvis`. Updates are currently manual: build and install the newer release to the same location. Automatic update delivery is not implemented.

The standalone executable bundles Python dependencies, not a browser installation. Browser actions require Edge or Chrome installed on the machine; Playwright Chromium is an optional separate install. Voice input also depends on a working microphone and audio backend.

## Security notes

- API keys are stored in a secure OS credential flow rather than plaintext in app state.
- Local data is handled with SQLite and stays on the machine.
- The app is designed for local-first use instead of browser-only execution.

## Encrypted backup and migration

Open **Settings** and choose **Export encrypted backup…** to save a `.jarvisbackup` file. Create and confirm a passphrase of at least 12 characters; Jarvis cannot recover a lost passphrase. The backup contains conversations, messages, durable memories, saved workflows, and the selected safe settings. OS credentials and secret settings are excluded, so configure credentials again on a new PC.

To move data, transfer the backup file to the other PC, open **Settings → Import / restore backup…**, enter the passphrase, and review the contents. **Merge** keeps existing data and adds the backup. **Replace personal data** deletes the existing conversations, messages, memories, and workflows after a separate confirmation; it preserves credentials and other settings.

Jarvis redacts common credential patterns found in exported text, but pattern-based detection cannot identify every secret. Avoid putting passwords or tokens in conversations, memories, or workflows, and inspect sensitive content before sharing a backup. Project and workflow paths may refer to folders that do not exist on the destination PC.

## Current status

This project is a working desktop-app foundation for a Windows AI assistant. It is intentionally scoped to a reliable local-first build rather than a broad web-style feature set, and it is structured to evolve into a fuller desktop agent over time.
