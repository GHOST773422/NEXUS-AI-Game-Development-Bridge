"""Stage 4 Automated Tests: Multi-Provider AI Framework, Credentials & MCP Server."""

from __future__ import annotations

import asyncio
import http.client
import json
import os
from pathlib import Path
import tempfile
import unittest

from core.nexus_core.config import NexusDaemonConfig
from core.nexus_core.daemon import NexusDaemon
from core.nexus_core.errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ValidationError,
)
from core.nexus_core.providers import (
    AnthropicClaudeProvider,
    CredentialStore,
    CustomProvider,
    GoogleGeminiProvider,
    OpenAICompatibleProvider,
    OpenAIProvider,
    ProviderCompletionRequest,
    ProviderConfig,
)
from sdk.python.nexus_sdk import (
    AIProviderKind,
    EngineKind,
    NexusStatus,
    PermissionScope,
    ToolContract,
)


class _LoopbackMockAIUpstream:
    """Real loopback asyncio HTTP/SSE server simulating upstream AI provider APIs."""

    def __init__(self) -> None:
        self._server: asyncio.AbstractServer | None = None
        self.port: int = 0
        self.last_headers: dict[str, str] = {}
        self.force_status: int | None = None

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        assert self._server.sockets
        self.port = int(self._server.sockets[0].getsockname()[1])
        return self.port

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            raw_head = await reader.readuntil(b"\r\n\r\n")
            lines = raw_head.decode("latin-1").split("\r\n")
            method, target, _ = lines[0].split(" ", 2)
            headers: dict[str, str] = {}
            for line in lines[1:]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
            self.last_headers = headers
            content_len = int(headers.get("content-length", "0") or "0")
            body_raw = await reader.readexactly(content_len) if content_len > 0 else b""
            body = json.loads(body_raw.decode("utf-8")) if body_raw else {}

            if self.force_status:
                err_bytes = json.dumps({"error": "forced"}).encode("utf-8")
                writer.write(
                    f"HTTP/1.1 {self.force_status} Error\r\n"
                    f"Content-Type: application/json\r\n"
                    f"Content-Length: {len(err_bytes)}\r\nConnection: close\r\n\r\n".encode("latin-1")
                    + err_bytes
                )
                await writer.drain()
                return

            if ":streamGenerateContent" in target:
                sse = (
                    'data: {"candidates":[{"content":{"parts":[{"text":"Hello "}]}}]}\n\n'
                    'data: {"candidates":[{"content":{"parts":[{"text":"Unity"}]},"finishReason":"STOP"}],"usageMetadata":{"promptTokenCount":5,"candidatesTokenCount":2,"totalTokenCount":7}}\n\n'
                ).encode("utf-8")
                self._send(writer, 200, sse, "text/event-stream")
            elif ":generateContent" in target:
                res = {
                    "modelVersion": "gemini-4-hydrogen",
                    "candidates": [
                        {
                            "content": {"parts": [{"text": "Gemini OK"}]},
                            "finishReason": "STOP",
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 10,
                        "candidatesTokenCount": 4,
                        "totalTokenCount": 14,
                    },
                }
                self._send(writer, 200, json.dumps(res).encode("utf-8"), "application/json")
            elif target.endswith("/v1/messages"):
                if body.get("stream"):
                    sse = (
                        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Claude "}}\n\n'
                        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Stream"}}\n\n'
                        'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":3}}\n\n'
                    ).encode("utf-8")
                    self._send(writer, 200, sse, "text/event-stream")
                else:
                    res = {
                        "id": "msg_1",
                        "model": body.get("model", "claude-sonnet-4-20250514"),
                        "content": [{"type": "text", "text": "Claude OK"}],
                        "stop_reason": "end_turn",
                        "usage": {"input_tokens": 8, "output_tokens": 3},
                    }
                    self._send(writer, 200, json.dumps(res).encode("utf-8"), "application/json")
            elif target.endswith("/v1/chat/completions"):
                if body.get("stream"):
                    sse = (
                        'data: {"choices":[{"delta":{"content":"OpenAI "}}]}\n\n'
                        'data: {"choices":[{"delta":{"content":"Stream"},"finish_reason":"stop"}]}\n\n'
                        "data: [DONE]\n\n"
                    ).encode("utf-8")
                    self._send(writer, 200, sse, "text/event-stream")
                else:
                    res = {
                        "id": "chatcmpl_1",
                        "model": body.get("model", "gpt-4.1"),
                        "choices": [
                            {
                                "message": {"role": "assistant", "content": "OpenAI OK"},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 6,
                            "completion_tokens": 2,
                            "total_tokens": 8,
                        },
                    }
                    self._send(writer, 200, json.dumps(res).encode("utf-8"), "application/json")
            elif target.endswith("/custom/chat"):
                res = {"content": "Custom OK", "usage": {"promptTokens": 3, "completionTokens": 2, "totalTokens": 5}}
                self._send(writer, 200, json.dumps(res).encode("utf-8"), "application/json")
            elif method == "GET":
                res = {"name": "models/gemini-4-hydrogen", "data": [{"id": "m1"}]}
                self._send(writer, 200, json.dumps(res).encode("utf-8"), "application/json")
            await writer.drain()
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    @staticmethod
    def _send(
        writer: asyncio.StreamWriter, status: int, body: bytes, ctype: str
    ) -> None:
        head = (
            f"HTTP/1.1 {status} OK\r\n"
            f"Content-Type: {ctype}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("latin-1")
        writer.write(head + body)


class TestAIProvidersAndMCP(unittest.IsolatedAsyncioTestCase):
    async def test_credential_store_protects_secrets_and_rejects_raw_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault = CredentialStore(Path(tmp) / "secrets.vault.json")
            with self.assertRaises(ValidationError):
                vault.validate_credential_ref("sk-raw-secret-123456")

            backend = vault.store_secret("wincred://nexus/test_key", "AIzaSecretTestValue999999")
            self.assertIn("Vault", backend)
            self.assertEqual(vault.resolve_secret("wincred://nexus/test_key"), "AIzaSecretTestValue999999")

            desc = vault.describe_credential("wincred://nexus/test_key")
            self.assertTrue(desc["credentialConfigured"])
            self.assertNotIn("AIzaSecretTestValue999999", json.dumps(desc))

            if os.name == "posix":
                mode = (Path(tmp) / "secrets.vault.json").stat().st_mode & 0o777
                self.assertEqual(mode, 0o600)

    async def test_all_five_ai_provider_modules_verify_generate_stream_and_handle_errors(self) -> None:
        upstream = _LoopbackMockAIUpstream()
        port = await upstream.start()
        base = f"http://127.0.0.1:{port}"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                vault = CredentialStore(Path(tmp) / "secrets.vault.json")
                vault.store_secret("vault://nexus/gemini", "AIzaTestKey123456789")
                vault.store_secret("vault://nexus/claude", "sk-ant-testkey123456")
                vault.store_secret("vault://nexus/openai", "sk-openai-testkey123456")
                vault.store_secret("vault://nexus/custom", "custom-token-abc")

                # 1. Google Gemini
                gem_cfg = ProviderConfig(
                    id="p-gem",
                    name="Gemini",
                    kind=AIProviderKind.GOOGLE_GEMINI,
                    enabled=True,
                    model_id="gemini-4-hydrogen",
                    endpoint_url=f"{base}/v1beta",
                    credential_ref="vault://nexus/gemini",
                )
                gemini = GoogleGeminiProvider(gem_cfg)
                self.assertIn("gemini-4-hydrogen", gemini.available_models())
                ver = await gemini.verify_connection(vault)
                self.assertTrue(ver.verified)
                self.assertEqual(ver.status, NexusStatus.CONNECTED)
                self.assertEqual(upstream.last_headers.get("x-goog-api-key"), "AIzaTestKey123456789")

                resp = await gemini.generate(
                    ProviderCompletionRequest(messages=[{"role": "user", "content": "hi"}]),
                    vault,
                )
                self.assertEqual(resp.content, "Gemini OK")
                self.assertEqual(resp.usage.total_tokens, 14)

                streamed = []
                async for chunk in gemini.stream(
                    ProviderCompletionRequest(messages=[{"role": "user", "content": "hi"}], stream=True),
                    vault,
                ):
                    streamed.append(chunk.delta_text)
                self.assertEqual("".join(streamed), "Hello Unity")

                # 2. Anthropic Claude
                claude_cfg = ProviderConfig(
                    id="p-claude",
                    name="Claude",
                    kind=AIProviderKind.ANTHROPIC_CLAUDE,
                    enabled=True,
                    model_id="claude-sonnet-4-20250514",
                    endpoint_url=f"{base}/v1",
                    credential_ref="vault://nexus/claude",
                )
                claude = AnthropicClaudeProvider(claude_cfg)
                c_ver = await claude.verify_connection(vault)
                self.assertTrue(c_ver.verified)
                self.assertEqual(upstream.last_headers.get("anthropic-version"), "2023-06-01")
                c_resp = await claude.generate(
                    ProviderCompletionRequest(messages=[{"role": "user", "content": "hi"}]),
                    vault,
                )
                self.assertEqual(c_resp.content, "Claude OK")
                self.assertEqual(c_resp.usage.total_tokens, 11)
                c_stream = [
                    ch.delta_text
                    async for ch in claude.stream(
                        ProviderCompletionRequest(messages=[{"role": "user", "content": "hi"}], stream=True),
                        vault,
                    )
                ]
                self.assertEqual("".join(c_stream), "Claude Stream")

                # 3. OpenAI
                oai_cfg = ProviderConfig(
                    id="p-oai",
                    name="OpenAI",
                    kind=AIProviderKind.OPENAI,
                    enabled=True,
                    model_id="gpt-4.1",
                    endpoint_url=f"{base}/v1",
                    credential_ref="vault://nexus/openai",
                )
                oai = OpenAIProvider(oai_cfg)
                o_resp = await oai.generate(
                    ProviderCompletionRequest(messages=[{"role": "user", "content": "hi"}]),
                    vault,
                )
                self.assertEqual(o_resp.content, "OpenAI OK")
                self.assertEqual(upstream.last_headers.get("authorization"), "Bearer sk-openai-testkey123456")
                o_stream = [
                    ch.delta_text
                    async for ch in oai.stream(
                        ProviderCompletionRequest(messages=[{"role": "user", "content": "hi"}], stream=True),
                        vault,
                    )
                ]
                self.assertEqual("".join(o_stream), "OpenAI Stream")

                # 4. OpenAI-Compatible (works even without key for local Ollama)
                compat_cfg = ProviderConfig(
                    id="p-compat",
                    name="Ollama",
                    kind=AIProviderKind.OPENAI_COMPATIBLE,
                    enabled=True,
                    model_id="llama3.2",
                    endpoint_url=f"{base}/v1",
                    credential_ref="vault://nexus/unused_local_token",
                )
                compat = OpenAICompatibleProvider(compat_cfg)
                lc_resp = await compat.generate(
                    ProviderCompletionRequest(messages=[{"role": "user", "content": "hi"}]),
                    vault,
                )
                self.assertEqual(lc_resp.content, "OpenAI OK")

                # 5. Custom provider
                custom_cfg = ProviderConfig(
                    id="p-custom",
                    name="Custom",
                    kind=AIProviderKind.CUSTOM,
                    enabled=True,
                    model_id="my-model",
                    endpoint_url=base,
                    credential_ref="vault://nexus/custom",
                    options={"chatPath": "/custom/chat", "healthPath": "/health"},
                )
                custom = CustomProvider(custom_cfg)
                cu_ver = await custom.verify_connection(vault)
                self.assertTrue(cu_ver.verified)
                cu_resp = await custom.generate(
                    ProviderCompletionRequest(messages=[{"role": "user", "content": "hi"}]),
                    vault,
                )
                self.assertEqual(cu_resp.content, "Custom OK")

                # Error handling: 401 & 429
                upstream.force_status = 401
                with self.assertRaises(ProviderAuthError):
                    await oai.generate(
                        ProviderCompletionRequest(messages=[{"role": "user", "content": "hi"}]),
                        vault,
                    )
                upstream.force_status = 429
                with self.assertRaises(ProviderRateLimitError):
                    await gemini.generate(
                        ProviderCompletionRequest(messages=[{"role": "user", "content": "hi"}]),
                        vault,
                    )
        finally:
            await upstream.stop()

    async def test_mcp_server_tools_resources_prompts_stdio_and_streamable_http(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "GodotSandbox"
            project_dir.mkdir(parents=True)

            cfg = NexusDaemonConfig(
                bind_host="127.0.0.1",
                rest_port=0,
                ws_port=0,
                mcp_http_port=0,
                data_dir=root / "nexus_data",
                sqlite_path=root / "nexus_data" / "nexus.db",
                token_path=root / "nexus_data" / "daemon.token",
                allowed_project_roots=[root],
                _api_token="stage4-mcp-bearer-token",
            )
            daemon = NexusDaemon(config=cfg)
            await daemon.start(start_network=True)
            try:
                assert daemon.http_port and daemon.mcp_port

                # Stdio JSON-RPC initialize + list_tools + register_project (traversal blocked vs valid)
                stdio_lines = [
                    json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
                    json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                    json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 3,
                            "method": "tools/call",
                            "params": {
                                "name": "nexus_register_project",
                                "arguments": {
                                    "name": "EscapeProject",
                                    "engine": "Godot",
                                    "rootPath": str(root / ".." / "escape"),
                                },
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 4,
                            "method": "tools/call",
                            "params": {
                                "name": "nexus_register_project",
                                "arguments": {
                                    "name": "GodotSandbox",
                                    "engine": "Godot",
                                    "rootPath": str(project_dir),
                                },
                            },
                        }
                    ),
                ]
                stdio_out = await daemon.mcp.serve_stdio_lines(stdio_lines)
                self.assertEqual(len(stdio_out), 4)
                init_res = json.loads(stdio_out[0])
                self.assertEqual(init_res["result"]["protocolVersion"], "2025-03-26")
                tools_res = json.loads(stdio_out[1])
                tool_names = {t["name"] for t in tools_res["result"]["tools"]}
                self.assertIn("nexus_get_capabilities", tool_names)
                self.assertIn("nexus_get_diagnostics", tool_names)

                # Traversal blocked by PermissionManager inside MCP tool execution
                blocked_res = json.loads(stdio_out[2])
                self.assertTrue(blocked_res["result"]["isError"])
                self.assertIn("NEXUS_PERMISSION_DENIED", blocked_res["result"]["content"][0]["text"])

                # Valid registration succeeds via same ProjectRegistry + SQLite + PermissionManager
                ok_res = json.loads(stdio_out[3])
                self.assertFalse(ok_res["result"]["isError"])
                reg_payload = json.loads(ok_res["result"]["content"][0]["text"])
                project_id = reg_payload["project"]["id"]

                # Dynamic tool discovery: register a verified tool into CoreToolRegistry and call via MCP
                daemon.tools.register_verified_tool(
                    ToolContract(
                        id="godot.ping_test",
                        category="Debugging",
                        description="Verified ping tool",
                        input_schema={"type": "object", "properties": {}},
                        output_schema={"type": "object"},
                        engine_compatibility=[EngineKind.GODOT],
                        required_permissions=[PermissionScope.READ_PROJECT],
                        execution_context="Editor main thread",
                        error_handling="Returns structured error if editor disconnected",
                        implementation_status=NexusStatus.CONNECTED,
                    )
                )

                async def _ping_handler(_args: dict[str, object]) -> dict[str, object]:
                    return {"pong": True}

                daemon.mcp.attach_engine_tool_handler("godot.ping_test", _ping_handler)
                dynamic_names = {t["name"] for t in daemon.mcp.list_tools()}
                self.assertIn("godot.ping_test", dynamic_names)

                # Resources & Prompts
                res_read = await daemon.mcp.read_resource("nexus://providers")
                provider_text = res_read["contents"][0]["text"]
                self.assertIn("Google Gemini", provider_text)
                prompt_res = await daemon.mcp.get_prompt(
                    "inspect_project_architecture", {"projectId": project_id}
                )
                self.assertIn("GodotSandbox", prompt_res["messages"][0]["content"]["text"])

                # Streamable HTTP MCP transport: 401 without Bearer, 200 with Bearer
                def _http_call(
                    port: int, method: str, path: str, body: bytes | None, headers: dict[str, str]
                ) -> tuple[int, dict[str, str], dict[str, object]]:
                    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                    conn.request(method, path, body=body, headers=headers)
                    r = conn.getresponse()
                    raw = r.read().decode("utf-8")
                    hdrs = {k.lower(): v for k, v in r.getheaders()}
                    conn.close()
                    return r.status, hdrs, json.loads(raw) if raw else {}

                s_unauth, _, _ = await asyncio.to_thread(
                    _http_call,
                    daemon.mcp_port,
                    "GET",
                    "/mcp",
                    None,
                    {},
                )
                self.assertEqual(s_unauth, 401)

                s_call, resp_headers, call_body = await asyncio.to_thread(
                    _http_call,
                    daemon.mcp_port,
                    "POST",
                    "/mcp",
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 99,
                            "method": "tools/call",
                            "params": {"name": "godot.ping_test", "arguments": {}},
                        }
                    ).encode("utf-8"),
                    {
                        "Authorization": "Bearer stage4-mcp-bearer-token",
                        "Content-Type": "application/json",
                    },
                )
                self.assertEqual(s_call, 200)
                self.assertIn("mcp-session-id", resp_headers)
                self.assertEqual(
                    json.loads(call_body["result"]["content"][0]["text"]),
                    {"pong": True},
                )

                # Built-in provider REST endpoint & MCP status check (never exposes secrets)
                s_prov, _, prov_body = await asyncio.to_thread(
                    _http_call,
                    daemon.http_port,
                    "GET",
                    "/api/v1/providers",
                    None,
                    {"Authorization": "Bearer stage4-mcp-bearer-token"},
                )
                self.assertEqual(s_prov, 200)
                self.assertGreaterEqual(len(prov_body["providers"]), 4)
            finally:
                await daemon.stop()
