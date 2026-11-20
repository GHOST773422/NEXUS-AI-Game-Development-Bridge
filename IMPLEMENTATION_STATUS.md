# NEXUS — Architecture Implementation Status Matrix

**Version**: `0.10.0` (synchronized across `package.json`, `core/pyproject.toml`, `core/nexus_core/config.py`, `apps/desktop/src-tauri/Cargo.toml`, `apps/desktop/src-tauri/tauri.conf.json`)  
**Last Audited**: `2026-11-20`  
**Audit Scope**: Complete feature-by-feature mapping of `ARCHITECTURE.md`, `docs/*`, `sdk/*`, `tools/categories.ts`, `src/data/architectureSpec.ts`, Stage 9 Security/Testing/Recovery, and Stage 10 Native Windows Desktop Packaging against current codebase files and verified test runs.

---

## Classification Key

Every architecture specification feature in this document uses strictly one of the following five statuses:

- `IMPLEMENTED AND VERIFIED` — Implemented in source AND verified via automated tests, static checks, build checks, or live daemon/protocol execution in the current workspace.
- `IMPLEMENTED BUT NOT VERIFIED` — Implemented cleanly in source and structurally checked, but **not** executed against native target host runtimes absent in this Linux container (`Unity.exe`, `Godot 4.2+` GUI binary, `cargo tauri build`, PyInstaller, Windows `advapi32`, clean Windows 10/11 VM, or external cloud AI API keys).
- `PARTIALLY IMPLEMENTED` — Implemented in part with concrete functional coverage gaps, missing tool categories across engines, or optional runtime dependencies unexercised end-to-end.
- `NOT IMPLEMENTED` — Explicitly scoped as future/deferred or absent from implementation code.
- `UNSUPPORTED` — Impossible or blocked by host OS / browser sandbox / target constraints by design or environment incompatibility.

---

## Executive Summary by Domain

| Domain | Primary Classification | Verified Evidence |
| :--- | :--- | :--- |
| **React 19 Control Center (`src/`, `dist/`)** | `IMPLEMENTED AND VERIFIED` | 10 views wired to live daemon REST/WebSocket hydration, honest disconnected defaults, offline `dist/` build, 19/19 Vitest + `tsc` + `oxlint` + `prettier` pass. |
| **Express Preview Backend (`server.ts`)** | `IMPLEMENTED AND VERIFIED` | `/api/health`, `/api/runtime/capabilities`, `/api/protocol/schemas`, SSRF-guarded `/api/bridge/probe`, and `@google/genai` routes verified by `tests/ts/server.test.ts`. |
| **Python Core Daemon (`core/nexus_core/`)** | `IMPLEMENTED AND VERIFIED` | 40/40 `unittest` tests pass on stdlib async runtime (SQLite WAL, REST `47100`, WS `47101`, MCP `47102`/stdio, security, checkpoints, recovery, DAG orchestrator). Optional `fastapi`/`uvicorn`/`aiosqlite`/`websockets` wheels not installed (`IMPLEMENTED BUT NOT VERIFIED`). |
| **AI Providers (`core/nexus_core/providers/`)** | `PARTIALLY IMPLEMENTED` | Gemini, Claude, OpenAI, OpenAI-Compatible, Custom + incremental SSE + `CredentialStore` verified against local loopback mock HTTP servers; Windows `advapi32` & live cloud keys not executed in sandbox. |
| **Universal Engine Adapter Runtime** | `IMPLEMENTED AND VERIFIED` | Language-neutral NDJSON JSON-RPC `2.0` (`stdio` + `tcp-loopback`), 11 protocol methods, SemVer/checksum checks, exponential backoff reconnect verified with synthetic harness & unit tests. |
| **Unity C# UPM Plugin (`adapters/unity/`)** | `IMPLEMENTED BUT NOT VERIFIED` | 17 typed `unity.*` tools, main-thread `ConcurrentQueue`, `Undo.*`, AssetDatabase/CompilationPipeline/BuildReport hooks verified via source & Python TCP protocol tests; live `Unity.exe` run pending Windows host. |
| **Godot 4.2+ GDScript Plugin (`adapters/godot/`)** | `IMPLEMENTED BUT NOT VERIFIED` | 18 version-aware `godot.*` tools, `EditorUndoRedoManager`, `EditorFileSystem`, debugger/viewport capture, safe `modify_node` validation verified via source, sync, & Python TCP tests; live `godot4` run pending host binary. |
| **Unreal C++ Adapter (`adapters/cpp/`)** | `NOT IMPLEMENTED` | Contains `README.md` and `nexus-adapter.manifest.json` specification contract only (`Planned`). |
| **Tool Categories (19 Namespaces)** | `PARTIALLY IMPLEMENTED` | Core Inspection, Scene, Object, Component, Script, Asset, Rendering, Debugging, Testing, Profiling, Build Status covered (`17` Unity / `18` Godot tools); 9 specialized domains (`Material`, `Shader`, `Lighting`, `Physics`, `Animation`, `Audio`, `UI`, `Navigation`, full automated Player Build) remain contract namespaces only. |
| **Security, Permissions & Recovery (Stage 9)** | `IMPLEMENTED AND VERIFIED` | 7 permission categories, unified REST/MCP/Orchestrator argument + traversal + destructive approval checks, loopback + Bearer auth, redaction, checkpoints, file manifests, journals, and selective rollback pass all Stage 9 tests. |
| **Tauri 2 Shell & Windows Packaging (Stage 10)** | `IMPLEMENTED BUT NOT VERIFIED` | Rust IPC shell (`lib.rs`, `daemon_manager.rs`, `config_store.rs`, `version.rs`), NSIS/MSI config, resource staging, and PowerShell build/service/uninstall/verify scripts checked; native `.exe`/`.msi` build & clean Windows VM test pending Windows host. |

---

## 1. Core Logical Subsystems (17 Architectural Components)

Mapped from `ARCHITECTURE.md` and `src/data/architectureSpec.ts` (`ARCHITECTURAL_SUBSYSTEMS`):

