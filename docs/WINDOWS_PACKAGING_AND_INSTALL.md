# NEXUS Stage 10 — Windows 10/11 Desktop Packaging, Deployment & Clean VM Testing Guide

## Overview

NEXUS packages as a native **Windows 10/11 (x64)** desktop application built with **Tauri 2 + Rust + React + TypeScript + Python 3.12+ + SQLite**, alongside native **Unity C# (UPM)** and **Godot 4.2+ GDScript (`EditorPlugin`)** engine adapters.

- **Zero Google AI Studio dependency**: The desktop shell loads the offline compiled frontend (`dist/`) directly via Tauri WebView2 and communicates strictly over local IPC / loopback (`127.0.0.1`).
- **Zero mandatory cloud server**: All project discovery, scene/node inspection, script edits, SQLite journals, checkpoints, MCP `stdio`/`Streamable HTTP`, and adapter operations execute locally. Cloud AI providers (Gemini, Claude, OpenAI) are optional user-configured connections.
- **Independent Background Daemon**: `nexus-daemon` (`core/nexus_core`) runs either as a bundled PyInstaller sidecar launched silently (`CREATE_NO_WINDOW`) by the Tauri shell OR as an independent Python 3.12+ background task (`scripts/install-windows-service.ps1`), so external AI/MCP clients and game engines remain connected even if the desktop UI exits.

---

## 1. Documented Windows Build Prerequisites

Install the following on a Windows 10/11 64-bit build machine:

1. **Node.js 22+ & npm** (`node --version`)
2. **Python 3.12+ (64-bit)** (`python --version`) with `pip`
3. **Rust Toolchain (MSVC target)**: `rustup toolchain install stable-x86_64-pc-windows-msvc`
4. **Visual Studio 2022 Build Tools** with **Desktop development with C++** + **Windows 10/11 SDK**
5. **Microsoft Edge WebView2 Runtime** (pre-installed on Windows 11; bootstrapper configured in `tauri.conf.json` for Windows 10)
6. **Tauri CLI v2**: `cargo install tauri-cli --version "^2.0.0"`
7. **WiX Toolset v3 / NSIS** (automatically downloaded by Tauri bundler on Windows when generating `.msi` and `-setup.exe` installers)

---

## 2. Architecture of Packaged Artifacts

| Component | Source / Staged Location | Windows Runtime Location |
| :--- | :--- | :--- |
| Desktop Shell (`NEXUS.exe`) | `apps/desktop/src-tauri/` | `%ProgramFiles%\NEXUS\NEXUS.exe` |
| Python Core Sidecar | `apps/desktop/src-tauri/binaries/nexus-daemon-x86_64-pc-windows-msvc.exe` | Sidecar next to `NEXUS.exe` |
| Offline React UI | `dist/` (`frontendDist: "../../../dist"`) | Embedded inside Tauri binary |
| Unity Adapter UPM | `apps/desktop/src-tauri/resources/adapters/unity/` | `<InstallDir>\resources\adapters\unity\` |
| Godot `EditorPlugin` | `apps/desktop/src-tauri/resources/adapters/godot/addons/nexus_bridge/` | `<InstallDir>\resources\adapters\godot\addons\nexus_bridge\` |
| Config, SQLite & Token | `%LOCALAPPDATA%\NEXUS\` | `desktop-config.json`, `nexus.db`, `daemon.token` |
| Rotating Logs | `%LOCALAPPDATA%\NEXUS\logs\` | `desktop-shell.log`, `nexus-daemon.log` |

### Application Version Management
All manifests are synchronized cleanly to **`0.10.0`**:
- `package.json` (`"version": "0.10.0"`)
- `core/pyproject.toml` (`version = "0.10.0"`)
- `core/nexus_core/config.py` (`APP_VERSION = "0.10.0"`)
- `apps/desktop/src-tauri/Cargo.toml` (`version = "0.10.0"`)
- `apps/desktop/src-tauri/tauri.conf.json` (`"version": "0.10.0"`)

---

## 3. Building the Windows Installers (Sidecar or Separate Service)

### Option A — Full Standalone Windows Installer (Bundled Python Sidecar)
Builds `dist/`, stages Unity & Godot adapters, freezes Python Core via PyInstaller (`scripts/build-python-sidecar.ps1`), runs test suites, and creates NSIS (`.exe`) and MSI (`.msi`) installers:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-desktop.ps1
```

