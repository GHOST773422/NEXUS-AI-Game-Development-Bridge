# NEXUS Local IPC & Loopback Gateway Contract

**Contract Version**: `2026.1.0-stage3`  
**Target Operating System**: Windows 10/11 64-bit (plus POSIX dev compatibility)

## 1. Boundary Architecture

The React frontend communicates exclusively through the `BridgeTransport` interface (`src/services/bridgeTransport.ts`), which supports two interchangeable implementations:

1. **`HttpDaemonBridgeTransport`**: Communicates with the local Python daemon over `127.0.0.1` HTTP REST (`47100`) and WebSocket (`47101`).
2. **`TauriIpcBridgeTransport`**: Delegates to Rust IPC commands via `window.__TAURI_INTERNALS__.invoke(...)` when running inside the compiled Tauri 2 desktop shell.

## 2. Tauri 2 Shell <-> Frontend IPC Commands

| Command | Arguments | Return Type | Purpose |
| :--- | :--- | :--- | :--- |
| `get_desktop_runtime_info` | none | `DesktopRuntimeInfo` | Reports Windows OS, arch, and daemon supervision state |
| `get_daemon_status` | none | `DaemonProcessStatus` | Returns whether Python daemon child process is running |
| `get_local_auth_token` | none | `string` | Reads local loopback bearer token from protected OS vault/file |
| `probe_daemon_health` | `{ endpoint: string }` | `BridgeProbeResult` | Performs native loopback health probe from Rust |

## 3. Loopback REST API Contract (`127.0.0.1:47100`)

- **Default Binding**: Strictly `127.0.0.1` unless `NEXUS_ALLOW_REMOTE_BIND=true` is explicitly set.
- **Authentication**: All `/api/v1/*` routes require `Authorization: Bearer <token>` validated in constant time (`hmac.compare_digest`). `GET /health` returns liveness summary only.
- **Endpoints**:
  - `GET /health`
  - `GET /api/v1/capabilities`
  - `GET /api/v1/diagnostics`
  - `GET /api/v1/projects` · `POST /api/v1/projects` · `GET /api/v1/projects/:id` · `PATCH /api/v1/projects/:id` · `DELETE /api/v1/projects/:id`
  - `GET /api/v1/engines`
  - `GET /api/v1/tools`
  - `GET /api/v1/tasks` · `POST /api/v1/tasks` · `POST /api/v1/tasks/:id/control`
  - `GET /api/v1/events/recent`
  - `POST /api/v1/daemon/shutdown`

## 4. Structured Error Envelope

Every 4xx/5xx response returns:

```json
{
  "error": {
    "code": "NEXUS_PERMISSION_DENIED",
    "message": "Target path escapes the registered project directory sandbox.",
    "details": {},
    "timestamp": "2026-11-18T15:00:00+00:00"
  }
}
```

Standard codes: `NEXUS_UNAUTHORIZED` (`401`), `NEXUS_PERMISSION_DENIED` (`403`), `NEXUS_VALIDATION_ERROR` (`400`), `NEXUS_NOT_FOUND` (`404`), `NEXUS_CONFLICT` (`409`), `NEXUS_DAEMON_UNAVAILABLE` (`503`), `NEXUS_INTERNAL_ERROR` (`500`).

## 5. WebSocket Event Stream (`ws://127.0.0.1:47101/events`)

- Enforces `Authorization: Bearer <token>` during the HTTP 101 upgrade handshake (returns `401` JSON envelope on failure).
- Emits ordered JSON event frames (`sequence`, `topic`, `source`, `timestamp`, `data`) and RFC-6455 ping heartbeats (`15s`).
