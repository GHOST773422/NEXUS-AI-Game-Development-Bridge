# Changelog

## [0.10.0-stage10] - 2026-11-19

### Added
- **Tauri 2 Windows Desktop Shell (`apps/desktop/src-tauri/`)**: Added `config_store.rs` (`%LOCALAPPDATA%\NEXUS` config, restricted `daemon.token`, rotating `desktop-shell.log`), `daemon_manager.rs` (zero-dependency loopback TCP client, automatic independent service adoption vs. `CREATE_NO_WINDOW` PyInstaller sidecar / Python 3.12+ child spawning, graceful shutdown, diagnostics, adapter install guides), `version.rs`, and full IPC command registration in `lib.rs`.
- **Standalone Python Core CLI & Rotating File Logs (`core/nexus_core/`)**: Added `--version`, `--data-dir`, `--bind-host`, `--rest-port`, `--log-file`, Windows `%LOCALAPPDATA%\NEXUS` default data path, secret-redacting `RotatingFileHandler` (2 MB x 3 backups) + `nxs_` token pattern & `%s`-safe filter redaction in `logging_config.py`, and version/logging/bundled-adapter telemetry in `daemon.py` & `diagnostics.py`.
- **Offline Desktop UI & Adapter Instructions (`src/`)**: Updated `App.tsx`, `bridgeTransport.ts`, `DiagnosticsView.tsx`, and `EnginesView.tsx` so Tauri Desktop operates 100% locally without AI Studio or Express `/api/health` dependencies, and displays daemon lifecycle controls + Unity/Godot installation instructions.
- **Windows Packaging, Service & Clean Uninstall Scripts (`scripts/`, `docs/`)**: Synchronized `0.10.0` across all manifests, enabled NSIS + MSI targets in `tauri.conf.json`, created `scripts/stage-adapter-resources.mjs`, `scripts/build-python-sidecar.ps1`, updated `scripts/build-desktop.ps1`, added `scripts/install-windows-service.ps1`, `scripts/uninstall-nexus.ps1`, `scripts/verify-windows-install.ps1`, `docs/WINDOWS_PACKAGING_AND_INSTALL.md`, and `tests/python/test_stage10_packaging.py`.

## [0.9.0-stage9] - 2026-11-19

### Added
- **Stage 8 Autonomous Development Engine**: Implemented `AutonomousOrchestrator` (16-phase DAG execution workflow), `MultiAgentCoordinator` project/resource locking, `CheckpointManager`, `RetryPolicy`/`ExecutionLimits`, bounded repair deduplication, screenshot verification, REST endpoints (`/api/v1/tasks/locks`, `/execute`, `/approve`), MCP autonomous task tools, and updated `TasksView.tsx`.
- **Stage 9 Security, Recovery & Testing**: Added explicit 7 capability-based permission categories (`/api/v1/permissions/categories`), `validate_tool_arguments` + cross-platform drive/UNC sandboxing, manifest entrypoint traversal & SHA-256 enforcement, SQLite `operation_journal` & `failed_operations` tables, pre/post SHA-256 `file_change_manifest.json`, selective file rollback (`POST /api/v1/tasks/:id/rollback`, `GET /api/v1/tasks/:id/journal`), automatic daemon restart recovery (`recover_interrupted_tasks`), `adapters/unity/test_project/`, `docs/SECURITY_AND_RECOVERY.md`, `tests/python/test_stage8_autonomous_engine.py`, and `tests/python/test_stage9_security_recovery_perf.py`.

### Fixed
- **Dev Server (`server.ts`)**: Added `allowedHosts: true` in Vite middleware config (fixing HTTP 403 host blocks on proxied requests), `--port`/`--host` CLI arg parsing, symlink-safe entry detection, and graceful `SIGINT`/`SIGTERM` shutdown.
- **Godot Addon Sync Integrity**: Restored intact `adapters/godot/addons/nexus_bridge/` source scripts and synced `adapters/godot/test_project/addons/nexus_bridge/`.

## [0.8.0-stage7] - 2026-11-18

### Added
- Completed native Godot `4.2+` GDScript `EditorPlugin` (`adapters/godot/addons/nexus_bridge/`): `plugin.cfg`, `plugin.gd`, `nexus_version.gd` (4.2+ checks & deterministic project ID), `nexus_state_plugins.gd` (`EditorDebuggerPlugin`, `EditorExportPlugin`, error ring buffer, `godot.log` tail), `nexus_tool_registry.gd` (18 version-aware Godot tools across 22 capabilities), `nexus_godot_handlers.gd` (`EditorInterface`, `EditorUndoRedoManager`, `ClassDB`, `GDScript.reload()`, `ResourceSaver`, `Viewport` PNG capture, `export_presets.cfg`), `nexus_tcp_server.gd` (main-thread `_process` `127.0.0.1` TCP JSON-RPC 2.0), and `nexus_dock.gd`.
- Created pre-configured Godot 4.x test project (`adapters/godot/test_project/` with `project.godot`, `scenes/main.tscn`, `scripts/test_actor.gd`, `export_presets.cfg`, `tests/nexus_godot_verification.gd`) and `scripts/sync-godot-addon.mjs` (`npm run sync:godot-addon`).
- Enforced daemon-side `compatible=False` rejection (`AdapterCompatibilityError`) inside `AdapterManager.connect_adapter`, updated `adapters/godot/nexus-adapter.manifest.json`, added `docs/GODOT_ADAPTER_GUIDE.md`, and added `tests/python/test_godot_adapter_integration.py`.