| # | Subsystem | Implementation Path(s) | Status | Notes & Evidence |
| :-: | :--- | :--- | :--- | :--- |
| 1 | **Desktop Frontend** | `src/App.tsx`, `src/components/views/*`, `src/services/*` | `IMPLEMENTED AND VERIFIED` | 10-view React 19 + Tailwind SPA; hydrates live daemon REST endpoints (`/api/v1/*`) + WebSocket `/events`; compiles cleanly (`npm run build`, `oxlint`, `prettier`, `tsc --noEmit`). |
| 2 | **Desktop Shell** | `apps/desktop/src-tauri/src/{lib.rs,daemon_manager.rs,config_store.rs,version.rs,main.rs}` | `IMPLEMENTED BUT NOT VERIFIED` | Implements 12 Tauri 2 IPC commands, `CREATE_NO_WINDOW` daemon spawn/adoption, `%LOCALAPPDATA%\NEXUS` storage, IPv6-safe `[::1]` loopback TCP client, rotating `desktop-shell.log`. Not compiled with `cargo` in Linux sandbox. |
| 3 | **Background Daemon** | `core/nexus_core/{daemon.py,__main__.py,config.py}` | `IMPLEMENTED AND VERIFIED` | Headless Python async daemon (`--serve`, `--mcp-stdio`, `--health-once`, `--version`, `--data-dir`, `--bind-host`, `--rest-port`, `--log-file`) verified live & in `test_core_backend.py` / `test_stage10_packaging.py`. |
| 4 | **Communication Gateway** | `core/nexus_core/{daemon.py,rest_gateway.py,mcp_server.py}`, `integrations/websocket/service.py` | `IMPLEMENTED AND VERIFIED` | Multiplexes loopback `127.0.0.1` ports (`47100` REST, `47101` WebSocket, `47102` MCP Streamable HTTP) + stdio cleanly. |
| 5 | **AI Provider Registry** | `core/nexus_core/providers/{registry.py,base.py,gemini.py,claude.py,openai_provider.py,openai_compatible.py,custom.py}` | `IMPLEMENTED AND VERIFIED` | CRUD, verification, incremental SSE streaming (`http_sse_line_stream`), latency/token telemetry, and non-secret SQLite persistence verified against loopback mock upstream servers in `test_ai_providers_and_mcp.py`. |
| 6 | **MCP Server** | `core/nexus_core/mcp_server.py`, `integrations/mcp/{server.py,schema.ts}` | `IMPLEMENTED AND VERIFIED` | JSON-RPC `2.0` (`2025-03-26`) over `--mcp-stdio` and Bearer-authenticated HTTP `/mcp`; exposes 12 core bridge tools + dynamic connected adapter tools + 6 `nexus://` resources + 3 prompts with unified security checks. |
| 7 | **REST API** | `core/nexus_core/rest_gateway.py`, `integrations/rest-api/{schema.ts,router.py}` | `IMPLEMENTED AND VERIFIED` | 35 daemon-only endpoints (40 total contracts in `schema.ts`) verified via `dispatch_rest_request` & live HTTP/1.1 stdlib server (`StdlibLoopbackHttpServer`). Optional FastAPI factory (`create_fastapi_app`) not exercised (`fastapi` absent in sandbox). |
| 8 | **WebSocket Event Service** | `integrations/websocket/service.py`, `integrations/websocket/schema.ts` | `IMPLEMENTED AND VERIFIED` | Custom async RFC-6455 server on `127.0.0.1:47101`; supports `Authorization: Bearer` header & `?token=` query auth for WebView2/browsers, EOF watch, close frames (`0x88`), and sub-second teardown. |
| 9 | **Engine Manager** | `core/nexus_core/engine_manager.py` | `IMPLEMENTED AND VERIFIED` | Probes OS install paths/Registry for Unity Hub & Godot `4.x`, supports verified `PATCH /api/v1/engines/{engine}` custom path overrides, explicitly marks missing paths `Unavailable`, binds connected adapters. |
| 10 | **Tool Registry** | `core/nexus_core/tool_registry.py`, `tools/categories.ts` | `IMPLEMENTED AND VERIFIED` | Enforces dynamic verified-only registration (`registeredToolCount == 0` until real editor attaches), blocks `Planned`/`Unavailable` stubs, and isolates `test-adapter` tools from production counts. |
| 11 | **Universal Adapter Runtime** | `core/nexus_core/adapters/{interface.py,manager.py,manifest.py,protocol.py}` | `IMPLEMENTED AND VERIFIED` | Language-neutral NDJSON JSON-RPC `2.0` over `tcp-loopback` & `stdio`; manages lifecycle FSM (`Installed` -> `Validated` -> `Connecting` -> `Connected` / `Degraded` / `Reconnecting` / `Disconnected` / `Failed`) and reconnect backoff. |
| 12 | **Project Context Engine** | `core/nexus_core/{project_registry.py,orchestrator.py}` | `IMPLEMENTED AND VERIFIED` | Persistent SQLite project registry with sandbox validation; captures scene state, hierarchy, scripts, assets, logs, and viewport screenshots prior to task planning. |
| 13 | **Autonomous Task Orchestrator** | `core/nexus_core/{orchestrator.py,task_manager.py,concurrency.py}` | `IMPLEMENTED AND VERIFIED` | 16-phase DAG state machine with priority queues, dependency checking, non-duplicate bounded repair loop, approval checkpoints, multi-agent project/resource locks, and real Phase 14/15 verification. |
| 14 | **Permission Manager** | `core/nexus_core/security.py`, `config/permissions.default.json` | `IMPLEMENTED AND VERIFIED` | 7 capability-based categories, unified path-traversal/drive/UNC sandboxing, tool argument depth/key limits, executable allowlist, destructive gate enforcement across REST/MCP/Orchestrator. |
| 15 | **Storage Manager** | `core/nexus_core/storage.py` | `IMPLEMENTED AND VERIFIED` | SQLite (`PRAGMA journal_mode=WAL`) storing `projects`, `tasks`, `ai_providers`, `installed_adapters`, `checkpoints`, `operation_journal`, `failed_operations`, `audit_logs`, `daemon_state` (`aiosqlite` optional; stdlib `sqlite3` verified). |
| 16 | **Recovery Manager** | `core/nexus_core/{checkpoints.py,task_manager.py}` | `IMPLEMENTED AND VERIFIED` | SHA-256 pre/post file snapshots, `file_change_manifest.json`, persistent operation journals, failed-op records, selective file rollback, and interrupted-task recovery on daemon restart. |
| 17 | **Diagnostics & Logging** | `core/nexus_core/{diagnostics.py,logging_config.py}` | `IMPLEMENTED AND VERIFIED` | Live `GET /api/v1/diagnostics` with SQLite `PRAGMA integrity_check`, connected adapter parity, bundled-adapter staging checks, redacted config snapshots, and rotating `nexus-daemon.log` (2 MB x 3 backups). |

---

## 2. Frontend Control Center & Bridge Transports (`src/`, `sdk/ts/`, `server.ts`)

