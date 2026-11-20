# NEXUS Architecture Specification

## 1. Monorepo Directory Structure

```text
nexus/
├── src/                        # React 19 + TypeScript Control Center frontend
├── server.ts                   # Node.js Express preview backend + server-side @google/genai proxy
├── apps/desktop/               # Tauri 2 + Rust Windows 10/11 desktop shell scaffolding
├── core/                       # Python 3.12+ daemon package (nexus_core, adapters/, providers/, mcp_server.py)
├── adapters/
│   ├── unity/                  # Native Unity C# Editor integration & manifest (tcp-loopback)
│   ├── godot/                  # Native Godot 4.x GDScript EditorPlugin & manifest (tcp-loopback)
│   ├── cpp/                    # Future native C++ / Unreal Editor adapter manifest & contract
│   └── test-adapter/           # Explicit out-of-process synthetic JSON-RPC 2.0 protocol harness
├── integrations/
│   ├── mcp/                    # MCP server schemas & runnable stdio server entrypoint
│   ├── rest-api/               # REST API route contracts & FastAPI/stdlib router re-export
│   ├── websocket/              # WebSocket event envelope schemas & RFC-6455 event service
│   └── ai-providers/           # Independent provider modules (Gemini, Claude, OpenAI, Compatible, Custom)
├── sdk/
│   ├── ts/                     # Shared TypeScript status, adapter, IPC, and protocol contracts
│   └── python/nexus_sdk/       # Shared Python dataclass & ABC contracts
├── tools/                      # 19-category tool contracts & Python ToolRegistry
├── tests/
│   ├── ts/                     # Vitest frontend, transport, contract, and Express API tests
│   └── python/                 # unittest/pytest Python daemon, AI provider, MCP & adapter protocol tests
├── docs/                       # Build, IPC, AI/MCP, Adapter Protocol & Manifest specifications
├── config/                     # Default runtime config, permissions, oxlint, prettier
└── scripts/                    # Directory checks & Windows local build scripts
```

## 2. Logical Layers & Strict Separation

1. **Frontend (`src/`)**: Communicates exclusively through `BridgeTransport` and `/api/*` endpoints; never embeds API secrets or direct OS process calls.
2. **Preview Backend (`server.ts`)**: Node.js Express server serving Vite middleware in dev and `dist/` in production, exposing `/api/health`, `/api/runtime/capabilities`, `/api/protocol/schemas`, SSRF-guarded `/api/bridge/probe`, and server-side Gemini `@google/genai` verification/generation endpoints (`/api/ai/providers/verify`, `/api/ai/providers/generate`).
3. **Python Background Daemon (`core/nexus_core/`)**: Standalone asyncio daemon coordinating lifecycle, loopback-first configuration, WAL-mode SQLite persistence (`installed_adapters`, `ai_providers`, `projects`, `tasks`, `audit_log`), binary-probing engine manager, verified-only tool registry, capability discovery, event manager, task drafts, diagnostics, secret-redacting logs, multi-provider inference (`providers/`), MCP server (`mcp_server.py`), and `AdapterManager` (`adapters/`).
4. **Universal Engine Adapter Boundary (`core/nexus_core/adapters/`)**: Language-neutral NDJSON JSON-RPC `2.0` runtime (`stdio` and loopback `tcp-loopback`) supporting `C#`, `GDScript`, `C++`, and third-party plugins without assuming Python inside engine processes.
5. **Outbound AI Providers vs. Inbound MCP Clients**: Built-in providers initiate outbound API calls via `CredentialStore`; external MCP hosts connect inbound to `nexus-mcp` (`stdio` or Bearer-authenticated `Streamable HTTP`) via `CoreToolRegistry` and `PermissionManager`.

## 3. Environment Incompatibilities (Google AI Studio vs. Windows Desktop)

- **Tauri 2 & Rust**: `cargo` and WebView2 do not execute in AI Studio's Linux web container; `apps/desktop/src-tauri/` must be built locally on Windows 10/11.
- **Python Version & OS Credential Manager**: AI Studio runs Python `3.11.2` without external pip wheels; `CredentialStore` uses native `advapi32` Windows Credential Manager when `sys.platform == "win32"` and falls back cleanly to a `0600`-restricted local vault file on Linux.
- **Unity, Godot & Unreal Editors**: No native engine binaries exist in the cloud sandbox; `EngineManager` and `AdapterManager` keep `connectedEngineCount = 0` and `registeredToolCount = 0` until real editor plugins attach.
