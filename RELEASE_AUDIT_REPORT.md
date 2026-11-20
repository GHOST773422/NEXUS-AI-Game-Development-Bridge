# NEXUS — Final Integration and Release Audit Report

**Audit Date**: 2026-11-19  
**Audited Version**: `0.10.0` (synchronized across `package.json`, `core/pyproject.toml`, `core/nexus_core/config.py`, `apps/desktop/src-tauri/Cargo.toml`, `apps/desktop/src-tauri/tauri.conf.json`)  
**Audit Role**: Independent Senior QA Engineer & Software Architect  
**Audit Method**: Full source code inspection across all subsystems + live execution of test suites, TypeScript/static linters, offline Vite production build, and a live out-of-process `python3 -m core.nexus_core --serve` + MCP (`stdio` + Streamable HTTP) + RFC-6455 WebSocket + TCP loopback Unity/Godot test-project E2E benchmark harness.

---

## Classification Key

Every audited subsystem uses strictly one of the following five classifications:

- `IMPLEMENTED AND VERIFIED` — Implemented in source AND verified by live execution in this audit.
- `IMPLEMENTED BUT NOT VERIFIED` — Implemented in source, structurally checked, NOT executed against native target runtimes (e.g., Windows `Unity.exe`, `godot4`, `cargo tauri build`, PyInstaller, clean Windows 10/11 VM).
- `PARTIALLY IMPLEMENTED` — Implemented in part, with concrete functional, wiring, or security defects identified in actual code/execution.
- `NOT IMPLEMENTED` — Absent from the codebase.
- `UNSUPPORTED` — Outside supported host/environment target.

---

## 1. Final Architecture Report

### 1.1 Implemented Runtime Topology

NEXUS is structured as a local-first, loopback-bound bridge split across four layers:

1. **Desktop Shell & Preview Layer (`apps/desktop/src-tauri/`, `src/`, `server.ts`)**:
   - **Tauri 2 Rust Shell (`apps/desktop/src-tauri/src/`)**: Implements `DaemonSupervisor` (`daemon_manager.rs`), `%LOCALAPPDATA%\NEXUS\desktop-config.json` management (`config_store.rs`), OS version metadata (`version.rs`), and 9 Tauri IPC commands (`lib.rs`) using a zero-dependency loopback HTTP/1.1 TCP client to talk to `127.0.0.1:47100`.
   - **React 19 Control Center (`src/`)**: Builds as a standalone offline bundle (`dist/`) without Google AI Studio dependencies. `TauriIpcBridgeTransport` and `HttpDaemonBridgeTransport` (`src/services/bridgeTransport.ts`) expose authenticated REST and Tauri IPC calls, actively consumed by `DiagnosticsView.tsx` and `EnginesView.tsx`. **Architectural disconnect found**: `src/App.tsx`, `ToolsView.tsx`, and `PluginsView.tsx` still operate on in-memory React state and static catalog constants rather than fetching `/api/v1/projects`, `/api/v1/tasks`, `/api/v1/tools`, `/api/v1/adapters`, or `/api/v1/providers` or subscribing to WebSocket events.
   - **Express Preview Server (`server.ts`)**: Node/Express dev & preview server exposing `/api/health`, `/api/runtime/capabilities`, `/api/protocol/schemas`, SSRF-guarded `/api/bridge/probe`, and optional server-side Gemini `@google/genai` routes when `GEMINI_API_KEY` is supplied. Not required for desktop/daemon operation.