Resulting installers on Windows:
- `apps\desktop\src-tauri\target\release\bundle\nsis\NEXUS_0.10.0_x64-setup.exe`
- `apps\desktop\src-tauri\target\release\bundle\msi\NEXUS_0.10.0_x64_en-US.msi`

### Option B — Desktop Shell + Separate Python 3.12+ Background Service
If you prefer running Python Core from a standard virtual environment or Windows Scheduled Task:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-python.ps1
powershell -ExecutionPolicy Bypass -File scripts\install-windows-service.ps1
powershell -ExecutionPolicy Bypass -File scripts\build-desktop.ps1 -ServiceMode
```

When `NEXUS.exe` launches, `DaemonSupervisor` automatically probes `http://127.0.0.1:47100/health` first and attaches cleanly (`LaunchMode::ExternalIndependent`) instead of spawning a duplicate process.

---

## 4. Installing Engine Adapters & Connecting External AI Clients

1. **Launch NEXUS** (or confirm `nexus-daemon` is running independently).
2. **Install Unity Adapter**:
   - In Unity Editor (`2022.3 LTS+`), open **Window -> Package Manager -> + -> Add package from disk...**
   - Select `<InstallDir>\resources\adapters\unity\package.json` (or `adapters\unity\package.json` from source).
   - Open **Window -> NEXUS Bridge** and verify endpoint `http://127.0.0.1:47100`.
3. **Install Godot Adapter**:
   - Copy `<InstallDir>\resources\adapters\godot\addons\nexus_bridge\` into `<YourGodotProject>\addons\nexus_bridge\`.
   - Enable **NEXUS Bridge** under **Project -> Project Settings -> Plugins**.
4. **Connect External MCP / AI Clients**:
   - Stdio command: `nexus-daemon.exe --mcp-stdio` (or `python -m core.nexus_core --mcp-stdio`)
   - Streamable HTTP endpoint: `http://127.0.0.1:47102/mcp` with `Authorization: Bearer <token>` from `%LOCALAPPDATA%\NEXUS\daemon.token`.

---

## 5. Clean Windows VM Install, Diagnostics & Uninstall Verification

Run inside a clean Windows 10/11 x64 VM after building the installer:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-windows-install.ps1 `
  -InstallerExe "apps\desktop\src-tauri\target\release\bundle\nsis\NEXUS_0.10.0_x64-setup.exe" `
  -RunUninstallCheck
```

To uninstall manually or remove leftover services cleanly:

```powershell
# Preserves %LOCALAPPDATA%\NEXUS SQLite history & configuration:
powershell -ExecutionPolicy Bypass -File scripts\uninstall-nexus.ps1

# Full clean removal including user configuration, tokens, SQLite DB & logs:
powershell -ExecutionPolicy Bypass -File scripts\uninstall-nexus.ps1 -PurgeUserData
```

> **Build Environment Disclosure**: Automated container tests verify CLI offline execution, loopback HTTP/diagnostics/shutdown, rotating secret-redacting log files, Rust IPC source modules, Tauri CSP/bundler schemas, adapter resource staging, and Vite offline bundle generation. Compiling native `.exe` / NSIS / MSI binaries with `cargo tauri build` + PyInstaller and running `verify-windows-install.ps1` **must be executed on a Windows 10/11 x64 host** and have NOT been executed in Google AI Studio's Linux sandbox.
