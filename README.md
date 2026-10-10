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

Jarvis currently uses the OpenAI-compatible Chat Completions API. For an OpenCode Console service-account key, set Runtime URL to `https://opencode.ai/inference/openai/v1`; Jarvis fetches its model catalog separately from `/inference/v1/models` and sends chat requests to `/inference/openai/v1/chat/completions`. For an OpenCode Zen API key, use `https://opencode.ai/zen/v1`. Jarvis filters OpenCode's mixed model catalog to models documented for Chat Completions and defaults to `deepseek-v4-flash`. Models offered only through `/responses` or `/messages` are not supported by this client. The local `opencode serve` session API is a different protocol and is not a compatible URL for this version of Jarvis.

Model discovery runs in a background worker with a six-second request timeout. If the model list is unavailable, Jarvis shows a provider error and keeps the chat window responsive. Logs are stored at `%APPDATA%\Jarvis\logs\jarvis.log`.

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

After building `dist/Jarvis/`, install the Nullsoft Scriptable Install System (NSIS) and run `cd installer; makensis installer.nsi` from the repository root. This creates `dist/Jarvis-Setup.exe`. The installer is a user-scoped install and does not require elevation; it installs into `%LOCALAPPDATA%\Programs\Jarvis` and registers its uninstall entry under the current user.

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