| Feature / Component | Location | Status | Notes & Evidence |
| :--- | :--- | :--- | :--- |
| **Dashboard View** | `src/components/views/DashboardView.tsx` | `IMPLEMENTED AND VERIFIED` | Displays live runtime host, daemon connection, real connected engine/tool counts, and Demo Fixture clarity banner. |
| **Connections View (AI Providers & MCP)** | `src/components/views/ConnectionsView.tsx` | `IMPLEMENTED AND VERIFIED` | Supports custom provider create/delete (`DELETE /api/v1/providers/:id`), secret storage via daemon, verification (`POST /api/v1/providers/:id/verify` or `/api/ai/providers/verify`), and live MCP `/api/v1/mcp/status` tools/resources/prompts. |
| **Engines View** | `src/components/views/EnginesView.tsx` | `IMPLEMENTED AND VERIFIED` | Displays Unity/Godot detected/configured binary paths, `PATCH /api/v1/engines/:engine` path override, native Tauri daemon start/stop/restart controls, and adapter installation guides. |
| **Projects View** | `src/components/views/ProjectsView.tsx` | `IMPLEMENTED AND VERIFIED` | Registers/removes Unity & Godot projects against daemon SQLite `/api/v1/projects` (or marks offline browser preview actions appropriately). |
| **Tools View** | `src/components/views/ToolsView.tsx` | `IMPLEMENTED AND VERIFIED` | Combines dynamic verified `liveTools` from connected adapters with all 19 `TOOL_CATEGORY_CONTRACTS` capability schemas cleanly labeled `Planned`. |
| **Tasks View** | `src/components/views/TasksView.tsx` | `IMPLEMENTED AND VERIFIED` | Lists persisted tasks, 16-phase steps, concurrency locks, `Execute Task`, `Pause`, `Resume`, `Cancel`, `Approve & Resume`, `Reject Gate`, and `Rollback` wired to daemon REST actions. |
| **Activity View** | `src/components/views/ActivityView.tsx` | `IMPLEMENTED AND VERIFIED` | Live session timeline fed by daemon WebSocket `/events` + `/api/v1/events/recent` with pause/resume/clear controls. |
| **Plugins View** | `src/components/views/PluginsView.tsx` | `IMPLEMENTED AND VERIFIED` | Merges live `/api/v1/adapters` state cleanly with Unity/Godot/`adapters/cpp` (`Planned`)/`test-adapter` manifest specs. |
| **Diagnostics View** | `src/components/views/DiagnosticsView.tsx` | `IMPLEMENTED AND VERIFIED` | Active loopback probe, Rust `collect_desktop_diagnostics`, daemon `/api/v1/diagnostics` display, and sanitized JSON export. |
| **Settings View** | `src/components/views/SettingsView.tsx` | `IMPLEMENTED AND VERIFIED` | Configures daemon URL, WebSocket URL, Bearer token (session-scoped, never persisted raw for AI keys), and Desktop `desktop-config.json` settings in Tauri. |
| **Replaceable `BridgeTransport`** | `src/services/bridgeTransport.ts` | `IMPLEMENTED AND VERIFIED` | Auto-selects `TauriIpcBridgeTransport` (when `window.__TAURI_INTERNALS__` present) or `HttpDaemonBridgeTransport`; tested in `tests/ts/bridgeTransport.test.ts` & `controlCenterService.test.ts`. |
| **Node Express Preview Backend** | `server.ts` | `IMPLEMENTED AND VERIFIED` | Serves Vite / static `dist/`, SSRF-protected `/api/bridge/probe`, `/api/protocol/schemas`, and `@google/genai` server proxy; tested in `tests/ts/server.test.ts`. Optional at desktop runtime (not required by Tauri/Python daemon). |

---

## 3. Communication Protocols, Gateways & API Surface

### 3.1 REST Endpoints (`core/nexus_core/rest_gateway.py`, `server.ts`, `integrations/rest-api/schema.ts`)

| Endpoint Group | Implementation | Status | Verification Evidence |
| :--- | :--- | :--- | :--- |
| Preview Health, Capabilities, Schemas, Probe (`/api/health`, `/api/runtime/capabilities`, `/api/protocol/schemas`, `/api/bridge/probe`) | `server.ts` | `IMPLEMENTED AND VERIFIED` | Verified in `tests/ts/server.test.ts` including SSRF non-loopback probe rejection. |
| Preview Gemini Proxy (`/api/ai/providers/verify`, `/api/ai/providers/generate`) | `server.ts` | `PARTIALLY IMPLEMENTED` | Server-side key gate (`503` when `GEMINI_API_KEY` missing) verified in `tests/ts/server.test.ts`; live external Gemini API call untested in sandbox. |
| Daemon Liveness & System (`/health`, `/api/v1/capabilities`, `/api/v1/diagnostics`, `/api/v1/daemon/shutdown`) | `core/nexus_core/rest_gateway.py` | `IMPLEMENTED AND VERIFIED` | Bearer-gated (except `/health`), verified live and across `test_core_backend.py` & `test_stage10_packaging.py`. |
| Engines & Projects (`/api/v1/engines`, `PATCH /api/v1/engines/:engine`, `/api/v1/projects*`) | `core/nexus_core/rest_gateway.py` | `IMPLEMENTED AND VERIFIED` | Verified in `test_core_backend.py` including invalid custom path checks (`400`) and SQLite persistence. |
| Tools, Tasks, Locks, Approvals, Journals & Rollback (`/api/v1/tools`, `/api/v1/tasks*`) | `core/nexus_core/rest_gateway.py` | `IMPLEMENTED AND VERIFIED` | Verified across `test_stage8_autonomous_engine.py` and `test_stage9_security_recovery_perf.py`. |
| Security & Events (`/api/v1/permissions/categories`, `/api/v1/events/recent`) | `core/nexus_core/rest_gateway.py` | `IMPLEMENTED AND VERIFIED` | Verified in `test_stage9_security_recovery_perf.py` & `test_core_backend.py`. |
| AI Providers (`/api/v1/providers`, `POST`, `DELETE`, `secret`, `verify`, `generate`) | `core/nexus_core/rest_gateway.py` | `IMPLEMENTED AND VERIFIED` | Verified in `test_ai_providers_and_mcp.py` & `test_core_backend.py` (custom delete, built-in delete block). |
| Adapters & Tool Execution (`/api/v1/adapters*`, `/api/v1/mcp/status`) | `core/nexus_core/rest_gateway.py` | `IMPLEMENTED AND VERIFIED` | Verified in `test_universal_adapter_framework.py` & `test_stage9_security_recovery_perf.py` (enforces `PermissionManager` argument + destructive approval checks). |
| Optional FastAPI / Uvicorn App (`create_fastapi_app`) | `core/nexus_core/rest_gateway.py`, `integrations/rest-api/router.py` | `IMPLEMENTED BUT NOT VERIFIED` | Code present; `fastapi` and `uvicorn` packages are not installed in the sandbox environment. |

