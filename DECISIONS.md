# NEXUS Architectural Decision Records

## ADR-001: Strict Service Boundary Between Frontend and Bridge
- **Date**: 2026-11-17
- **Status**: Accepted
- **Decision**: All frontend views communicate exclusively through `BridgeTransport` and typed `/api/*` endpoints rather than embedding engine logic, filesystem paths, or AI SDKs in React components.

## ADR-002: Explicit Runtime Status Taxonomy Without Simulated Indicators
- **Date**: 2026-11-17
- **Status**: Accepted
- **Decision**: Standardize all subsystem, adapter, tool, and task states to `Connected`, `Disconnected`, `Available`, `Unavailable`, `Running`, `Failed`, and `Planned`.

## ADR-003: Separation of Built-in AI Providers and External MCP Clients
- **Date**: 2026-11-17
- **Status**: Accepted
- **Decision**: Model outbound AI providers (`integrations/ai-providers/`) separately from inbound external MCP clients (`integrations/mcp/`). Configuring an API provider credential never implies or creates an MCP desktop client connection.

## ADR-004: Native Engine Integrations Over Lowest-Common-Denominator Wrappers
- **Date**: 2026-11-17
- **Status**: Accepted
- **Decision**: Implement Unity integration as a native C# UPM package (`adapters/unity/`) and Godot integration as a native GDScript `EditorPlugin` (`adapters/godot/`), mapped to the shared 13-method `EngineAdapterContract`.

## ADR-005: Local-Only Default Network Binding & SSRF-Guarded Probe
- **Date**: 2026-11-18
- **Status**: Accepted
- **Decision**: Bind local daemon services strictly to `127.0.0.1` (requiring explicit `NEXUS_ALLOW_REMOTE_BIND=true` override) and validate that `POST /api/bridge/probe` in `server.ts` accepts only loopback hostnames (`127.0.0.1` or `localhost`).

## ADR-006: TypeScript 7 (`tsgo`) Linting via `oxlint` + `tsc --noEmit`
- **Date**: 2026-11-18
- **Status**: Accepted
- **Decision**: Because `typescript-eslint` currently blocks TypeScript `7.0.2`, use `tsc --noEmit` with `"strict": true` for type safety, `oxlint` for TypeScript/React lint rules, and Prettier for formatting checks.

## ADR-007: Dual Stdlib Loopback Runtime + FastAPI Factory for Python Daemon
- **Date**: 2026-11-18
- **Status**: Accepted
- **Decision**: Implement REST request dispatch (`dispatch_rest_request`) and RFC-6455 WebSocket event streaming on Python stdlib (`asyncio` + `sqlite3`) alongside a `create_fastapi_app(daemon)` factory, enabling verified independent daemon startup and integration tests inside Python 3.11+ containers without third-party wheels while supporting FastAPI/Uvicorn in local Python 3.12+ deployments.

## ADR-008: Windows Credential Manager + Restricted Vault for Provider Secrets & Dual-Transport MCP Server
- **Date**: 2026-11-18
- **Status**: Accepted
- **Decision**: Resolve built-in provider API keys at call time via `CredentialStore` (`advapi32` Windows Credential Manager on `win32`, `0600` vault file / `env://` fallback) while keeping SQLite, frontend bundles, browser storage, and logs secret-free; implement MCP JSON-RPC `2.0` (`stdio` + Bearer-guarded `Streamable HTTP`) directly on `NexusDaemon`'s shared `CoreToolRegistry` and `PermissionManager`.

## ADR-009: Language-Neutral NDJSON Adapter Protocol & Strict Test Adapter Isolation
- **Date**: 2026-11-18
- **Status**: Accepted
- **Decision**: Standardize local engine adapter IPC on UTF-8 NDJSON JSON-RPC `2.0` over `stdio` or `127.0.0.1` `tcp-loopback` so `C#`, `GDScript`, `C++`, and third-party adapters never depend on Python; require explicit `isTestAdapter: true` attestation and isolate test harnesses from `connectedEngineCount` and `CoreToolRegistry.verified_count`.

## ADR-010: Unity Editor Main-Thread Marshaling & Zero-Dependency JSON-RPC
- **Date**: 2026-11-18
- **Status**: Accepted
- **Decision**: Execute Unity Editor socket reads asynchronously off-thread, marshal every UnityEngine/UnityEditor API call through `NexusMainThreadDispatcher` (`EditorApplication.update`), include an internal RFC-8259 JSON serializer (`NexusSimpleJson`) to eliminate third-party UPM package dependencies, guard mutations against `isCompiling`/`isUpdating`/`isPlaying`, and wrap scene/object mutations in `Undo`.

## ADR-011: Godot 4.2+ EditorPlugin Main-Thread TCPServer Polling & Version Compatibility Gating
- **Date**: 2026-11-18
- **Status**: Accepted
- **Decision**: Poll `TCPServer` and `StreamPeerTCP` NDJSON frames synchronously inside `EditorPlugin._process(delta)` on Godot's main thread (avoiding background-thread access to `SceneTree`, `EditorInterface`, and `Viewport`), wrap edits in `EditorUndoRedoManager`, keep Godot `test_project/addons/nexus_bridge/` byte-synchronized via `scripts/sync-godot-addon.mjs`, and enforce `compatible=false` rejection via `AdapterCompatibilityError` inside `AdapterManager`.

## ADR-012: Bounded 16-Phase Autonomous Orchestration & Multi-Agent Project Locking
- **Date**: 2026-11-19
- **Status**: Accepted
- **Decision**: Execute multi-step game development tasks through a deterministic 16-phase DAG pipeline (`AutonomousOrchestrator`) guarded by `MultiAgentCoordinator` project/resource locks, explicit `PermissionManager` approval gates (`assets:modify`, `build:export`), `process:restricted` hard-blocking for autonomous agents, and SHA-256 operation fingerprint deduplication so identical failed mutations never retry indefinitely.

## ADR-013: SQLite Operation Journaling, Selective File Rollback & Cross-Platform Sandboxing
- **Date**: 2026-11-19
- **Status**: Accepted
- **Decision**: Persist every operation start/completion (`operation_journal`), failure context with redacted secrets (`failed_operations`), and pre/post SHA-256 `file_change_manifest.json` artifacts per checkpoint; expose single-file/subset restoration (`selective_rollback`), detect Windows drive/UNC prefixes cleanly even when running in POSIX test sandboxes, and transition orphaned `Running` tasks to `Unavailable` automatically on daemon restart.

## ADR-014: Zero-Dependency Rust Loopback IPC, Sidecar/Service Dual Mode & Offline Desktop Execution
- **Date**: 2026-11-19
- **Status**: Accepted
- **Decision**: Implement `DaemonSupervisor` TCP HTTP/1.1 loopback communication in `apps/desktop/src-tauri/` directly on Rust `std::net::TcpStream` (avoiding external HTTP client crates), support both PyInstaller bundled sidecar execution (`CREATE_NO_WINDOW`) and pre-existing independent Python 3.12+ services (`LaunchMode::ExternalIndependent`), enforce strict `keepDaemonAliveOnExit` / graceful `/api/v1/daemon/shutdown` semantics, stage Unity/Godot adapters into Tauri `resources/adapters/`, and bypass Express `/api/health` preview checks whenever running inside `TauriDesktop` so packaged Windows builds never depend on Google AI Studio.