2. **Python Core Daemon (`core/nexus_core/`)**:
   - Runs headlessly (`--serve`, `--mcp-stdio`, `--health-once`, `--version`) independently of the desktop GUI, bound by default to `127.0.0.1` across three local TCP ports:
     - **REST Gateway**: `127.0.0.1:47100` (`core/nexus_core/rest_gateway.py` — zero-dependency stdlib HTTP/1.1 server)
     - **WebSocket Event Service**: `127.0.0.1:47101` (`integrations/websocket/service.py` — custom RFC-6455 server)
     - **MCP Streamable HTTP Server**: `127.0.0.1:47102` (`core/nexus_core/mcp_server.py` — JSON-RPC `2.0`, protocol `"2025-03-26"`, also exposed over `stdio`)
   - Persists state in WAL-mode SQLite (`nexus.db`) across 9 tables (`ai_providers`, `audit_logs`, `checkpoints`, `daemon_state`, `failed_operations`, `installed_adapters`, `operation_journal`, `projects`, `tasks`) with rotating secret-redacting JSON logs (`nexus-daemon.log`) and a `0600` bearer token file (`daemon.token`).

3. **Universal Adapter Boundary & Native Engine Plugins (`core/nexus_core/adapters/`, `adapters/`)**:
   - Communicates via NDJSON JSON-RPC `2.0` (`11` standard lifecycle/tool/event methods) over `tcp-loopback` or `stdio` without embedding Python inside engine processes.
   - **Unity C# UPM Extension (`adapters/unity/`)**: TCP loopback listener marshaling 17 `unity.*` tools onto Unity's main thread via `ConcurrentQueue` + `EditorApplication.update`, blocking unsafe mutations during `EditorApplication.isCompiling` / `BuildPipeline.isBuildingPlayer`, registering `Undo.*` records, and attaching Unity console/compilation/build hooks (`NexusUnityStateTracker.cs`).
   - **Godot 4.2+ GDScript Plugin (`adapters/godot/addons/nexus_bridge/`)**: `@tool` `EditorPlugin` exposing 18 `godot.*` tools (`Engine.get_version_info()` compatibility checks, `EditorUndoRedoManager`, `EditorFileSystem`, `EditorDebuggerPlugin`, `EditorInterface` viewport capture, `EditorExportPlugin`).
   - **Future C++ / Unreal Stub (`adapters/cpp/`)**: Manifest/contract placeholder only (`NOT IMPLEMENTED`).

4. **Autonomous Development Engine, Security & Recovery (`core/nexus_core/orchestrator.py`, `security.py`, `checkpoints.py`, `task_manager.py`)**:
   - 16-phase DAG workflow with step dependencies, retry policies, execution limits, non-duplicate repair guards (`NEXUS_VALIDATION_ERROR` on identical failed retries), multi-agent project/resource locks (`concurrency.py`), SHA-256 pre/post checkpoints, selective file rollback, `operation_journal` / `failed_operations`, and startup interrupted-task recovery.

---

## 2. Feature Implementation Matrix