### 3.2 WebSocket Event Service (`integrations/websocket/service.py`)

| Feature | Status | Notes & Evidence |
| :--- | :--- | :--- |
| RFC-6455 Handshake, Frame Encoding (`0x81` Text / `0x88` Close) & Heartbeat | `IMPLEMENTED AND VERIFIED` | Custom asyncio RFC-6455 server verified live in `test_core_backend.py` & `test_stage10_packaging.py`. |
| Loopback Auth (`Authorization: Bearer` header & `?token=` query param) | `IMPLEMENTED AND VERIFIED` | Unauthenticated upgrades rejected (`401`); both header and `?token=` verified constant-time. |
| Sub-second Shutdown Wakeup & EOF Reader Watch | `IMPLEMENTED AND VERIFIED` | Sends close frames, cancels reader/connection tasks with bounded `0.5s` waits; no shutdown hang. |
| Optional `websockets` Library Runtime | `IMPLEMENTED BUT NOT VERIFIED` | `websockets` package absent in sandbox; stdlib RFC-6455 service runs natively. |

### 3.3 Model Context Protocol (`core/nexus_core/mcp_server.py`, `integrations/mcp/`)

| Feature | Status | Notes & Evidence |
| :--- | :--- | :--- |
| Protocol Handshake (`2025-03-26`, `initialize`, `ping`, JSON-RPC `2.0`) | `IMPLEMENTED AND VERIFIED` | Verified over both `--mcp-stdio` and HTTP `/mcp`. |
| Transports: `stdio` & Bearer-Authenticated `Streamable HTTP` | `IMPLEMENTED AND VERIFIED` | Tested end-to-end in `test_ai_providers_and_mcp.py` & `test_stage9_security_recovery_perf.py`. |
| Legacy Separate `SSE` MCP Transport (`MCPTransportKind.SSE`) | `NOT IMPLEMENTED` | Listed in TS enum `MCPTransportKind.SSE` for external client compatibility metadata; server implements `stdio` and unified `Streamable HTTP` (`2025-03-26`). |
| 12 Built-In Bridge Tools (`nexus_*`) | `IMPLEMENTED AND VERIFIED` | `nexus_get_capabilities`, `nexus_get_diagnostics`, `nexus_list_engines`, `nexus_list_projects`, `nexus_register_project`, `nexus_list_tasks`, `nexus_create_task_draft`, `nexus_submit_autonomous_task`, `nexus_get_task_status`, `nexus_control_task`, `nexus_get_task_recovery`, `nexus_list_concurrency_locks`. |
| Dynamic Engine Tool Exposure + Argument & Destructive Validation | `IMPLEMENTED AND VERIFIED` | Publishes verified tools only when adapters connect; enforces `validate_tool_arguments(..., project_root=...)` and destructive approval (`_approved`). |
| 6 Read-Only Resources (`nexus://*`) | `IMPLEMENTED AND VERIFIED` | `nexus://engines`, `nexus://projects`, `nexus://capabilities`, `nexus://tasks`, `nexus://diagnostics`, `nexus://providers`. |
| 3 Game-Dev Prompts | `IMPLEMENTED AND VERIFIED` | `inspect_project_architecture`, `plan_engine_automation_task`, `diagnose_bridge_health`. |

---

## 4. AI Providers & Credential Security (`core/nexus_core/providers/`)

| Provider / Component | Implementation | Status | Notes & Evidence |
| :--- | :--- | :--- | :--- |
| **Google Gemini** | `core/nexus_core/providers/gemini.py` | `PARTIALLY IMPLEMENTED` | Model list, HTTP/SSE (`streamGenerateContent?alt=sse`), tool calling, usage metadata verified vs local mock HTTP server; live `generativelanguage.googleapis.com` API call unverified in sandbox. |
| **Anthropic Claude** | `core/nexus_core/providers/claude.py` | `PARTIALLY IMPLEMENTED` | `x-api-key` header, `anthropic-version`, SSE `content_block_delta` verified vs local mock HTTP server; live `api.anthropic.com` call unverified. |
| **OpenAI** | `core/nexus_core/providers/openai_provider.py` | `PARTIALLY IMPLEMENTED` | Chat Completions + SSE `choices[].delta` + tool calls verified vs local mock HTTP server; live `api.openai.com` call unverified. |
| **OpenAI-Compatible (Ollama / LM Studio / vLLM)** | `core/nexus_core/providers/openai_compatible.py` | `PARTIALLY IMPLEMENTED` | Local `127.0.0.1` endpoint probing, optional Bearer key, streaming verified vs local mock server; live Ollama/LM Studio server absent in container. |
| **Custom Provider** | `core/nexus_core/providers/custom.py` | `IMPLEMENTED AND VERIFIED` | Extensible provider adapter with custom endpoints/headers/models verified in `test_ai_providers_and_mcp.py`. |
| **Incremental Async SSE Streaming (`http_sse_line_stream`)** | `core/nexus_core/providers/base.py` | `IMPLEMENTED AND VERIFIED` | Line-by-line async `asyncio.Queue` socket reader (`generate_stream`), replacing buffered full-body reads. |
| **Credential Storage (`CredentialStore`)** | `core/nexus_core/providers/credentials.py` | `PARTIALLY IMPLEMENTED` | `env://`, `vault://` (`0600` local store) verified cleanly; Windows `wincred://` (`advapi32` `CredReadW`/`CredWriteW`/`CredDeleteW`) is `IMPLEMENTED BUT NOT VERIFIED` (Linux host). Raw plaintext API keys rejected cleanly. |

---

## 5. Universal Engine Adapter Framework & Native Engine Plugins

### 5.1 Protocol & Lifecycle Contracts (`core/nexus_core/adapters/`, `sdk/ts/adapter.ts`)

