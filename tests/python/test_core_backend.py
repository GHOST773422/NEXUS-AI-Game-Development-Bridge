"""Comprehensive Automated Tests for NEXUS Core Backend (Stage 3)."""

from __future__ import annotations

import asyncio
import base64
import http.client
from io import StringIO
import json
import logging
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.nexus_core.config import NexusDaemonConfig
from core.nexus_core.daemon import NexusDaemon
from core.nexus_core.errors import PermissionDeniedError, ValidationError
from core.nexus_core.logging_config import SecretRedactionFilter, StructuredJsonFormatter
from sdk.python.nexus_sdk import EngineKind, NexusStatus, PermissionScope, ToolContract


def _http_json(
    host: str,
    port: int,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    conn = http.client.HTTPConnection(host, port, timeout=5)
    headers: dict[str, str] = {"Accept": "application/json"}
    raw_body: bytes | None = None
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        headers["Content-Type"] = "application/json"
        raw_body = json.dumps(body).encode("utf-8")
    conn.request(method, path, body=raw_body, headers=headers)
    resp = conn.getresponse()
    data = json.loads(resp.read().decode("utf-8"))
    conn.close()
    return resp.status, data


class TestNexusCoreBackend(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        self.allowed_root = self.tmp_dir / "workspace"
        self.allowed_root.mkdir()
        self.unity_proj = self.allowed_root / "UnitySample"
        self.unity_proj.mkdir()
        self.godot_proj = self.allowed_root / "GodotSample"
        self.godot_proj.mkdir()

        self.config = NexusDaemonConfig(
            bind_host="127.0.0.1",
            rest_port=0,
            ws_port=0,
            mcp_http_port=0,
            require_bearer_token=True,
            data_dir=self.tmp_dir / "nexus_data",
            sqlite_path=self.tmp_dir / "nexus_data" / "nexus.db",
            token_path=self.tmp_dir / "nexus_data" / "daemon.token",
            allowed_project_roots=[self.allowed_root],
        )

    async def asyncTearDown(self) -> None:
        self._tmp.cleanup()

    def test_config_rejects_non_loopback_by_default(self) -> None:
        with self.assertRaises(ValidationError):
            NexusDaemonConfig(
                bind_host="0.0.0.0",
                data_dir=self.tmp_dir / "d",
                sqlite_path=self.tmp_dir / "d" / "nexus.db",
                token_path=self.tmp_dir / "d" / "daemon.token",
            )

    def test_structured_logging_redacts_secrets(self) -> None:
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredJsonFormatter())
        handler.addFilter(SecretRedactionFilter())
        logger = logging.getLogger("nexus_test_redaction")
        logger.handlers = [handler]
        logger.setLevel(logging.INFO)
        logger.propagate = False

        logger.info("Using Bearer supersecrettoken12345 and sk-abcd1234efgh5678")
        output = stream.getvalue().strip()
        parsed = json.loads(output)
        self.assertNotIn("supersecrettoken12345", parsed["message"])
        self.assertNotIn("sk-abcd1234efgh5678", parsed["message"])
        self.assertIn("[REDACTED]", parsed["message"])

    async def test_daemon_startup_sqlite_persistence_and_graceful_shutdown(self) -> None:
        daemon1 = NexusDaemon(config=self.config)
        await daemon1.start(start_network=False)
        self.assertTrue(daemon1.is_running)

        health = await daemon1.health()
        self.assertEqual(health["status"], NexusStatus.CONNECTED.value)
        self.assertEqual(health["connectedEngineCount"], 0)
        self.assertEqual(health["registeredToolCount"], 0)

        p1 = await daemon1.projects.register_project(
            name="Unity Sample",
            engine=EngineKind.UNITY.value,
            root_path=str(self.unity_proj),
            require_existing_dir=True,
        )
        p2 = await daemon1.projects.register_project(
            name="Godot Sample",
            engine=EngineKind.GODOT.value,
            root_path=str(self.godot_proj),
            require_existing_dir=True,
        )
        self.assertTrue(p1.exists_on_disk)
        self.assertTrue(p2.exists_on_disk)
        await daemon1.stop()
        self.assertFalse(daemon1.is_running)

        # Restart a fresh daemon instance pointing to the same SQLite database.
        daemon2 = NexusDaemon(config=self.config)
        await daemon2.start(start_network=False)
        try:
            persisted = await daemon2.projects.list_projects()
            self.assertEqual(len(persisted), 2)
            diag = await daemon2.diagnostics.collect()
            self.assertEqual(diag["storage"]["integrity"], "ok")
        finally:
            await daemon2.stop()

    async def test_permission_manager_prevents_unauthorized_paths(self) -> None:
        daemon = NexusDaemon(config=self.config)
        await daemon.start(start_network=False)
        try:
            outside_dir = self.tmp_dir / "outside_secret"
            outside_dir.mkdir()
            with self.assertRaises(PermissionDeniedError):
                await daemon.projects.register_project(
                    name="Unauthorized",
                    engine=EngineKind.UNITY.value,
                    root_path=str(outside_dir),
                )
            with self.assertRaises(PermissionDeniedError):
                daemon.permissions.assert_path_within_project(
                    self.unity_proj, outside_dir / "passwords.txt"
                )
        finally:
            await daemon.stop()

    async def test_tool_registry_blocks_planned_dummy_tools(self) -> None:
        daemon = NexusDaemon(config=self.config)
        await daemon.start(start_network=False)
        try:
            planned = ToolContract(
                id="unity.fake.tool",
                category="Scene management",
                description="Should not register",
                input_schema={},
                output_schema={},
                engine_compatibility=[EngineKind.UNITY],
                required_permissions=[PermissionScope.READ_PROJECT],
                execution_context="EditorMainThread",
                error_handling="Structured",
                implementation_status=NexusStatus.PLANNED,
            )
            with self.assertRaises(ValidationError):
                daemon.tools.register_verified_tool(planned)
            self.assertEqual(daemon.tools.verified_count, 0)
        finally:
            await daemon.stop()

    async def test_live_loopback_rest_auth_projects_tasks_and_shutdown(self) -> None:
        daemon = NexusDaemon(config=self.config)
        await daemon.start(start_network=True)
        try:
            port = daemon.http_port
            assert port is not None
            token = self.config.get_or_create_api_token()

            # Unauthenticated /health succeeds
            status, health = await asyncio.to_thread(
                _http_json, "127.0.0.1", port, "GET", "/health"
            )
            self.assertEqual(status, 200)
            self.assertEqual(health["service"], "nexus-python-daemon")

            # Unauthenticated /api/v1/capabilities fails with 401 structured error
            status, unauth = await asyncio.to_thread(
                _http_json, "127.0.0.1", port, "GET", "/api/v1/capabilities"
            )
            self.assertEqual(status, 401)
            self.assertEqual(unauth["error"]["code"], "NEXUS_UNAUTHORIZED")

            # Authenticated /api/v1/capabilities succeeds
            status, caps = await asyncio.to_thread(
                _http_json, "127.0.0.1", port, "GET", "/api/v1/capabilities", token=token
            )
            self.assertEqual(status, 200)
            self.assertEqual(caps["registeredToolCount"], 0)
            self.assertEqual(caps["connectedEngineCount"], 0)

            # Register project via REST
            status, created_proj = await asyncio.to_thread(
                _http_json,
                "127.0.0.1",
                port,
                "POST",
                "/api/v1/projects",
                token=token,
                body={
                    "name": "REST Unity Game",
                    "engine": "Unity",
                    "rootPath": str(self.unity_proj),
                    "requireExistingDir": True,
                },
            )
            self.assertEqual(status, 201)
            proj_id = created_proj["project"]["id"]

            # Create task draft & verify execute refuses dummy execution (503)
            status, created_task = await asyncio.to_thread(
                _http_json,
                "127.0.0.1",
                port,
                "POST",
                "/api/v1/tasks",
                token=token,
                body={"projectId": proj_id, "title": "Inspect Scene"},
            )
            self.assertEqual(status, 201)
            task_id = created_task["task"]["id"]

            status, exec_err = await asyncio.to_thread(
                _http_json,
                "127.0.0.1",
                port,
                "POST",
                f"/api/v1/tasks/{task_id}/control",
                token=token,
                body={"action": "execute"},
            )
            self.assertEqual(status, 503)
            self.assertEqual(exec_err["error"]["code"], "NEXUS_DAEMON_UNAVAILABLE")

            # Authenticated shutdown signal
            status, shutdown_res = await asyncio.to_thread(
                _http_json,
                "127.0.0.1",
                port,
                "POST",
                "/api/v1/daemon/shutdown",
                token=token,
            )
            self.assertEqual(status, 202)
            self.assertTrue(shutdown_res["shuttingDown"])
            self.assertTrue(daemon.stop_requested)
        finally:
            await daemon.stop()

    async def test_websocket_event_service_auth_and_live_stream(self) -> None:
        daemon = NexusDaemon(config=self.config)
        await daemon.start(start_network=True)
        try:
            ws_port = daemon.ws_port
            assert ws_port is not None
            token = self.config.get_or_create_api_token()

            # Reject missing bearer token with 401
            reader, writer = await asyncio.open_connection("127.0.0.1", ws_port)
            ws_key = base64.b64encode(b"nexus-test-key-1").decode("ascii")
            writer.write(
                (
                    f"GET /events HTTP/1.1\r\n"
                    f"Host: 127.0.0.1:{ws_port}\r\n"
                    f"Upgrade: websocket\r\n"
                    f"Connection: Upgrade\r\n"
                    f"Sec-WebSocket-Key: {ws_key}\r\n"
                    f"Sec-WebSocket-Version: 13\r\n\r\n"
                ).encode("ascii")
            )
            await writer.drain()
            head = await reader.readuntil(b"\r\n\r\n")
            self.assertIn(b"401 Unauthorized", head)
            writer.close()
            await writer.wait_closed()

            # Accept valid bearer token and receive real event frame
            reader, writer = await asyncio.open_connection("127.0.0.1", ws_port)
            writer.write(
                (
                    f"GET /events HTTP/1.1\r\n"
                    f"Host: 127.0.0.1:{ws_port}\r\n"
                    f"Upgrade: websocket\r\n"
                    f"Connection: Upgrade\r\n"
                    f"Authorization: Bearer {token}\r\n"
                    f"Sec-WebSocket-Key: {ws_key}\r\n"
                    f"Sec-WebSocket-Version: 13\r\n\r\n"
                ).encode("ascii")
            )
            await writer.drain()
            head = await reader.readuntil(b"\r\n\r\n")
            self.assertIn(b"101 Switching Protocols", head)

            # Read initial welcome WS frame
            hdr = await reader.readexactly(2)
            payload_len = hdr[1] & 0x7F
            if payload_len == 126:
                payload_len = struct.unpack("!H", await reader.readexactly(2))[0]
            frame_json = json.loads((await reader.readexactly(payload_len)).decode("utf-8"))
            self.assertEqual(frame_json["type"], "bridge.status")

            # Publish a real event and confirm delivery
            await daemon.events.publish("engine.health", "test", {"status": "Disconnected"})
            hdr2 = await reader.readexactly(2)
            len2 = hdr2[1] & 0x7F
            if len2 == 126:
                len2 = struct.unpack("!H", await reader.readexactly(2))[0]
            evt_json = json.loads((await reader.readexactly(len2)).decode("utf-8"))
            self.assertEqual(evt_json["topic"], "engine.health")
            self.assertEqual(evt_json["data"]["status"], "Disconnected")

            writer.close()
            await writer.wait_closed()
        finally:
            await daemon.stop()

    async def test_engine_path_override_and_provider_delete_and_diagnostics(self) -> None:
        daemon = NexusDaemon(config=self.config)
        await daemon.start(start_network=True)
        try:
            port = daemon.http_port
            assert port is not None
            token = self.config.get_or_create_api_token()

            # 1. PATCH /api/v1/engines/Godot with traversal path fails with 400
            status, err_body = await asyncio.to_thread(
                _http_json,
                "127.0.0.1",
                port,
                "PATCH",
                "/api/v1/engines/Godot",
                token=token,
                body={"executablePath": "/tmp/../nonexistent/godot"},
            )
            self.assertEqual(status, 400)
            self.assertEqual(err_body["error"]["code"], "NEXUS_VALIDATION_ERROR")

            # 2. PATCH /api/v1/engines/Godot with nonexistent path reports honest Unavailable status
            missing_bin = self.tmp_dir / "missing_godot_bin"
            status, patch_res = await asyncio.to_thread(
                _http_json,
                "127.0.0.1",
                port,
                "PATCH",
                "/api/v1/engines/Godot",
                token=token,
                body={"executablePath": str(missing_bin)},
            )
            self.assertEqual(status, 200)
            godot_desc = next(e for e in patch_res["engines"] if e["engine"] == "Godot")
            self.assertEqual(godot_desc["detection_status"], NexusStatus.UNAVAILABLE.value)
            self.assertEqual(godot_desc["version"], "Configured path not found")

            # Reset override with empty string
            status, reset_res = await asyncio.to_thread(
                _http_json,
                "127.0.0.1",
                port,
                "PATCH",
                "/api/v1/engines/Godot",
                token=token,
                body={"executablePath": ""},
            )
            self.assertEqual(status, 200)
            self.assertEqual(len(reset_res["engines"]), 2)

            # 3. Built-in provider cannot be deleted; custom provider deletes cleanly
            status, del_builtin = await asyncio.to_thread(
                _http_json,
                "127.0.0.1",
                port,
                "DELETE",
                "/api/v1/providers/conn-gemini",
                token=token,
            )
            self.assertEqual(status, 400)
            self.assertEqual(del_builtin["error"]["code"], "NEXUS_VALIDATION_ERROR")

            status, created_prov = await asyncio.to_thread(
                _http_json,
                "127.0.0.1",
                port,
                "POST",
                "/api/v1/providers",
                token=token,
                body={
                    "name": "Local Ollama Test",
                    "kind": "OpenAI-Compatible",
                    "modelId": "qwen2.5-coder",
                    "endpointUrl": "http://127.0.0.1:11434/v1",
                },
            )
            self.assertEqual(status, 201)
            custom_id = created_prov["provider"]["id"]

            status, del_custom = await asyncio.to_thread(
                _http_json,
                "127.0.0.1",
                port,
                "DELETE",
                f"/api/v1/providers/{custom_id}",
                token=token,
            )
            self.assertEqual(status, 200)
            self.assertTrue(del_custom["deleted"])

            status, list_prov = await asyncio.to_thread(
                _http_json,
                "127.0.0.1",
                port,
                "GET",
                "/api/v1/providers",
                token=token,
            )
            self.assertEqual(status, 200)
            self.assertFalse(any(p["id"] == custom_id for p in list_prov["providers"]))

            # 4. Diagnostics passes connected adapters into EngineManager
            diag_empty = await daemon.diagnostics.collect()
            self.assertTrue(
                all(e["connection_status"] == NexusStatus.DISCONNECTED.value for e in diag_empty["engines"])
            )
        finally:
            await daemon.stop()


if __name__ == "__main__":
    unittest.main()