## [0.7.0-stage6] - 2026-11-18

### Added
- Built native Unity Editor UPM package `com.nexus.bridge` (`adapters/unity/`): `NexusUnityBridgeEntrypoint` (`[InitializeOnLoad]`, `AssemblyReloadEvents`, multi-project port assignment, Status `EditorWindow`), `NexusSimpleJson` (zero-dependency RFC-8259 JSON parser/serializer), `NexusMainThreadDispatcher` (`EditorApplication.update`), `NexusUnityStateTracker` (compilation, threaded console logs, BuildReport), `NexusUnityTcpServer` (loopback `127.0.0.1` JSON-RPC 2.0), `NexusUnityHandlers`, and `NexusUnityToolRegistry` (17 typed Unity tools covering all 21 requested capabilities).
- Added Unity Test Framework NUnit EditMode test suite (`adapters/unity/Tests/Editor/NexusUnityIntegrationTests.cs`) for real Unity project verification on Windows 10/11.
- Updated `engine_manager.py`, `capability_discovery.py`, `rest_gateway.py`, and `mcp_server.py` so real connected engine adapters reflect accurate live engine status and automatically route verified tool executions through `PermissionManager` approvals.
- Documented Unity setup & verification in `docs/UNITY_ADAPTER_GUIDE.md` and added `tests/python/test_unity_adapter_integration.py`.

## [0.6.0-stage5] - 2026-11-18

### Added
- Created `core/nexus_core/adapters/` implementing `UniversalEngineAdapter` (all 11 canonical methods), `ProtocolEngineAdapter`, language-neutral JSON-RPC `2.0` NDJSON transports (`StdioAdapterTransport`, `TcpLoopbackAdapterTransport`), `AdapterManifest` + `validate_adapter_compatibility`, and `AdapterManager` (lifecycle FSM, capability registry, health monitoring, error history, and automatic exponential-backoff `ReconnectionPolicy`).
- Added SQLite `installed_adapters` persistence, `AdapterCompatibilityError` (`422`) / `AdapterProtocolError` (`502`), and authenticated `/api/v1/adapters*` REST routes in `rest_gateway.py` & `integrations/rest-api/schema.ts`.
- Created multi-language `nexus-adapter.manifest.json` specifications for Unity (`C#`), Godot (`GDScript`), and Unreal (`C++`), plus explicit out-of-process `adapters/test-adapter/test_adapter_server.py` supporting both `stdio` and `tcp-loopback` transports with strict isolation from real `connectedEngineCount` and `CoreToolRegistry.verified_count`.
- Documented protocol & manifest schemas (`docs/ADAPTER_PROTOCOL.md`, `docs/ADAPTER_MANIFEST_SPEC.md`), updated `sdk/ts/adapter.ts`, `sdk/ts/ipc.ts`, `PluginsView.tsx`, and added `tests/python/test_universal_adapter_framework.py`.

## [0.5.0-stage4] - 2026-11-18

### Added
- Created independent AI provider modules (`core/nexus_core/providers/` & `integrations/ai-providers/`): `gemini.py`, `claude.py`, `openai_provider.py`, `openai_compatible.py`, and `custom.py` implementing `BaseAIProvider` with connection verification, model selection, non-streaming generation, SSE streaming, usage/latency telemetry, and structured error mapping (`ProviderAuthError`, `ProviderRateLimitError`, `ProviderUpstreamError`).
- Added `CredentialStore` (`credentials.py`) supporting `env://`, `wincred://` (Windows `advapi32` ctypes + `0600` POSIX vault fallback), and `vault://`, plus `ai_providers` SQLite non-secret persistence and `x-api-key`/`x-goog-api-key` log redaction.
- Implemented full MCP JSON-RPC `2.0` server (`core/nexus_core/mcp_server.py`, `integrations/mcp/server.py`, `python -m core.nexus_core --mcp-stdio`) with dynamic `CoreToolRegistry` + `PermissionManager` tool discovery/execution, 6 `nexus://` resources, 3 game-dev prompts, `stdio` transport, and Bearer-authenticated loopback `Streamable HTTP` (`/mcp`).
- Added server-side Gemini `@google/genai` verification and generation routes in `server.ts`, updated `ConnectionsView.tsx` with active model presets, verification checks, and external MCP client snippets, documented setup in `docs/AI_PROVIDERS_AND_MCP.md`, and added `tests/python/test_ai_providers_and_mcp.py`.

## [0.4.0-stage3] - 2026-11-18
- Implemented 12-module Python Core daemon, SQLite persistence, Bearer auth, loopback HTTP/WS gateways, and replaceable frontend `BridgeTransport`.

## [0.3.0-stage2] - 2026-11-18
- Built the complete 10-view NEXUS Control Center UI, dedicated `controlCenterService`, and explicit Demo Fixture mode.

## [0.2.0-stage1] - 2026-11-18
- Established monorepo layout, Express preview backend, shared SDKs, and test/lint tooling.

## [0.1.0-stage0] - 2026-11-17
- Initial architecture baseline and control center shell.