| Contract / Feature | Implementation | Status | Notes & Evidence |
| :--- | :--- | :--- | :--- |
| **13-Method `EngineAdapterContract`** | `sdk/ts/adapter.ts`, `engine_manager.py`, `core/nexus_core/adapters/` | `IMPLEMENTED AND VERIFIED` | `detectEngine`, `identifyVersion`, `discoverProjects` (split cleanly between `EngineManager` binary/hub scanning + `ProtocolEngineAdapter`) and runtime RPC/health methods implemented and tested. |
| **11 NDJSON JSON-RPC 2.0 Wire Methods** | `core/nexus_core/adapters/{interface.py,protocol.py}` | `IMPLEMENTED AND VERIFIED` | `getEngineInfo`, `discoverProjects`, `connect`, `disconnect`, `getCapabilities`, `listTools`, `executeTool`, `getProjectState`, `subscribeEvents`, `captureScreenshot`, `healthCheck`. |
| **Transports (`stdio` & `tcp-loopback`)** | `core/nexus_core/adapters/protocol.py` | `IMPLEMENTED AND VERIFIED` | Both `StdioAdapterTransport` and `TcpLoopbackAdapterTransport` verified against out-of-process harnesses. |
| **Manifest Validation, SemVer & Checksum** | `core/nexus_core/adapters/manifest.py` | `IMPLEMENTED AND VERIFIED` | Validates `manifestVersion`, SemVer protocol compatibility bounds (`minDaemonProtocolVersion`/`maxDaemonProtocolVersion`), entrypoint path traversal, and optional `checksumSha256`. |
| **Lifecycle FSM & Exponential Backoff Reconnect** | `core/nexus_core/adapters/manager.py` | `IMPLEMENTED AND VERIFIED` | Handles disconnect EOF, auto-reconnect backoff (`ReconnectionPolicy`), test-adapter isolation, and SQLite persistence across restarts. |
| **Synthetic Test Adapter** | `adapters/test-adapter/test_adapter_server.py` | `IMPLEMENTED AND VERIFIED` | Out-of-process JSON-RPC 2.0 harness (`stdio` + `tcp-loopback`) explicitly flagged `isTestAdapter: true` and excluded from real counts. |

### 5.2 Native Game Engine Plugins (`adapters/unity/`, `adapters/godot/`, `adapters/cpp/`)

| Engine Adapter | Scope / Mechanism | Status | Notes & Evidence |
| :--- | :--- | :--- | :--- |
| **Unity C# UPM Plugin (`adapters/unity/`)** | `com.nexus.bridge`, 17 `unity.*` tools, TCP `127.0.0.1:47201`, `NexusMainThreadDispatcher` (`ConcurrentQueue`), `Undo.*`, `NexusUnityStateTracker`, EditorWindow UI | `IMPLEMENTED BUT NOT VERIFIED` | Verified in C# source and Python TCP loopback simulation (`test_unity_adapter_integration.py`). **Not compiled or executed inside live `Unity.exe` (`2022.3 LTS+`/`Unity 6`)** in Linux container. No standalone blank-scene generator tool (`unity.save_scene` saves active/new path). |
| **Godot 4.2+ GDScript Plugin (`adapters/godot/`)** | `EditorPlugin` (`nexus_bridge`), 18 `godot.*` tools, TCP `127.0.0.1:47202`, `EditorUndoRedoManager`, `EditorFileSystem`, `EditorDebuggerPlugin`, `Viewport` PNG capture | `IMPLEMENTED BUT NOT VERIFIED` | Verified in GDScript source, addon sync (`test_project` parity), and Python TCP loopback simulation (`test_godot_adapter_integration.py`). **Not executed inside live `godot4` editor binary**. `modify_node` UndoRedo leak fixed prior to audit. No blank `.tscn` creation without an edited scene. |
| **Unreal Engine C++ Adapter (`adapters/cpp/`)** | `nexus-adapter.manifest.json`, `README.md` | `NOT IMPLEMENTED` | Manifest/architecture placeholder only (`NexusCppBridgeModule.cpp` does not exist; marked `Planned` in UI). |

---

## 6. Tool Categories (19 Architectural Namespaces vs Native Tool Coverage)

Mapped from `tools/categories.ts` (`ToolCategory`), `core/nexus_core/tool_registry.py` (`PLANNED_TOOL_CATEGORIES`), `adapters/unity/Editor/NexusUnityToolRegistry.cs`, and `adapters/godot/addons/nexus_bridge/nexus_tool_registry.gd`:

| # | Tool Category (`ToolCategory`) | Unity Registered Tools | Godot Registered Tools | Status | Gap / Notes |
| :-: | :--- | :--- | :--- | :--- | :--- |
| 1 | **Project management** | `unity.get_editor_state` | — (via `nexus://projects`, `getEngineInfo`) | `IMPLEMENTED BUT NOT VERIFIED` | Daemon project CRUD + Unity editor state implemented; live Unity run pending. |
| 2 | **Scene management** | `unity.get_scene_hierarchy`, `unity.save_scene` | `godot.get_scene_state`, `godot.get_node_hierarchy`, `godot.save_scene` | `PARTIALLY IMPLEMENTED` | Inspect hierarchy & save active/target scene implemented (`IMPLEMENTED BUT NOT VERIFIED` in live engine); lacks standalone blank `create_scene` / `open_scene` / `delete_scene`. |
| 3 | **Object management** | `unity.inspect_object`, `unity.create_object`, `unity.delete_object`, `unity.transform_object` | `godot.create_node`, `godot.modify_node`, `godot.delete_node`, `godot.set_transform` | `IMPLEMENTED BUT NOT VERIFIED` | Full CRUD + transforms with `Undo` / `EditorUndoRedoManager` implemented; live editor verification pending. |
| 4 | **Component management** | `unity.manage_component` | `godot.manage_signals` | `IMPLEMENTED BUT NOT VERIFIED` | Unity add/remove/update serialized components; Godot persistent signal management. Live engine verification pending. |
| 5 | **Script management** | `unity.create_script`, `unity.modify_script` | `godot.create_script`, `godot.modify_script` | `IMPLEMENTED BUT NOT VERIFIED` | Sandboxed C# (`Assets/`) and GDScript (`res://`) creation/patching + reload verification implemented; live editor pending. |
| 6 | **Asset management** | `unity.inspect_assets`, `unity.import_asset` | `godot.inspect_assets`, `godot.manage_resource` | `IMPLEMENTED BUT NOT VERIFIED` | AssetDatabase search/reimport & Godot `.tres`/`.res` + `EditorFileSystem` tools implemented; live editor pending. |
| 7 | **Material management** | — | — | `NOT IMPLEMENTED` | Category contract schema only (`tools/categories.ts`); no dedicated material tools registered yet (partial generic resource inspection via `manage_resource`). |
| 8 | **Shader management** | — | — | `NOT IMPLEMENTED` | Category contract schema only (`tools/categories.ts`); no shader authoring/compilation tools registered yet. |
| 9 | **Lighting** | — | — | `NOT IMPLEMENTED` | Category contract schema only (`tools/categories.ts`); no dedicated lightmap/environment baking tools registered yet. |
| 10 | **Physics** | — | — | `NOT IMPLEMENTED` | Category contract schema only (`tools/categories.ts`); no dedicated physics layer/collider/raycast tools registered yet. |
| 11 | **Animation** | — | — | `NOT IMPLEMENTED` | Category contract schema only (`tools/categories.ts`); no Animator/`AnimationPlayer` tools registered yet. |
| 12 | **Audio** | — | — | `NOT IMPLEMENTED` | Category contract schema only (`tools/categories.ts`); no mixer/`AudioSource`/`AudioStreamPlayer` tools registered yet. |
| 13 | **UI** | — | — | `NOT IMPLEMENTED` | Category contract schema only (`tools/categories.ts`); no dedicated Canvas/`Control` layout preset tools registered yet. |
| 14 | **Navigation** | — | — | `NOT IMPLEMENTED` | Category contract schema only (`tools/categories.ts`); no NavMesh baking/agent tools registered yet. |
| 15 | **Rendering** | `unity.capture_screenshot` | `godot.capture_screenshot` (if viewport supported) | `PARTIALLY IMPLEMENTED` | Viewport screenshot capture to PNG implemented (`IMPLEMENTED BUT NOT VERIFIED` in live editors); render-pipeline asset/pass configuration tools not implemented. |
| 16 | **Debugging** | `unity.get_compilation_status`, `unity.get_console_logs` | `godot.get_errors`, `godot.inspect_debugger` | `IMPLEMENTED BUT NOT VERIFIED` | Compiler diagnostics, log buffers, and Godot `EditorDebuggerPlugin` implemented; live editor pending. |
| 17 | **Testing** | `unity.control_play_mode` | `godot.launch_runtime` | `PARTIALLY IMPLEMENTED` | Play Mode / Runtime launch & stop implemented (`IMPLEMENTED BUT NOT VERIFIED` in live engine), plus standalone EditMode/GDScript test suites (`NexusUnityIntegrationTests.cs`, `nexus_godot_verification.gd`); MCP-triggered Unity Test Runner / GUT execution tools not yet exposed. |
| 18 | **Profiling** | — | `godot.get_runtime_status` | `PARTIALLY IMPLEMENTED` | Godot runtime FPS/frame/memory snapshot tool implemented (`IMPLEMENTED BUT NOT VERIFIED` in live editor); deep Unity Profiler API frame-capture tool not implemented. |
| 19 | **Build and export** | `unity.get_build_status` | `godot.get_export_status` | `PARTIALLY IMPLEMENTED` | Build/export target/preset & last-report inspection implemented (`IMPLEMENTED BUT NOT VERIFIED` in live engine); triggering full player builds (`BuildPipeline.BuildPlayer` / `EditorExportPlatform`) via MCP is not yet exposed. |

