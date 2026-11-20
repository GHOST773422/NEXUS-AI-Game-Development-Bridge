# NEXUS Language-Neutral Engine Adapter Protocol

**Protocol Version**: `1.0.0`  
**Framing**: UTF-8 Newline-Delimited JSON (NDJSON) JSON-RPC `2.0`

---

## 1. Design Principles

1. **Language Neutrality**: NEXUS Core (`core/nexus_core/`) never assumes game engine adapters run Python. Unity C# (`TcpListener`), Godot GDScript (`TCPServer`), C++ Unreal Editor modules, and third-party scripts communicate exclusively over NDJSON JSON-RPC `2.0`.
2. **Transport Independence**: Two local-only transports are supported:
   - `stdio`: Daemon spawns the adapter executable/script and exchanges single-line JSON frames over stdin/stdout.
   - `tcp-loopback`: Daemon connects to `127.0.0.1` (or `localhost` / `::1`) on the manifest's declared port. Non-loopback TCP hosts are rejected prior to activation.
3. **Strict Test Adapter Isolation**: Any test harness (`engineKind: "TestHarness"` or `isTestAdapter: true`) MUST return `"isTestAdapter": true` from `getEngineInfo()`. `AdapterManager` enforces this attestation and isolates test adapter tools/counts from real `connectedEngineCount` and `CoreToolRegistry.verified_count`.

---

## 2. Required JSON-RPC Methods (11 Canonical Operations)

| # | Method | Request `params` | Key Response `result` Fields |
| :--- | :--- | :--- | :--- |
| 1 | `getEngineInfo` | `{}` | `adapterId`, `displayName`, `engineKind`, `engineVersion`, `runtimeLanguage`, `protocolVersion`, `isTestAdapter` |
| 2 | `discoverProjects` | `{ searchRoots: string[] }` | `projects[]` (`id`, `name`, `engine`, `rootPath`, `engineVersion`) |
| 3 | `connect` | `{ adapterId, protocolVersion }` | `connected: true`, `sessionId`, `protocolVersion` |
| 4 | `disconnect` | `{}` | `disconnected: true` |
| 5 | `getCapabilities` | `{}` | `capabilities: string[]` |
| 6 | `listTools` | `{}` | `tools[]` (`id`, `category`, `description`, `inputSchema`, `outputSchema`, `requiredPermissions`, `executionContext`) |
| 7 | `executeTool` | `{ requestId, toolId, projectId, arguments }` | `requestId`, `toolId`, `projectId`, `status`, `verified`, `output` / `error` |
| 8 | `getProjectState` | `{ projectId }` | `projectId`, `activeScene`, scene/node/asset metadata |
| 9 | `subscribeEvents` | `{ topics: string[] }` | `subscribed: true`, `topics[]`; adapter pushes JSON-RPC notifications without `id` |
| 10 | `captureScreenshot` | `{ projectId, viewport }` | `projectId`, `viewport`, `mimeType: "image/png"`, `width`, `height`, `dataBase64` or `artifactPath` |
| 11 | `healthCheck` | `{}` | `responsive: boolean`, `connected: boolean`, `timestamp` |

---

## 3. Asynchronous Event Notifications

After `subscribeEvents` succeeds, adapters emit JSON-RPC `2.0` notifications (no `id` field):

```json
{"jsonrpc":"2.0","method":"adapter.event","params":{"topics":["engine.log"],"message":"Scene saved"}}
```

`AdapterManager` forwards these frames into `EventManager` tagged with `source = "adapter:<adapterId>"` and `isTestAdapter`.

---

## 4. Reconnection & Lifecycle State Machine

`Installed` -> `Validated` -> `Connecting` -> `Connected` -> (`Degraded` | `Reconnecting` -> `Connected` | `Failed`) -> `Disconnected`.

- Unexpected EOF triggers `NEXUS_ADAPTER_DISCONNECTED` error recording, clears active tool registrations, and launches `ReconnectionPolicy` exponential backoff attempts.
- Explicit `disconnect_adapter` or daemon shutdown cancels any pending reconnect task cleanly.
