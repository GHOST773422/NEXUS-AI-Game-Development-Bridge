# NEXUS AI Providers & MCP Integration Guide

## 1. Architectural Distinction: Built-in AI Providers vs. External MCP Clients

NEXUS strictly separates two independent communication flows:

1. **Built-in AI Providers (`integrations/ai-providers/`, `core/nexus_core/providers/`)**: Outbound inference clients initiated by NEXUS to contact external or local LLM APIs (Google Gemini, Anthropic Claude, OpenAI, OpenAI-compatible servers such as Ollama/LM Studio, or custom endpoints).
2. **External MCP Clients (`integrations/mcp/`, `core/nexus_core/mcp_server.py`)**: Inbound JSON-RPC `2.0` connections initiated by external agent hosts (Claude Desktop, Cursor, Windsurf, Gemini CLI) calling into NEXUS's `nexus-mcp` server to inspect engines, projects, capabilities, tasks, diagnostics, and execute verified tools.

Configuring an Anthropic API key inside Built-in AI Providers **does not** connect Claude Desktop via MCP, and adding `nexus-bridge` to Claude Desktop's MCP config **does not** give NEXUS outbound Anthropic API credits.

---

## 2. Built-in AI Providers & Secure Credential Storage

### Independent Provider Modules
- `integrations/ai-providers/gemini.py` (`GoogleGeminiProvider` — `x-goog-api-key`, `v1beta` `generateContent` + `streamGenerateContent`)
- `integrations/ai-providers/claude.py` (`AnthropicClaudeProvider` — `x-api-key`, `anthropic-version: 2023-06-01`, `/v1/messages` + SSE)
- `integrations/ai-providers/openai_provider.py` (`OpenAIProvider` — Bearer auth, `/v1/chat/completions` + SSE)
- `integrations/ai-providers/openai_compatible.py` (`OpenAICompatibleProvider` — Ollama, vLLM, LM Studio, OpenRouter)
- `integrations/ai-providers/custom.py` (`CustomProvider` — configurable HTTP JSON/SSE endpoint + custom auth header)

### Credential Reference Schemes (Zero Keys in Browser or SQLite)
- `env://VAR_NAME`: Reads API key from process environment variables (`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`).
- `wincred://nexus/<alias>`: Uses native Windows Credential Manager (`advapi32.dll` `CredReadW` / `CredWriteW`) on Windows 10/11, falling back to `0600`-restricted `~/.nexus/secrets.vault.json` on POSIX development hosts.
- `vault://nexus/<alias>`: Local `0600`-restricted key vault file (`~/.nexus/secrets.vault.json`).

Raw keys are never serialized in SQLite `ai_providers`, frontend bundles, `localStorage`, or structured JSON logs (`SecretRedactionFilter` masks `Bearer`, `sk-`, `AIza`, `x-api-key`, `x-goog-api-key`).

---

## 3. External MCP Server Setup (`nexus-mcp`)

### Capabilities Exposed
- **Dynamic Tools (`tools/list`, `tools/call`)**: Exposes core NEXUS bridge tools (`nexus_get_capabilities`, `nexus_get_diagnostics`, `nexus_list_engines`, `nexus_list_projects`, `nexus_register_project`, `nexus_list_tasks`, `nexus_create_task_draft`) plus every verified engine tool dynamically registered in `CoreToolRegistry`. Every execution enforces `PermissionManager` path sandboxing and `SQLiteStorageManager` audit logging.
- **Resources (`resources/list`, `resources/read`)**:
  - `nexus://engines`
  - `nexus://projects`
  - `nexus://capabilities`
  - `nexus://tasks`
  - `nexus://diagnostics`
  - `nexus://providers` (redacted metadata only)
- **Prompts (`prompts/list`, `prompts/get`)**:
  - `inspect_project_architecture`
  - `plan_engine_automation_task`
  - `diagnose_bridge_health`

### Connecting via Local `stdio` (Recommended for Claude Desktop / Cursor / Gemini CLI)

```json
{
  "mcpServers": {
    "nexus-bridge": {
      "command": "python",
      "args": ["-m", "core.nexus_core", "--mcp-stdio"],
      "cwd": "<PATH_TO_NEXUS_REPO>"
    }
  }
}
```

Or launch directly via `python -m integrations.mcp.server`.

### Connecting via Optional Loopback `Streamable HTTP`

1. Start the NEXUS daemon (`python -m core.nexus_core --serve`).
2. Read the generated loopback token from `~/.nexus/daemon.token`.
3. Configure your MCP HTTP client against `http://127.0.0.1:47102/mcp` with header:
   `Authorization: Bearer <token_from_daemon_token_file>`
