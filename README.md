# NEXUS — AI Game Development Bridge

NEXUS is a desktop-first universal bridge enabling AI assistants, external MCP clients, and autonomous development agents to inspect, modify, execute, debug, test, and manage real game development projects in **Unity**, **Godot**, and future C++/third-party engine targets.

## Current Stage

**Stage 10 — Windows Desktop Packaging (Ready for Local Windows Native Compilation)**

- **Standalone Windows Desktop Architecture (`apps/desktop/src-tauri/`)**: Tauri 2 + Rust desktop shell with background Python 3.12+ sidecar / independent service supervision (`DaemonSupervisor`), zero-dependency loopback HTTP/1.1 IPC, secure `%LOCALAPPDATA%\NEXUS\` config & token management (`0600` / user profile ACLs), graceful UI-exit vs. keep-daemon-alive handling, rotating structured logs (`desktop-shell.log` & `nexus-daemon.log`), offline diagnostics, and synchronized **`0.10.0`** version metadata.
- **Zero Cloud / AI Studio Lock-In**: The compiled desktop bundle (`dist/`) and `nexus-daemon` run 100% locally on loopback (`127.0.0.1:47100/47101/47102`) without Google AI Studio or any required external cloud server.
- **Autonomous Development Engine & Security (`core/nexus_core/`)**: Checkpointed 16-phase DAG workflow, 7 capability-based permission categories, cross-platform sandboxing, `operation_journal` + `failed_operations`, pre/post SHA-256 manifests, selective file rollback, and crash recovery.
- **Native Engine Adapters & Bundled Resources**: Staged Unity UPM C# package (`adapters/unity/` -> `resources/adapters/unity/`) and Godot `4.2+` GDScript `EditorPlugin` (`adapters/godot/addons/nexus_bridge/` -> `resources/adapters/godot/`), plus standalone test projects.
- **Honest Build Disclosure**: Because AI Studio's Linux sandbox lacks `cargo`, `rustc`, `pyinstaller`, `makensis`, `Unity.exe`, and `godot4`, native Windows installer compilation (`scripts/build-desktop.ps1`) and clean Windows VM install/uninstall checks (`scripts/verify-windows-install.ps1`) have **not** been executed in this container and must be run on Windows 10/11 x64.

## Documentation Index

- `ARCHITECTURE.md` — System architecture, directory layout, and environment boundaries
- `IMPLEMENTATION_STATUS.md` — Verified status of features, limitations, and test ledger
- `ROADMAP.md` — Staged delivery plan
- `DECISIONS.md` — Architectural Decision Records (`ADR-001` through `ADR-014`)
- `TEST_REPORT.md` — Exact executed checks and results
- `CHANGELOG.md` — Chronological release/stage notes
- `docs/WINDOWS_PACKAGING_AND_INSTALL.md` — Stage 10 Windows installer build, prerequisites, sidecar/service modes & clean VM testing
- `docs/TAURI_BUILD.md` — Tauri 2 Rust build steps
- `docs/LOCAL_IPC_CONTRACT.md` — Local IPC, REST, Bearer Auth, and WebSocket event specification
- `docs/AI_PROVIDERS_AND_MCP.md` — AI provider credential setup & external MCP client instructions
- `docs/ADAPTER_PROTOCOL.md` — Language-neutral 11-method JSON-RPC 2.0 adapter wire protocol
- `docs/ADAPTER_MANIFEST_SPEC.md` — `nexus-adapter.manifest.json` schema & pre-activation checks
- `docs/UNITY_ADAPTER_GUIDE.md` — Native Unity Editor C# UPM setup, 17 tools, multi-project & Unity Test Runner guide
- `docs/GODOT_ADAPTER_GUIDE.md` — Native Godot 4.2+ GDScript EditorPlugin, 18 tools, test project & verification guide
- `docs/SECURITY_AND_RECOVERY.md` — 7 permission categories, sandboxing, operation journaling, selective rollback & crash recovery
