# NEXUS Communication Protocol Specification

**Protocol Version**: `2026.1.0-stage1`

## 1. Transports

- **REST Control Plane (`127.0.0.1:47100`)**: Local HTTP JSON API for status, project discovery, configuration, and tool invocation.
- **WebSocket Event Bus (`127.0.0.1:47101/events`)**: Ordered event envelopes (`bridge.status`, `engine.health`, `engine.log`, `engine.scene_changed`, `task.step_updated`, `error.diagnostic`).
- **MCP Server (`stdio`, `127.0.0.1:47102/mcp` Streamable HTTP & SSE)**: JSON-RPC 2.0 exposure of verified `ToolRegistry` descriptors to external AI clients.

## 2. Security & Binding Rules

- All local daemon listeners bind strictly to `127.0.0.1` by default.
- REST and HTTP MCP requests require per-install local bearer token authorization on desktop deployments.
- Outbound AI provider keys are resolved exclusively in backend/vault layers and never transmitted to browser UIs.