---

## 7. Autonomous Development Engine (16-Phase Workflow)

Mapped from `core/nexus_core/{orchestrator.py,task_manager.py,concurrency.py}`:

| Feature / Phase | Status | Notes & Evidence |
| :--- | :--- | :--- |
| **16-Phase DAG State Machine (`AUTONOMOUS_PHASES`)** | `IMPLEMENTED AND VERIFIED` | Phases 1–16 (`Receive Task` through `Generate Report`) with dependency checking (`DependencyResolver`), persisted in SQLite and tested in `test_stage8_autonomous_engine.py`. |
| **Prioritized Task Queue & Concurrency Locks** | `IMPLEMENTED AND VERIFIED` | `low`/`normal`/`high`/`critical` priority weights (`MultiAgentCoordinator`) enforcing project-level & resource-level mutual exclusion cleanly (`ConflictError` `409`). |
| **Approval Pause/Resume Gates** | `IMPLEMENTED AND VERIFIED` | Destructive plans pause at Phase 8 (`Validate Permissions`) cleanly and resume or abort via `POST /api/v1/tasks/:id/approve` or MCP `nexus_control_task`. |
| **Bounded Non-Duplicate Repair Engine** | `IMPLEMENTED AND VERIFIED` | `RetryPolicy` (`maxRepairAttempts`, `maxStepRetries`, `preventDuplicateFailures`) blocks identical failing retries (`NEXUS_VALIDATION_ERROR`) in Phase 12/13. |
| **Result, Error & Screenshot Verification (Phases 11, 14, 15)** | `IMPLEMENTED AND VERIFIED` | Phase 14 inspects actual test/adapter outputs (`passed`, `verified`, `errorCount`, `failed`, `adapterErrors`, `errors`) instead of hardcoded pass flags; Phase 15 verifies every planned operation completed (`test_stage8_autonomous_engine.py`). |
| **Visual Screenshot Capture Hook** | `IMPLEMENTED AND VERIFIED` | Captures PNG base64/artifact paths when `captureVisualVerification: true` via adapter `captureScreenshot`. |

---

## 8. Stage 9: Permissions, Security & Recovery

### 8.1 Permissions & Security Controls (`core/nexus_core/security.py`, `logging_config.py`, `adapters/manifest.py`)

| Requirement | Status | Implementation & Verification Evidence |
| :--- | :--- | :--- |
| **7 Capability-Based Permission Categories** | `IMPLEMENTED AND VERIFIED` | `Read-only inspection`, `Non-destructive modification`, `Project modification`, `Script execution`, `Runtime control`, `Build and export`, `External process access` exposed at `/api/v1/permissions/categories`. |
| **Explicit Destructive Operation Restrictions** | `IMPLEMENTED AND VERIFIED` | `DESTRUCTIVE_SCOPES` + `requires_approval_for_tool()` / `validate_destructive_operation()` block `delete_*`, `remove_component`, `assets:modify`, `build:export`, and `process:restricted` unless explicitly approved; enforced consistently across REST, MCP, and Orchestrator (`test_stage9_security_recovery_perf.py`). |
| **All Tool Input Validation** | `IMPLEMENTED AND VERIFIED` | `validate_tool_arguments()` validates tool ID regex, object key counts (`<=64`), nesting depth (`<=8`), array length (`<=500`), NUL bytes, and process/shell metacharacters across all execution entry points. |
| **Project Sandbox & Path Traversal Prevention** | `IMPLEMENTED AND VERIFIED` | `validate_project_registration_path()`, `assert_path_within_project()`, and `resolve_engine_resource_path()` block `..`, escaping absolute paths, and external Windows drive/UNC paths across C#/GDScript/Python. |
| **Credential Protection & Secret Redaction** | `IMPLEMENTED AND VERIFIED` | Frontend stores zero raw AI API keys; raw keys rejected by `CredentialStore`; `redact_sensitive_fields()` and `SecretRedactingFilter` scrub Bearer tokens, `nxs_` tokens, `x-api-key`, `x-goog-api-key`, passwords, and secrets from logs/SQLite audit records. |
| **Local API Authentication & Network Restriction** | `IMPLEMENTED AND VERIFIED` | `assert_loopback_bind()` restricts daemon to `127.0.0.1` / `localhost` / `::1`; constant-time `hmac.compare_digest` on `0600` (ACL-restricted on Windows) `daemon.token` protects REST, WS, and MCP HTTP. |
| **Plugin Validation** | `IMPLEMENTED AND VERIFIED` | `AdapterManifest.from_dict()` + `validate_adapter_compatibility()` verify manifest schema, protocol SemVer range, entrypoint relative path (no traversal), and SHA-256 checksums. |
| **Audit Logs** | `IMPLEMENTED AND VERIFIED` | Persistent SQLite `audit_logs` table records actor, action, status, timestamp, and redacted details (`test_stage9_security_recovery_perf.py`). |
| **Unauthorized Execution Prevention** | `IMPLEMENTED AND VERIFIED` | `ALLOWED_PROCESS_NAMES` allowlist + `_SHELL_META_RE` block arbitrary shell commands; `PROCESS_SPAWN_RESTRICTED` blocked by default. |