| # | Audit Area | Classification | Empirical Evidence & Concrete Gaps |
| :--- | :--- | :--- | :--- |
| 1 | **Desktop application (`src/`, `dist/`)** | `PARTIALLY IMPLEMENTED` | Offline `dist/` Vite build succeeded cleanly (`npm run build`, zero AI Studio lock-in). `DiagnosticsView` & `EnginesView` talk to daemon IPC cleanly. **Gap**: `src/App.tsx` manages Projects, Tasks, Tools, Plugins, and AI Providers in client-only React state; `ToolsView.tsx` hardcodes `0 Live Tools`; `PluginsView.tsx` hardcodes `0 Real Connected`; `handleTaskControl` still references stale Stage 5 copy. |
| 2 | **Tauri integration (`apps/desktop/src-tauri/`)** | `PARTIALLY IMPLEMENTED` | `lib.rs`, `daemon_manager.rs`, `config_store.rs`, `version.rs`, `capabilities/default.json` cleanly structure IPC, `CREATE_NO_WINDOW`, and `%LOCALAPPDATA%\NEXUS` storage. **Gaps**: (a) `daemon_manager.rs` line 682 allows `"::1"` then formats `"::1:47100"` without `[::1]`, breaking IPv6 `SocketAddr::parse`; (b) `tauri.conf.json` hardcodes `"externalBin": ["binaries/nexus-daemon"]`, breaking `-ServiceMode` / `-SkipSidecar` builds; (c) not compiled with `cargo` (absent in sandbox). |
| 3 | **Background daemon (`core/nexus_core/daemon.py`, `__main__.py`, `config.py`)** | `PARTIALLY IMPLEMENTED` | Live `--serve`, `--health-once`, `--version`, `--mcp-stdio`, WAL SQLite, `0600` bearer token, and secret-redacting rotating JSON logs verified. **Gaps**: (a) graceful `POST /api/v1/daemon/shutdown` stalled **`10,052 ms`** (~10s, up to 15s heartbeat window) after an active WS connection because `WebSocketEventService._handle_connection` blocks on `queue.get(timeout=15)` and `stop()` waits for `_server.wait_closed()`; (b) CLI omits `--ws-port` and `--mcp-port` flags (env vars `NEXUS_WS_PORT` / `NEXUS_MCP_PORT` required). |
| 4 | **Python backend (`core/nexus_core/`)** | `PARTIALLY IMPLEMENTED` | 37/37 unittest tests & live daemon subprocess passed using stdlib fallback runtime on Python `3.11.2`. **Gaps**: Target `Python 3.12+` and optional `pyproject.toml` dependencies (`fastapi`, `uvicorn`, `websockets`, `mcp`, `aiosqlite`, `httpx`) are absent/untested in container; `providers/base.py` `http_sse_lines()` buffers the full HTTP response body before yielding chunks. |
| 5 | **MCP connectivity (`core/nexus_core/mcp_server.py`)** | `IMPLEMENTED AND VERIFIED` | Verified live over both Streamable HTTP (`127.0.0.1:47102/mcp`, unauth rejected `401`, protocol `2025-03-26`) and `--mcp-stdio` subprocess (`initialize`, `tools/list` returning 36 dynamic tools, `tools/call`, `resources/*`, `prompts/*`). Direct-tool argument validation gap tracked under Security (#15). |
| 6 | **AI provider integration (`core/nexus_core/providers/`, `server.ts`)** | `PARTIALLY IMPLEMENTED` | `server.ts` `@google/genai` compiles cleanly; Python `AIProviderManager` (`Gemini`, `Claude`, `OpenAI`, `OpenAI-Compatible`, `Custom`) verified in `unittest` against local `_LoopbackMockAIUpstream`. **Gaps**: Live cloud inference against external Gemini/Anthropic/OpenAI endpoints unverified; `http_sse_lines()` buffers responses rather than true socket streaming. |
| 7 | **REST API (`core/nexus_core/rest_gateway.py`)** | `PARTIALLY IMPLEMENTED` | Auth (`401`), `/health`, projects, adapters, tasks, diagnostics, and `/api/v1/daemon/shutdown` (`202`) verified live (`1.35 ms` p50). **Gap**: `POST /api/v1/adapters/{id}/tools/execute` returned HTTP **`200`** on unapproved `assets:modify` calls without checking `requires_approval()` or `validate_tool_arguments()`. |
| 8 | **WebSocket communication (`integrations/websocket/service.py`)** | `PARTIALLY IMPLEMENTED` | Live RFC-6455 upgrade tested: unauth rejected `401`, Bearer header accepted `101`, `bridge.status` welcome frame delivered. **Gaps**: (a) rejects browser/WebView2 `window.WebSocket` clients because only HTTP `Authorization` header is accepted (no `?token=` or `Sec-WebSocket-Protocol`); (b) frontend does not connect; (c) does not read client FIN or wake `queue.get()` on shutdown (`10s–15s` shutdown stall). |
| 9 | **Tool discovery (`core/nexus_core/tool_registry.py`, `capability_discovery.py`)** | `IMPLEMENTED AND VERIFIED` | Dynamically discovered 36 tools live (`12` built-in `nexus_*` + `12` Unity + `12` Godot); maintains honest `registeredToolCount = 0` prior to adapter attachment and isolates test-adapter tools from real counts. |
| 10 | **Adapter framework (`core/nexus_core/adapters/`)** | `IMPLEMENTED AND VERIFIED` | Manifest schema & protocol semver validation, `tcp-loopback` + `stdio` NDJSON JSON-RPC `2.0`, SQLite manifest persistence across restarts, health checks, and exponential backoff reconnection verified across unit tests and live loopback harness. |
| 11 | **Unity integration (`adapters/unity/`)** | `IMPLEMENTED BUT NOT VERIFIED` | 17 C# tools (`Unity` UPM package + `test_project`), `NexusMainThreadDispatcher` (`ConcurrentQueue` + `EditorApplication.update`), `Undo.*`, AssetDatabase/SceneManager/CompilationPipeline hooks verified in source and Python loopback protocol tests. **Not compiled or executed in live `Unity.exe` (`2022.3 LTS+`/`Unity 6`)**. Lacks standalone `unity.create_scene` without active scene (`save_scene` saves current/new path). |
| 12 | **Godot integration (`adapters/godot/addons/nexus_bridge/`)** | `IMPLEMENTED BUT NOT VERIFIED` | 18 GDScript tools (`EditorPlugin` + `test_project`), Godot `4.2+` version guard, `EditorUndoRedoManager`, `EditorFileSystem`, debugger/viewport capability discovery verified in source and Python loopback protocol tests. **Not executed in live `godot4` binary**. Minor bug in `nexus_godot_handlers.gd` (`modify_node` calls `undo_redo.create_action` before validating property existence, leaving an uncommitted UndoRedo action on error). |
| 13 | **Project context (`core/nexus_core/project_registry.py`, `orchestrator.py`)** | `IMPLEMENTED AND VERIFIED` | Persistent SQLite registry, allowed-roots validation, and orchestrator capture of scene/hierarchy/scripts/assets/logs/screenshots verified in live harness and unit suites. |
| 14 | **Autonomous tasks (`core/nexus_core/orchestrator.py`, `task_manager.py`, `concurrency.py`)** | `IMPLEMENTED AND VERIFIED` | 16-phase DAG pipeline, checkpoint/approval pause (`Unavailable`), bounded non-duplicate failure guard (`NEXUS_VALIDATION_ERROR`), multi-agent lock tracking, and SQLite task history persistence verified end-to-end. |
| 15 | **Security (`core/nexus_core/security.py`, `providers/credentials.py`)** | `PARTIALLY IMPLEMENTED` | Loopback enforcement, constant-time bearer auth, allowed executable allowlist, secret redaction, and orchestrator argument/path sandboxing pass. **Critical Security Defects**: (a) `WRITE_SCENE` omitted from `DESTRUCTIVE_SCOPES` so `unity.delete_object` & `godot.delete_node` execute without `_approved`; (b) direct `MCPServer.call_tool()` bypasses `validate_tool_arguments()`; (c) direct REST `/adapters/{id}/tools/execute` bypasses both `requires_approval()` and `validate_tool_arguments()`; (d) Windows `advapi32` `CredentialStore` is unverified on Windows (`0600` local fallback tested on Linux). |
| 16 | **Checkpointing (`core/nexus_core/checkpoints.py`)** | `IMPLEMENTED AND VERIFIED` | SHA-256 pre/post file change manifests, checkpoint snapshots on disk, and selective file rollback verified. |
| 17 | **Recovery (`core/nexus_core/task_manager.py`, `checkpoints.py`)** | `IMPLEMENTED AND VERIFIED` | Persistent `operation_journal`, `failed_operations` (`1` recorded on live controlled failure), selective rollback, `recover_interrupted_tasks()`, and adapter reconnection recovery verified. |
| 18 | **Installation (`scripts/*.ps1`, `tauri.conf.json`)** | `PARTIALLY IMPLEMENTED` | `npm run stage:adapters`, `npm run build`, and static PowerShell/Tauri configuration checks pass. **Gaps**: Windows `.exe`/`.msi` installers NOT built (`cargo`, `rustc`, `pyinstaller`, `makensis` unavailable); clean Windows VM install/uninstall NOT executed; `-ServiceMode` build fails unless `externalBin` is overridden. |
| 19 | **Documentation (`README.md`, `IMPLEMENTATION_STATUS.md`, `docs/*`)** | `PARTIALLY IMPLEMENTED` | Strong architectural, IPC, adapter, and Windows packaging docs with clear sandbox disclosures. **Gap**: `IMPLEMENTATION_STATUS.md` overstates desktop UI completion relative to `src/App.tsx` client-state placeholders and does not document the direct REST/MCP validation bypasses discovered in this audit. |

*Note on C++/Unreal Adapter (`adapters/cpp/`): Contains manifest/spec contract only — `NOT IMPLEMENTED`.*

---

## 3. Test Results

### 3.1 Existing Automated Test & Static Verification Suites (Re-Executed Live)

| Check | Command | Outcome | Observed Result |
| :--- | :--- | :--- | :--- |
| Python Unit, Integration, Protocol, Security, Recovery, Perf & Packaging Suite | `python3 -m unittest discover -s tests/python -p "test_*.py" -v` | **PASSED** (`exit 0`) | **37 tests passed in 3.191s** (run on Python `3.11.2` stdlib runtime; tests Stages 3–10 with loopback/mock upstreams rather than live Unity/Godot/Cloud APIs). |
| TypeScript / Express / Contract Tests | `npm test` | **PASSED** (`exit 0`) | **4 files, 17 tests passed** (`server`, `bridgeTransport`, `contracts`, `controlCenterService`) in `1.29s`. |
| TypeScript Compiler Strict Check | `npm run lint` (`tsc --noEmit`) | **PASSED** (`exit 0`) | `0` errors. |
| Static Code Lint | `npm run lint:code` (`oxlint`) | **PASSED** (`exit 0`) | `0` warnings, `0` errors. |
| Code Formatting Check | `npm run format:check` (`prettier`) | **PASSED** (`exit 0`) | All matched files conform. |
| Monorepo Structure Check | `npm run check:structure` | **PASSED** (`exit 0`) | 14 required architectural directories verified. |
| Vite + TypeScript Build & `lint_applet` | `compile_applet` + `lint_applet` | **PASSED** (`exit 0`) | Verified clean build & lint. |

### 3.2 Live Integration & Release Audit Harness (Executed Out-of-Process)

An isolated audit harness spawned real `python3 -m core.nexus_core --serve` on ephemeral loopback ports (`rest`, `ws`, `mcp`), backed by two TCP loopback NDJSON JSON-RPC `2.0` protocol servers operating on temporary copies of `adapters/unity/test_project/` and `adapters/godot/test_project/`:

- **Authentication Gates**: Unauthenticated REST `GET /api/v1/projects` -> **`401`**; unauthenticated MCP `GET /mcp` -> **`401`**; unauthenticated WebSocket upgrade -> **`401 Unauthorized`**.
- **WebSocket Live Check**: Authenticated RFC-6455 upgrade succeeded (`101 Switching Protocols`), received initial `bridge.status` welcome event.
- **MCP Dynamic Discovery & Operations (`Streamable HTTP` + `--mcp-stdio`)**:
  - `initialize` negotiated `"2025-03-26"`; `tools/list` dynamically exposed **`36` tools** (`12` built-in `nexus_*` + `12` `unity.*` + `12` `godot.*`).
  - Executed project inspection (`nexus_list_projects`, `unity.get_editor_state`, `godot.get_scene_state`), scene save (`unity.save_scene`, `godot.save_scene`), object/node creation (`unity.create_object`, `godot.create_node`), transform/node update (`unity.transform_object`, `godot.modify_node`), script creation on disk (`Assets/Scripts/AuditHero.cs` & `scripts/audit_hero.gd` verified present), compilation/error check (`unity.get_compilation_status`, `godot.get_errors`), runtime launch (`unity.control_play_mode`, `godot.launch_runtime`), and PNG screenshot output (`audit_unity.png`, `audit_godot.png`).
  - `--mcp-stdio` subprocess read back all **`4` persisted SQLite tasks** (`nexus_list_tasks`).
- **Autonomous Task, Controlled Failure & Recovery**:
  - Multi-step Unity autonomous task reached terminal status `Connected` (`2` operations executed).
  - Controlled Godot failure (`godot.modify_node` with `forceFail: true`, `maxRetries: 0`) returned `NEXUS_VALIDATION_ERROR` (`"No distinct repair strategy for 'step-01' (prevented duplicate retry)"`), persisting **`1` failed operation** and **`1` operation journal entry** in SQLite (`nexus_get_task_recovery`).
- **SQLite State & Integrity**:
  - `PRAGMA integrity_check` = **`"ok"`**, `PRAGMA journal_mode` = **`"wal"`**.
  - Verified row counts: `projects: 2`, `installed_adapters: 2`, `tasks: 4`, `checkpoints: 2`, `operation_journal: 3`, `failed_operations: 1`, `audit_logs: 82`, `ai_providers: 4`.
- **Native Engine & Installer Tests NOT Executable in Sandbox**:
  - `Unity.exe` (`NexusUnityIntegrationTests.cs`), `godot4` (`nexus_godot_verification.gd`), `powershell scripts/build-desktop.ps1`, and `powershell scripts/verify-windows-install.ps1` could **not** execute due to absent Windows/Unity/Godot/Rust toolchains in the Linux container.

---

## 4. Known Limitations

1. **Control Center UI Disconnected from Daemon State (`src/App.tsx`, `ToolsView.tsx`, `PluginsView.tsx`)**: Desktop shell diagnostics/engines talk to the daemon, but Projects, Tasks, Tools, Plugins, Providers, and real-time event streaming remain client-side React state/static contracts.
2. **Daemon Shutdown Stall with WebSocket Subscribers (`integrations/websocket/service.py`)**: `_handle_connection()` waits inside `queue.get(timeout=15.0)` without monitoring `reader` EOF or waking on `stop_requested`, causing graceful `POST /api/v1/daemon/shutdown` to take **`10,052 ms`** (~10–15s) even after client disconnect (exceeding the `600ms` wait in `scripts/uninstall-nexus.ps1`).
3. **Browser WebSocket Auth Compatibility**: `WebSocketEventService` only accepts `Authorization: Bearer <token>` headers; browser/WebView2 `window.WebSocket(url)` cannot pass custom headers.
4. **Windows `-ServiceMode` Build Conflict**: `tauri.conf.json` mandates `bundle.externalBin: ["binaries/nexus-daemon"]` while `scripts/build-desktop.ps1 -ServiceMode` skips sidecar freezing, causing `cargo tauri build` to fail unless `--config` overrides `externalBin`.
5. **IPv6 `::1` Loopback Formatting Bug (`daemon_manager.rs`)**: Allows `::1` host validation then interpolates `"{host}:{port}"` (`::1:47100` instead of `[::1]:47100`).
6. **Buffered SSE AI Provider Streaming (`core/nexus_core/providers/base.py`)**: `http_sse_lines()` calls `resp.read()` synchronously on the entire stream before yielding lines.
7. **Python 3.12+ / FastAPI Stack Untested**: Sandbox runs Python `3.11.2` without `fastapi`, `uvicorn`, `websockets`, `mcp`, `aiosqlite`, or `pyinstaller`.
8. **No Standalone Blank `create_scene` Tool**: Unity (`EditorSceneManager.SaveScene`) and Godot (`save_scene`) require an active open scene and do not expose standalone empty-scene creation (`NewScene`).
9. **Godot `modify_node` UndoRedo Edge Case (`nexus_godot_handlers.gd`)**: Calling `undo_redo.create_action()` before property existence validation can leave an uncommitted UndoRedo action if a property lookup fails mid-loop.

---

## 5. Security Assessment

### Controls Verified Active
- **Loopback Binding**: `NexusDaemonConfig` and `PermissionManager.assert_loopback_bind()` block non-loopback hosts unless explicitly overridden.
- **Constant-Time Bearer Auth**: REST (`127.0.0.1:47100`), WebSocket (`47101`), and MCP HTTP (`47102`) reject unauthenticated requests with `401` (`hmac.compare_digest` on `0600` token file).
- **Redaction & Process Allowlist**: `redact_sensitive_fields()` masks keys containing `secret`/`token`/`apikey`/`password`; `ALLOWED_PROCESS_NAMES` + `_SHELL_META_RE` guard restricted process inputs; orchestrator path traversal (`../../escape.cs`) was blocked (`NEXUS_PERMISSION_DENIED`) before dispatch.

### Critical Security Defects Found During Audit

| Severity | Finding | Observed Live Result | Root Cause Location |
| :--- | :--- | :--- | :--- |
| **HIGH** | **Direct REST `/api/v1/adapters/{id}/tools/execute` bypasses both approval gates and argument validation** | Unapproved `unity.import_asset` (`assets:modify`) returned HTTP **`200`** via REST! | `core/nexus_core/rest_gateway.py` (lines 337–347) & `core/nexus_core/adapters/manager.py` (`execute_tool` lines 628–652) never invoke `PermissionManager.requires_approval()` or `validate_tool_arguments()`. |
| **HIGH** | **Direct MCP `tools/call` bypasses daemon-level `validate_tool_arguments()`** | `assetPath: "../../escape.cs"` passed through `mcp_server.py` and reached the adapter TCP socket directly (`"Adapter-side sandbox blocked path traversal"` instead of daemon `NEXUS_PERMISSION_DENIED`). | `core/nexus_core/mcp_server.py` (lines 409–437) does not call `validate_tool_arguments(..., project_root=...)` (`Orchestrator` does). |
| **MEDIUM** | **`WRITE_SCENE` (`scene:write`) omitted from `DESTRUCTIVE_SCOPES` despite policy declaration** | `unity.delete_object` & `godot.delete_node` executed over MCP **without `_approved`** (`deleteObjectBlockedWithoutApproved: false`), while `unity.import_asset` (`assets:modify`) was blocked (`true`). | `core/nexus_core/security.py`: `PERMISSION_CATEGORIES["Project modification"]` marks `WRITE_SCENE` `destructive: True, requiresApproval: True`, yet line 78 `DESTRUCTIVE_SCOPES` omits `PermissionScope.WRITE_SCENE`. |
| **LOW** | **Windows Credential Manager (`advapi32`) backend unverified on host OS** | Executed only Linux `0600` fallback file; native Windows `CredWriteW`/`CredReadW` ctypes calls are unverified. | `core/nexus_core/providers/credentials.py`. |

---

## 6. Performance Results

Measured live against an out-of-process `python3 -m core.nexus_core --serve` daemon with WAL SQLite persistence (`n` sequential loopback HTTP/1.1 requests after connection warm-up):

| Benchmark Target | Sample Size (`n`) | Min (ms) | p50 (ms) | p95 (ms) | Max (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Authenticated REST `GET /api/v1/projects` | 50 | `1.06` | `1.35` | `2.53` | `4.07` |
| Authenticated MCP HTTP `POST /mcp` (`nexus_get_capabilities`) | 25 | `2.23` | `2.62` | `3.16` | `5.47` |
| Graceful Shutdown `POST /api/v1/daemon/shutdown` (after WS session) | 1 | — | — | — | **`10,052.08`** (defect) |

---

## 7. Installation Instructions (Windows 10/11 Target)

*Prerequisites on Windows 10/11 x64*: Node.js 22+, Python 3.12+, Rust `stable-x86_64-pc-windows-msvc`, Visual Studio 2022 C++ Build Tools + Windows SDK, Edge WebView2 Runtime, and `cargo install tauri-cli --version "^2.0.0"`.

1. **Build Bundled Sidecar + Windows Installers (Recommended until `-ServiceMode` `externalBin` config override is fixed)**:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\build-desktop.ps1
   ```
   Outputs NSIS (`NEXUS_0.10.0_x64-setup.exe`) and MSI (`NEXUS_0.10.0_x64_en-US.msi`) under `apps\desktop\src-tauri\target\release\bundle\`.
2. **Optional Standalone Background Daemon Service (Headless MCP/Engine Mode)**:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\setup-python.ps1
   powershell -ExecutionPolicy Bypass -File scripts\install-windows-service.ps1
   ```
3. **Install Game Engine Adapters**:
   - **Unity (`2022.3 LTS+` / `Unity 6`)**: Package Manager -> `+` -> **Add package from disk...** -> select `<InstallDir>\resources\adapters\unity\package.json`, then **Window -> NEXUS Bridge**.
   - **Godot (`4.2+`)**: Copy `<InstallDir>\resources\adapters\godot\addons\nexus_bridge\` into `<GodotProject>\addons\nexus_bridge\` and enable under **Project Settings -> Plugins**.
4. **Connect External MCP Client**:
   - **Stdio**: `nexus-daemon.exe --mcp-stdio` (or `python -m core.nexus_core --mcp-stdio`)
   - **HTTP**: `http://127.0.0.1:47102/mcp` with `Authorization: Bearer <token>` from `%LOCALAPPDATA%\NEXUS\daemon.token`.
5. **Clean Verification & Uninstallation on Windows VM**:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\verify-windows-install.ps1 `
     -InstallerExe "apps\desktop\src-tauri\target\release\bundle\nsis\NEXUS_0.10.0_x64-setup.exe" `
     -RunUninstallCheck
   powershell -ExecutionPolicy Bypass -File scripts\uninstall-nexus.ps1 -PurgeUserData
   ```

---

## 8. Release Readiness Assessment

### **Verdict: NOT PRODUCTION-READY (Staging / Windows Developer Preview Only)**

NEXUS has strong foundational Python daemon, MCP, adapter protocol, autonomous DAG orchestration, SQLite journaling, and checkpoint/rollback engineering—and every Stage 3–10 automated container test passes—**however it MUST NOT be released as production-ready** until all **P0 Release Blockers** below are resolved and verified:

#### P0 Release-Gating Blockers
1. **Enforce Unified Tool Security Across All Execution Paths**: Enforce `validate_tool_arguments()` and `validate_destructive_operation()` inside `AdapterManager.execute_tool()` / `REST` / `MCP`, and align `DESTRUCTIVE_SCOPES` so destructive `scene:write` operations (`delete_object`, `delete_node`) require explicit approval.
2. **Wire Control Center UI (`src/App.tsx`, `ToolsView.tsx`, `PluginsView.tsx`) to Live Daemon APIs & WebSocket**: Eliminate remaining in-memory mock/static UI handlers (`Projects`, `Tasks`, `Tools`, `Plugins`, `Providers`) and add browser-compatible WS auth (`?token=` or `Sec-WebSocket-Protocol` on `127.0.0.1`).
3. **Fix `WebSocketEventService` Shutdown Stall**: Monitor client `reader` EOF and wake `queue.get()` immediately on `daemon.request_shutdown()` so graceful exit completes in `<250 ms` instead of stalling `10–15 s`.
4. **Execute Native Engine Verification**: Run `NexusUnityIntegrationTests.cs` inside a real Windows **Unity 2022.3 LTS / Unity 6 Editor** and `nexus_godot_verification.gd` inside a real **Godot 4.2+ Editor** (and fix the `modify_node` UndoRedo early-return leak).
5. **Execute Windows Packaging & Clean VM Verification**: Fix `tauri.conf.json` `-ServiceMode` `externalBin` override and `daemon_manager.rs` `[::1]` formatting, compile real Windows NSIS/MSI installers (`scripts/build-desktop.ps1`), verify Windows `CredWriteW`/`CredReadW`, and pass `scripts/verify-windows-install.ps1 -RunUninstallCheck` on a clean Windows 10/11 x64 VM.