### 8.2 Recovery Controls (`core/nexus_core/{checkpoints.py,task_manager.py,storage.py,adapters/manager.py}`)

| Requirement | Status | Implementation & Verification Evidence |
| :--- | :--- | :--- |
| **Task Checkpoints** | `IMPLEMENTED AND VERIFIED` | Pre-mutation snapshots stored in `checkpoints` SQLite table & disk snapshot directories (`chk-*`). |
| **File Change Manifests** | `IMPLEMENTED AND VERIFIED` | `file_change_manifest.json` records `relativePath`, `existed`, `beforeHash` (SHA-256), `afterHash` (SHA-256), `changed`, `sizeBytes`, and backup file paths. |
| **Operation Journals** | `IMPLEMENTED AND VERIFIED` | Persistent SQLite `operation_journal` tracks `stepId`, `toolId`, `status`, timestamps, and sanitized payloads (`GET /api/v1/tasks/:id/journal`). |
| **Failed-Operation Records** | `IMPLEMENTED AND VERIFIED` | Persistent SQLite `failed_operations` records structured error codes, messages, recovery hints, and operation refs. |
| **Selective Rollback** | `IMPLEMENTED AND VERIFIED` | `CheckpointManager.rollback_checkpoint()` & `POST /api/v1/tasks/:id/rollback` restore specific requested files or delete newly created untracked files cleanly. |
| **Adapter Reconnection** | `IMPLEMENTED AND VERIFIED` | Exponential backoff reconnect loop on unexpected TCP/stdio EOF + Unity `AssemblyReloadEvents` / Godot `_exit_tree()` recovery. |
| **Daemon Restart & Interrupted Task Recovery** | `IMPLEMENTED AND VERIFIED` | `TaskManager.recover_interrupted_tasks()` runs on daemon startup, transitions orphaned `Running` tasks to recoverable `Failed`/`interrupted` records, and logs recovery diagnostics (`test_stage9_security_recovery_perf.py`). |

---

## 9. Testing Infrastructure & Native Engine Test Projects

| Test Layer | Location / Command | Status | Scope & Verified Result |
| :--- | :--- | :--- | :--- |
| **Python Automated Suite (Unit, Integration, Adapter, Protocol, Security, Autonomous Workflow, Recovery, Perf, Packaging)** | `tests/python/test_*.py` (`python3 -m unittest discover -s tests/python -p "test_*.py" -v`) | `IMPLEMENTED AND VERIFIED` | **9 test files, 40 / 40 tests passing** (`core_backend`, `core_contracts`, `ai_providers_and_mcp`, `universal_adapter_framework`, `unity_adapter_integration`, `godot_adapter_integration`, `stage8_autonomous_engine`, `stage9_security_recovery_perf`, `stage10_packaging`). Runs against loopback sockets & mock upstreams. |
| **TypeScript / React / Express Tests** | `tests/ts/*.test.ts` (`npm test`) | `IMPLEMENTED AND VERIFIED` | **4 test files, 19 / 19 tests passing** (`bridgeTransport`, `contracts`, `controlCenterService`, `server`). |
| **Static Analysis & Repo Health Checks** | `npm run lint`, `npm run lint:code`, `npm run format:check`, `npm run check:structure`, `npm run build` | `IMPLEMENTED AND VERIFIED` | `tsc --noEmit` (`0` errors), `oxlint` (`0` warnings / `0` errors), `prettier` (all pass), 14 architectural directories verified, offline `dist/` bundle builds cleanly. |
| **Unity Test Project & NUnit Suite** | `adapters/unity/test_project/`, `adapters/unity/Tests/Editor/NexusUnityIntegrationTests.cs` | `IMPLEMENTED BUT NOT VERIFIED` | Pre-configured Unity project + NUnit EditMode suite asserting actual scene/object/script/Undo/asset states. **Not run inside `Unity.exe`** in Linux container (verified via Python TCP loopback protocol harness). |
| **Godot Test Project & Verification Suite** | `adapters/godot/test_project/`, `adapters/godot/test_project/tests/nexus_godot_verification.gd` | `IMPLEMENTED BUT NOT VERIFIED` | Pre-configured Godot 4.x project (`project.godot`, `scenes/main.tscn`, `export_presets.cfg`, synced addon) + GDScript verification assertions. **Not run inside `godot4` binary** in Linux container (verified via Python TCP loopback protocol harness). |

---

## 10. Stage 10: Windows Desktop Packaging & Native Deployment

Mapped from `apps/desktop/src-tauri/`, `scripts/*.ps1`, `scripts/stage-adapter-resources.mjs`, and `docs/WINDOWS_PACKAGING_AND_INSTALL.md`:

| Requirement | Implementation Location | Status | Notes & Evidence |
| :--- | :--- | :--- | :--- |
| **1. Tauri 2 Application Shell** | `apps/desktop/src-tauri/{Cargo.toml,tauri.conf.json,build.rs,capabilities/default.json}` | `IMPLEMENTED BUT NOT VERIFIED` | Configured for Tauri 2, strict CSP (`http://127.0.0.1:* ws://127.0.0.1:*`), WebView2 silent bootstrapper, bundled `resources/**/*`; `cargo` toolchain unavailable in Linux sandbox. |
| **2. Native Application Startup** | `apps/desktop/src-tauri/src/{main.rs,lib.rs}` | `IMPLEMENTED BUT NOT VERIFIED` | Window setup, resource dir resolution, background startup thread for daemon spawn/adoption; pending Windows build verification. |
| **3. Background Daemon Startup (`CREATE_NO_WINDOW`)** | `apps/desktop/src-tauri/src/daemon_manager.rs` | `IMPLEMENTED BUT NOT VERIFIED` | Probes existing daemon/service first; spawns hidden Windows process (`0x08000000`) when needed; pending Windows execution. |
| **4. Python Sidecar & Standalone Service** | `scripts/build-python-sidecar.ps1`, `scripts/install-windows-service.ps1`, `core/nexus_core/__main__.py` | `IMPLEMENTED BUT NOT VERIFIED` | PyInstaller one-file sidecar build script + Windows Scheduled Task/Service scripts implemented; daemon runs independently of UI (`IMPLEMENTED AND VERIFIED` on Linux CLI; PyInstaller `.exe` pending Windows build). |
| **5. Local IPC Communication** | `apps/desktop/src-tauri/src/lib.rs`, `src/services/bridgeTransport.ts` | `IMPLEMENTED AND VERIFIED` | 12 Rust `#[tauri::command]` bindings matched 1:1 with `TauriIpcBridgeTransport` contract (`tests/ts/contracts.test.ts` & `bridgeTransport.test.ts`); native Tauri runtime execution pending Windows build. |
| **6. Secure Configuration Storage** | `apps/desktop/src-tauri/src/config_store.rs` | `IMPLEMENTED BUT NOT VERIFIED` | `%LOCALAPPDATA%\NEXUS\desktop-config.json` + `icacls` current-user-only ACL for `daemon.token`; pending Windows execution. |
| **7. Application Shutdown Handling** | `apps/desktop/src-tauri/src/lib.rs`, `daemon_manager.rs`, `core/nexus_core/daemon.py` | `IMPLEMENTED AND VERIFIED` | Daemon `POST /api/v1/daemon/shutdown` + WebSocket close teardown verified (`<250ms` in daemon tests); Rust `RunEvent::Exit` calls `shutdown_on_app_exit` (`IMPLEMENTED BUT NOT VERIFIED` natively). |
| **8. Daemon Lifecycle Management** | `apps/desktop/src-tauri/src/daemon_manager.rs`, `EnginesView.tsx` | `IMPLEMENTED BUT NOT VERIFIED` | `start_background_daemon`, `stop_background_daemon`, `restart_background_daemon`, `get_daemon_lifecycle_status` (`service` vs `sidecar` adoption); pending Windows test. |
| **9. Logging** | `core/nexus_core/logging_config.py`, `apps/desktop/src-tauri/src/config_store.rs` | `IMPLEMENTED AND VERIFIED` | Secret-redacting rotating JSON `nexus-daemon.log` verified in `test_stage10_packaging.py`; Rust `desktop-shell.log` rotation implemented (`IMPLEMENTED BUT NOT VERIFIED` natively). |
| **10. Diagnostics** | `apps/desktop/src-tauri/src/daemon_manager.rs`, `core/nexus_core/diagnostics.py`, `DiagnosticsView.tsx` | `IMPLEMENTED AND VERIFIED` | Python diagnostics + adapter parity + SQLite `integrity_check` verified; Rust host diagnostics & resource bundle checks implemented cleanly. |
| **11. Windows Installer (NSIS & MSI)** | `apps/desktop/src-tauri/tauri.conf.json`, `scripts/build-desktop.ps1` | `IMPLEMENTED BUT NOT VERIFIED` | Staging (`npm run stage:adapters`) & `-ServiceMode` `externalBin` config override verified; `cargo tauri build` (`NSIS`/`MSI`) **NOT BUILT** in Linux container. |
| **12. Application Version Management** | `apps/desktop/src-tauri/src/version.rs`, `core/nexus_core/config.py`, `package.json`, `Cargo.toml` | `IMPLEMENTED AND VERIFIED` | All manifests and `APP_VERSION` synchronized at `0.10.0` (verified in `test_stage10_packaging.py`). |
| **13. Uninstallation** | `scripts/uninstall-nexus.ps1`, NSIS/WiX uninstallers | `IMPLEMENTED BUT NOT VERIFIED` | Cleanly shuts down daemon, removes Scheduled Task/service, removes install artifacts, supports `-PurgeUserData`; unexecuted without Windows host. |
| **14. Adapter Installation Instructions** | `apps/desktop/src-tauri/src/daemon_manager.rs`, `EnginesView.tsx`, `docs/UNITY_ADAPTER_GUIDE.md`, `docs/GODOT_ADAPTER_GUIDE.md` | `IMPLEMENTED AND VERIFIED` | Resourced staging (`npm run stage:adapters`) verified into `apps/desktop/src-tauri/resources/adapters/` and exposed dynamically in Rust IPC + `EnginesView.tsx`. |
| **15. Clean Windows Environment Verification** | `scripts/verify-windows-install.ps1` | `IMPLEMENTED BUT NOT VERIFIED` | Automated verification script ready (`-RunUninstallCheck`), **NOT EXECUTED** in absence of a clean Windows 10/11 VM. |

---

## 11. Environment Incompatibilities & Hard Architecture Constraints

| Capability / Scenario | Location / Constraint | Status | Explanation |
| :--- | :--- | :--- | :--- |
| **Google AI Studio Independence & Zero Cloud Lock-In** | `core/nexus_core/`, `src/`, `apps/desktop/` | `IMPLEMENTED AND VERIFIED` | Verified in `test_stage10_packaging.py` and offline `npm run build` (`dist/` runs headless without `server.ts`, AI Studio APIs, or cloud backends). |
| **In-Browser Web Preview Execution of Native Engines / Tauri** | Browser Sandbox / Iframe (`ARCHITECTURE.md` §3, `ENVIRONMENT_INCOMPATIBILITIES`) | `UNSUPPORTED` | Sandboxed web iframes cannot spawn local Windows executables, access `window.__TAURI_INTERNALS__`, use Windows DPAPI, or bypass HTTPS->`ws://127.0.0.1` mixed-content restrictions; UI degrades cleanly to `Unavailable` / `Disconnected`. |
| **Linux Container Execution of Windows Toolchains & Engines** | Cloud Linux Host (`Python 3.11.2`, no `cargo`/`Unity.exe`/`godot4`) | `UNSUPPORTED` | `Unity.exe`, `godot4`, `cargo tauri build`, `pyinstaller`, `makensis`, Windows `advapi32` Credential Manager, and clean Windows VM install checks cannot execute inside this container and require a local Windows 10/11 x64 environment. |
| **Non-Loopback / LAN Daemon Exposure by Default** | `core/nexus_core/security.py` | `UNSUPPORTED` | `PermissionManager.assert_loopback_bind()` blocks public interface binding by design to keep local game projects isolated to `127.0.0.1`. |
