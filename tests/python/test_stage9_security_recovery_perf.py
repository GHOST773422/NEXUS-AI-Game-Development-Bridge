"""Stage 9 Comprehensive Security, Permissions, Recovery & Performance Verification."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import http.client
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from typing import Any

from core.nexus_core.adapters.manifest import parse_adapter_manifest, validate_adapter_compatibility
from core.nexus_core.config import NexusDaemonConfig
from core.nexus_core.daemon import NexusDaemon
from core.nexus_core.errors import AdapterCompatibilityError, PermissionDeniedError, ValidationError
from core.nexus_core.rest_gateway import dispatch_rest_request
from sdk.python.nexus_sdk import NexusStatus, PermissionScope
from tests.python.test_stage8_autonomous_engine import _LoopbackAutonomousAdapterServer


class _DualFileMutationAdapter(_LoopbackAutonomousAdapterServer):
    """Test Unity loopback adapter mutating real Assets/Scripts files for recovery verification."""

    def _dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "executeTool":
            tool_id = str(params.get("toolId", ""))
            args = dict(params.get("arguments") or {})
            if tool_id == "unity.create_script":
                rel = str(args.get("path", "")).lstrip("/")
                if args.get("forceFail"):
                    return {
                        "verified": False,
                        "status": "Failed",
                        "error": "CS1002: ; expected",
                    }
                target = (self.project_root / rel).resolve()
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(str(args.get("content", "")), encoding="utf-8")
                self.created_files[rel] = str(args.get("content", ""))
                return {"verified": True, "status": "Succeeded", "output": {"writtenPath": rel}}
        return super()._dispatch(method, params)


class TestStage9SecurityRecoveryPerformance(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_root = Path(self.tmp.name).resolve()
        self.data_dir = self.tmp_root / "daemon_data"
        self.unity_proj = self.tmp_root / "UnitySample"
        (self.unity_proj / "Assets" / "Scripts").mkdir(parents=True)
        (self.unity_proj / "Assets" / "Scripts" / "FileA.cs").write_text("// initial A\n", encoding="utf-8")
        (self.unity_proj / "Assets" / "Scripts" / "FileB.cs").write_text("// initial B\n", encoding="utf-8")

        self.config = NexusDaemonConfig(
            data_dir=self.data_dir,
            sqlite_path=self.data_dir / "nexus.db",
            token_path=self.data_dir / "daemon.token",
            bind_host="127.0.0.1",
            rest_port=0,
            ws_port=0,
            mcp_http_port=0,
            require_bearer_token=True,
            allowed_project_roots=[self.tmp_root],
        )
        self.daemon = NexusDaemon(self.config)
        await self.daemon.start(start_network=True)
        self.token = self.config.get_or_create_api_token()
        self.auth_headers = {"authorization": f"Bearer {self.token}"}

    async def asyncTearDown(self) -> None:
        await self.daemon.stop()
        self.tmp.cleanup()

    async def test_security_categories_sandboxing_validation_and_manifest_integrity(self) -> None:
        # 1. All 7 Permission Categories exposed & enforced via REST
        status, cats_body = await dispatch_rest_request(
            self.daemon, "GET", "/api/v1/permissions/categories", self.auth_headers
        )
        self.assertEqual(status, 200)
        cats = cats_body["categories"]
        for expected in (
            "Read-only inspection",
            "Non-destructive modification",
            "Project modification",
            "Script execution",
            "Runtime control",
            "Build and export",
            "External process access",
        ):
            self.assertIn(expected, cats)

        # 2. Unauthenticated REST request returns 401
        unauth_status, _ = await dispatch_rest_request(
            self.daemon, "GET", "/api/v1/projects", {}
        )
        self.assertEqual(unauth_status, 401)

        # 3. Network exposure blocked outside loopback
        with self.assertRaises(PermissionDeniedError):
            self.daemon.permissions.assert_loopback_bind("0.0.0.0")

        # 4. Path traversal, outside-project access & shell injection blocked
        with self.assertRaises(PermissionDeniedError):
            self.daemon.permissions.validate_tool_arguments(
                "unity.create_script",
                {"path": "../../etc/passwd"},
                project_root=self.unity_proj,
            )
        with self.assertRaises(PermissionDeniedError):
            self.daemon.permissions.validate_tool_arguments(
                "unity.create_script",
                {"filePath": "C:/Windows/System32/evil.dll"},
                project_root=self.unity_proj,
            )
        with self.assertRaises(PermissionDeniedError):
            self.daemon.permissions.validate_tool_arguments(
                "custom.exec",
                {"command": "powershell.exe; Invoke-WebRequest"},
                project_root=self.unity_proj,
            )
        with self.assertRaises(ValidationError):
            self.daemon.permissions.validate_tool_arguments(
                "bad\x00tool", {"path": "Assets/Scripts/FileA.cs"}
            )
        with self.assertRaises(PermissionDeniedError):
            self.daemon.permissions.validate_destructive_operation(
                [PermissionScope.BUILD_EXPORT], approved=False
            )
        with self.assertRaises(PermissionDeniedError):
            self.daemon.permissions.validate_destructive_operation(
                [PermissionScope.WRITE_SCENE], approved=False
            )

        # 5. Plugin manifest tampering / SHA-256 mismatch & traversal rejected
        plugin_dir = self.tmp_root / "plugin_pkg"
        plugin_dir.mkdir()
        entry_file = plugin_dir / "adapter.py"
        entry_file.write_text("print('trusted')", encoding="utf-8")
        good_hash = hashlib.sha256(entry_file.read_bytes()).hexdigest()

        raw_manifest = {
            "manifestVersion": "1.0",
            "adapterId": "sec-test-adapter",
            "displayName": "Sec Test",
            "version": "1.0.0",
            "runtimeLanguage": "Python",
            "engineKind": "Custom",
            "isTestAdapter": False,
            "protocolVersion": "1.0.0",
            "minDaemonProtocolVersion": "1.0.0",
            "maxDaemonProtocolVersion": "1.99.99",
            "transport": {"kind": "tcp-loopback", "host": "127.0.0.1", "port": 47999},
            "entrypoint": "adapter.py",
            "checksumSha256": good_hash,
        }
        validate_adapter_compatibility(parse_adapter_manifest(raw_manifest), base_dir=plugin_dir)

        entry_file.write_text("print('tampered!')", encoding="utf-8")
        with self.assertRaises(AdapterCompatibilityError):
            validate_adapter_compatibility(parse_adapter_manifest(raw_manifest), base_dir=plugin_dir)

        traversal_manifest = {**raw_manifest, "entrypoint": "../escape.py"}
        with self.assertRaises(AdapterCompatibilityError):
            validate_adapter_compatibility(parse_adapter_manifest(traversal_manifest), base_dir=plugin_dir)

    async def test_journal_failed_ops_manifest_and_selective_rollback(self) -> None:
        srv = _DualFileMutationAdapter(project_root=self.unity_proj, engine_kind="Unity")
        port = await srv.start()
        try:
            manifest = {
                "manifestVersion": "1.0",
                "adapterId": "nexus-unity-rec",
                "displayName": "Recovery Unity Adapter",
                "version": "1.0.0",
                "runtimeLanguage": "C#",
                "engineKind": "Unity",
                "isTestAdapter": False,
                "protocolVersion": "1.0.0",
                "minDaemonProtocolVersion": "1.0.0",
                "maxDaemonProtocolVersion": "1.99.99",
                "transport": {"kind": "tcp-loopback", "host": "127.0.0.1", "port": port},
                "entrypoint": "NexusUnityAdapter.cs",
                "capabilities": ["script_write", "screenshot_capture"],
                "requestedPermissions": ["project:read", "script:write"],
                "supportedEngineVersions": ["2022.3"],
            }
            await self.daemon.adapters.install_adapter(manifest)
            await self.daemon.adapters.connect_adapter("nexus-unity-rec")

            proj = await self.daemon.projects.register_project(
                name="UnitySample",
                engine="Unity",
                root_path=str(self.unity_proj),
                require_existing_dir=True,
            )

            # Mutate FileA.cs and FileB.cs via autonomous task
            task = await self.daemon.tasks.create_task_draft(
                project_id=proj.id,
                title="Mutate two C# scripts for selective rollback test",
                adapter_id="nexus-unity-rec",
                operations=[
                    {
                        "opId": "op-a",
                        "toolId": "unity.create_script",
                        "arguments": {
                            "path": "Assets/Scripts/FileA.cs",
                            "content": "// modified A\n",
                            "overwrite": True,
                        },
                    },
                    {
                        "opId": "op-b",
                        "toolId": "unity.create_script",
                        "arguments": {
                            "path": "Assets/Scripts/FileB.cs",
                            "content": "// modified B\n",
                            "overwrite": True,
                        },
                        "dependsOn": ["op-a"],
                    },
                ],
            )
            executed = await self.daemon.tasks.execute_task(task["id"], adapter_id="nexus-unity-rec")
            self.assertEqual(executed["status"], "Connected")
            self.assertEqual(
                (self.unity_proj / "Assets" / "Scripts" / "FileA.cs").read_text(encoding="utf-8"),
                "// modified A\n",
            )
            self.assertEqual(
                (self.unity_proj / "Assets" / "Scripts" / "FileB.cs").read_text(encoding="utf-8"),
                "// modified B\n",
            )

            # Inspect operation journal + file change manifest via REST
            st_j, journal_body = await dispatch_rest_request(
                self.daemon, "GET", f"/api/v1/tasks/{task['id']}/journal", self.auth_headers
            )
            self.assertEqual(st_j, 200)
            self.assertEqual(len(journal_body["operationJournal"]), 2)
            self.assertIsNotNone(journal_body["fileChangeManifest"])
            self.assertEqual(journal_body["fileChangeManifest"]["changedCount"], 2)

            # Selective rollback ONLY FileA.cs -> FileA reverts to "// initial A\n", FileB stays "// modified B\n"
            st_rb, rb_body = await dispatch_rest_request(
                self.daemon,
                "POST",
                f"/api/v1/tasks/{task['id']}/rollback",
                self.auth_headers,
                json.dumps({"files": ["Assets/Scripts/FileA.cs"]}).encode("utf-8"),
            )
            self.assertEqual(st_rb, 200)
            self.assertTrue(rb_body["rollback"]["selective"])
            self.assertEqual(rb_body["rollback"]["restoredFiles"], ["Assets/Scripts/FileA.cs"])
            self.assertEqual(
                (self.unity_proj / "Assets" / "Scripts" / "FileA.cs").read_text(encoding="utf-8"),
                "// initial A\n",
            )
            self.assertEqual(
                (self.unity_proj / "Assets" / "Scripts" / "FileB.cs").read_text(encoding="utf-8"),
                "// modified B\n",
            )

            # Verify engine failure payload (verified: False) is recorded in failed_operations with redacted secrets
            fail_task = await self.daemon.tasks.create_task_draft(
                project_id=proj.id,
                title="Verify failed operation persistence and secret redaction",
                adapter_id="nexus-unity-rec",
                operations=[
                    {
                        "opId": "op-fail",
                        "toolId": "unity.create_script",
                        "arguments": {
                            "path": "Assets/Scripts/FileA.cs",
                            "forceFail": True,
                            "apiKey": "SECRET-MUST-BE-REDACTED",
                        },
                    }
                ],
            )
            with self.assertRaises(ValidationError):
                await self.daemon.tasks.execute_task(fail_task["id"], adapter_id="nexus-unity-rec")

            st_fj, fail_journal = await dispatch_rest_request(
                self.daemon, "GET", f"/api/v1/tasks/{fail_task['id']}/journal", self.auth_headers
            )
            self.assertEqual(st_fj, 200)
            self.assertEqual(len(fail_journal["failedOperations"]), 1)
            fop = fail_journal["failedOperations"][0]
            self.assertIn("CS1002", fop["errorMessage"])
            self.assertEqual(fop["arguments"]["apiKey"], "[REDACTED]")
        finally:
            await srv.stop()

    async def test_daemon_restart_recovers_interrupted_tasks(self) -> None:
        proj = await self.daemon.projects.register_project(
            name="UnityCrashTest",
            engine="Unity",
            root_path=str(self.unity_proj),
            require_existing_dir=True,
        )
        task = await self.daemon.tasks.create_task_draft(
            project_id=proj.id,
            title="Simulated mid-flight crash task",
        )
        # Simulate task + journal left in 'Running' state by unclean crash before restart
        await self.daemon.storage.execute(
            "UPDATE tasks SET status = ?, current_operation = ? WHERE id = ?",
            (NexusStatus.RUNNING.value, "Writing scene object before crash", task["id"]),
        )
        await self.daemon.storage.execute(
            """
            INSERT INTO operation_journal (
                task_id, op_id, project_id, tool_id, target_resources_json,
                fingerprint, status, reversible, started_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (task["id"], "op-crash", proj.id, "unity.create_script", "[]", "fp-crash", "Running", 1, "2026-01-01T00:00:00Z"),
        )
        await self.daemon.stop()

        # Boot a brand-new NexusDaemon against the same SQLite DB
        restarted = NexusDaemon(self.config)
        await restarted.start(start_network=False)
        try:
            self.assertEqual(len(restarted.recovered_interrupted_tasks), 1)
            self.assertEqual(restarted.recovered_interrupted_tasks[0]["taskId"], task["id"])
            health = await restarted.health()
            self.assertEqual(health["recoveredInterruptedTasks"], 1)

            recovered_task = await restarted.tasks.get_task(task["id"])
            self.assertEqual(recovered_task["status"], NexusStatus.UNAVAILABLE.value)
            self.assertIn("Daemon restart recovery", "\n".join(recovered_task["logs"]))

            recovery_info = await restarted.tasks.get_task_recovery_details(task["id"])
            self.assertEqual(recovery_info["operationJournal"][0]["status"], "Interrupted")
            self.assertEqual(
                recovery_info["operationJournal"][0]["errorCode"],
                "DAEMON_RESTART_INTERRUPTED",
            )
        finally:
            await restarted.stop()

    async def test_unity_and_godot_test_projects_integrity(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        unity_tp = repo_root / "adapters" / "unity" / "test_project"
        self.assertTrue((unity_tp / "ProjectSettings" / "ProjectVersion.txt").is_file())
        manifest_data = json.loads((unity_tp / "Packages" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest_data["dependencies"].get("com.nexus.bridge"), "file:../..")
        self.assertTrue((unity_tp / "Assets" / "Scenes" / "Main.unity").is_file())
        self.assertTrue((unity_tp / "Assets" / "Scripts" / "TestActor.cs").is_file())

        godot_tp = repo_root / "adapters" / "godot" / "test_project"
        self.assertTrue((godot_tp / "project.godot").is_file())
        self.assertTrue((godot_tp / "scenes" / "main.tscn").is_file())
        self.assertTrue((godot_tp / "scripts" / "test_actor.gd").is_file())
        self.assertTrue((godot_tp / "addons" / "nexus_bridge" / "nexus_godot_handlers.gd").is_file())

    async def test_performance_concurrent_rest_and_sqlite_throughput(self) -> None:
        proj = await self.daemon.projects.register_project(
            name="PerfProject",
            engine="Godot",
            root_path=str(self.tmp_root),
            require_existing_dir=True,
        )
        t0 = time.perf_counter()

        async def _probe_health() -> int:
            st, _ = await dispatch_rest_request(self.daemon, "GET", "/health", {})
            return st

        health_statuses = await asyncio.gather(*[_probe_health() for _ in range(100)])
        self.assertTrue(all(st == 200 for st in health_statuses))

        for i in range(20):
            await self.daemon.tasks.create_task_draft(
                project_id=proj.id,
                title=f"Perf task #{i}",
                priority="normal",
            )
        tasks = await self.daemon.tasks.list_tasks()
        self.assertEqual(len(tasks), 20)

        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 3.0, f"Performance benchmark exceeded 3.0s budget: {elapsed:.3f}s")

    async def test_rest_and_mcp_direct_tool_security_gates_and_fast_ws_shutdown(self) -> None:
        # 1. Start loopback Unity-like adapter exposing assets:modify & delete_object tools
        srv = _DualFileMutationAdapter(project_root=self.unity_proj, engine_kind="Unity")
        port = await srv.start()
        try:
            manifest = {
                "manifestVersion": "1.0",
                "adapterId": "nexus-unity-secgate",
                "displayName": "Security Gate Unity Adapter",
                "version": "1.0.0",
                "runtimeLanguage": "C#",
                "engineKind": "Unity",
                "isTestAdapter": False,
                "protocolVersion": "1.0.0",
                "minDaemonProtocolVersion": "1.0.0",
                "maxDaemonProtocolVersion": "1.99.99",
                "transport": {"kind": "tcp-loopback", "host": "127.0.0.1", "port": port},
                "entrypoint": "NexusUnityAdapter.cs",
                "capabilities": ["script_write", "scene_write", "assets_modify"],
                "requestedPermissions": ["project:read", "script:write", "scene:write", "assets:modify"],
                "supportedEngineVersions": ["2022.3"],
            }
            # Patch srv listTools to include scene, asset, and delete operations.
            orig_dispatch = srv._dispatch

            def _extended_dispatch(method: str, params: dict[str, Any]) -> dict[str, Any]:
                if method == "listTools":
                    res = orig_dispatch(method, params)
                    tools = list(res.get("tools") or [])
                    tools.extend(
                        [
                            {
                                "id": "unity.import_asset",
                                "category": "Asset management",
                                "description": "Import Unity asset.",
                                "requiredPermissions": ["assets:modify"],
                                "inputSchema": {"type": "object"},
                                "outputSchema": {"type": "object"},
                            },
                            {
                                "id": "unity.create_object",
                                "category": "Object management",
                                "description": "Create a GameObject in the active scene.",
                                "requiredPermissions": ["scene:write"],
                                "inputSchema": {"type": "object"},
                                "outputSchema": {"type": "object"},
                            },
                            {
                                "id": "unity.delete_object",
                                "category": "Object management",
                                "description": "Delete GameObject from active scene.",
                                "requiredPermissions": ["scene:write"],
                                "inputSchema": {"type": "object"},
                                "outputSchema": {"type": "object"},
                            },
                        ]
                    )
                    return {"tools": tools}
                return orig_dispatch(method, params)

            srv._dispatch = _extended_dispatch  # type: ignore[method-assign]

            await self.daemon.adapters.install_adapter(manifest)
            await self.daemon.adapters.connect_adapter("nexus-unity-secgate")
            proj = await self.daemon.projects.register_project(
                name="UnitySecGate",
                engine="Unity",
                root_path=str(self.unity_proj),
                require_existing_dir=True,
            )

            # REST /tools/execute blocks unapproved assets:modify -> 403
            st_mod, _ = await dispatch_rest_request(
                self.daemon,
                "POST",
                "/api/v1/adapters/nexus-unity-secgate/tools/execute",
                self.auth_headers,
                json.dumps(
                    {
                        "toolId": "unity.import_asset",
                        "projectId": proj.id,
                        "arguments": {"assetPath": "Assets/Materials/Test.mat"},
                    }
                ).encode("utf-8"),
            )
            self.assertEqual(st_mod, 403)

            # REST /tools/execute blocks unapproved unity.delete_object -> 403
            st_del, _ = await dispatch_rest_request(
                self.daemon,
                "POST",
                "/api/v1/adapters/nexus-unity-secgate/tools/execute",
                self.auth_headers,
                json.dumps(
                    {
                        "toolId": "unity.delete_object",
                        "projectId": proj.id,
                        "arguments": {"path": "Cube"},
                    }
                ).encode("utf-8"),
            )
            self.assertEqual(st_del, 403)

            # REST /tools/execute also blocks non-destructive-looking scene writes.
            st_create, _ = await dispatch_rest_request(
                self.daemon,
                "POST",
                "/api/v1/adapters/nexus-unity-secgate/tools/execute",
                self.auth_headers,
                json.dumps(
                    {
                        "toolId": "unity.create_object",
                        "projectId": proj.id,
                        "arguments": {"name": "UnapprovedObject"},
                    }
                ).encode("utf-8"),
            )
            self.assertEqual(st_create, 403)

            # REST /tools/execute blocks path traversal -> 403
            st_trav, _ = await dispatch_rest_request(
                self.daemon,
                "POST",
                "/api/v1/adapters/nexus-unity-secgate/tools/execute",
                self.auth_headers,
                json.dumps(
                    {
                        "toolId": "unity.create_script",
                        "projectId": proj.id,
                        "arguments": {"path": "../../escape.cs", "content": "// bad"},
                    }
                ).encode("utf-8"),
            )
            self.assertEqual(st_trav, 403)

            # MCP call_tool also blocks path traversal and unapproved unity.delete_object
            with self.assertRaises(PermissionDeniedError):
                await self.daemon.mcp.call_tool(
                    "nexus-unity-secgate.unity.create_script",
                    {"projectId": proj.id, "path": "../../escape.cs", "content": "// bad"},
                )
            with self.assertRaises(ValidationError):
                await self.daemon.mcp.call_tool(
                    "nexus-unity-secgate.unity.delete_object",
                    {"projectId": proj.id, "path": "Cube"},
                )
            with self.assertRaises(ValidationError):
                await self.daemon.mcp.call_tool(
                    "nexus-unity-secgate.unity.create_object",
                    {"projectId": proj.id, "name": "UnapprovedObject"},
                )

            # 2. Live WebSocket connects via ?token= query auth and shuts down in < 1.0s
            import base64

            ws_port = self.daemon.ws_port
            self.assertIsNotNone(ws_port)
            assert ws_port is not None
            reader, writer = await asyncio.open_connection("127.0.0.1", ws_port)
            try:
                ws_key = base64.b64encode(b"nexus-test-ws-01").decode("ascii")
                handshake = (
                    f"GET /events?token={self.token} HTTP/1.1\r\n"
                    f"Host: 127.0.0.1:{ws_port}\r\n"
                    f"Upgrade: websocket\r\n"
                    f"Connection: Upgrade\r\n"
                    f"Sec-WebSocket-Key: {ws_key}\r\n"
                    f"Sec-WebSocket-Version: 13\r\n\r\n"
                ).encode("latin-1")
                writer.write(handshake)
                await writer.drain()
                head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=2.0)
                self.assertIn(b"101 Switching Protocols", head)

                t_stop = time.perf_counter()
                await self.daemon.stop()
                stop_elapsed = time.perf_counter() - t_stop
                self.assertLess(stop_elapsed, 1.0, f"WS shutdown took {stop_elapsed:.3f}s")
            finally:
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()
        finally:
            await srv.stop()

    async def test_http_keepalive_cache_invalidation_and_nonblocking_adapter_rpc(self) -> None:
        rest_port = self.daemon.http_port
        mcp_port = self.daemon.mcp_port
        assert rest_port is not None and mcp_port is not None

        def _exercise_keepalive_sync() -> tuple[int, int, str, str]:
            rest_conn = http.client.HTTPConnection("127.0.0.1", rest_port, timeout=3.0)
            mcp_conn = http.client.HTTPConnection("127.0.0.1", mcp_port, timeout=3.0)
            try:
                rest_conn.request("GET", "/health")
                r1 = rest_conn.getresponse()
                r1.read()
                fd_rest_1 = rest_conn.sock.fileno() if rest_conn.sock else -1
                conn_hdr_rest = (r1.getheader("Connection") or "").lower()

                rest_conn.request("GET", "/api/v1/projects", headers=self.auth_headers)
                r2 = rest_conn.getresponse()
                r2.read()
                fd_rest_2 = rest_conn.sock.fileno() if rest_conn.sock else -2

                self.assertEqual(r1.status, 200)
                self.assertEqual(r2.status, 200)
                self.assertEqual(fd_rest_1, fd_rest_2)

                mcp_headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.token}",
                }
                mcp_conn.request(
                    "POST",
                    "/mcp",
                    body=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
                    headers=mcp_headers,
                )
                m1 = mcp_conn.getresponse()
                m1.read()
                fd_mcp_1 = mcp_conn.sock.fileno() if mcp_conn.sock else -1
                conn_hdr_mcp = (m1.getheader("Connection") or "").lower()

                mcp_conn.request(
                    "POST",
                    "/mcp",
                    body=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
                    headers=mcp_headers,
                )
                m2 = mcp_conn.getresponse()
                m2.read()
                fd_mcp_2 = mcp_conn.sock.fileno() if mcp_conn.sock else -2

                self.assertEqual(m1.status, 200)
                self.assertEqual(m2.status, 200)
                self.assertEqual(fd_mcp_1, fd_mcp_2)
                return fd_rest_1, fd_mcp_1, conn_hdr_rest, conn_hdr_mcp
            finally:
                rest_conn.close()
                mcp_conn.close()

        fd_r, fd_m, hdr_r, hdr_m = await asyncio.to_thread(_exercise_keepalive_sync)
        self.assertGreater(fd_r, 0)
        self.assertGreater(fd_m, 0)
        self.assertEqual(hdr_r, "keep-alive")
        self.assertEqual(hdr_m, "keep-alive")

        # Diagnostics integrity cache hits within TTL and invalidates immediately after a DB write
        orig_integrity = self.daemon.storage.integrity_check
        integrity_calls = 0

        async def _counted_integrity() -> str:
            nonlocal integrity_calls
            integrity_calls += 1
            return await orig_integrity()

        self.daemon.storage.integrity_check = _counted_integrity  # type: ignore[method-assign]
        try:
            await self.daemon.diagnostics.collect()
            await self.daemon.diagnostics.collect()
            self.assertEqual(integrity_calls, 1)

            await self.daemon.projects.register_project(
                name="InvalidateCacheProj",
                engine="Unity",
                root_path=str(self.unity_proj),
                require_existing_dir=True,
            )
            await self.daemon.diagnostics.collect()
            self.assertEqual(integrity_calls, 2)
        finally:
            self.daemon.storage.integrity_check = orig_integrity  # type: ignore[method-assign]

        # Engine binary probe cache hits within TTL and invalidates on executable override change
        from sdk.python.nexus_sdk import EngineKind

        self.daemon.engines._probe_cache.clear()
        with patch("core.nexus_core.engine_manager.shutil.which", return_value=None) as which_mock:
            self.daemon.engines.list_engines()
            calls_after_first = which_mock.call_count
            self.daemon.engines.list_engines()
            self.assertEqual(which_mock.call_count, calls_after_first)
            self.daemon.engines.set_engine_executable_path(EngineKind.UNITY, None)
            self.daemon.engines.list_engines()
            self.assertGreater(which_mock.call_count, calls_after_first)

        # Adapter transport dispatches slow notification callbacks concurrently without blocking RPC replies
        srv = _DualFileMutationAdapter(project_root=self.unity_proj, engine_kind="Unity")
        port = await srv.start()
        try:
            from core.nexus_core.adapters.protocol import TcpLoopbackAdapterTransport

            transport = TcpLoopbackAdapterTransport("127.0.0.1", port)
            events_seen = 0

            async def _slow_event_handler(_payload: dict[str, Any]) -> None:
                nonlocal events_seen
                await asyncio.sleep(0.25)
                events_seen += 1

            transport.set_event_callback(_slow_event_handler)
            await transport.open()
            try:
                for idx in range(5):
                    await transport._dispatch_incoming_line(
                        json.dumps({"jsonrpc": "2.0", "method": "engine.log", "params": {"i": idx}}).encode("utf-8")
                    )
                t_rpc = time.perf_counter()
                health = await transport.call("healthCheck")
                rpc_elapsed = time.perf_counter() - t_rpc
                self.assertTrue(health.get("healthy", True))
                self.assertLess(rpc_elapsed, 0.15)
                await asyncio.sleep(0.3)
                self.assertEqual(events_seen, 5)
            finally:
                await transport.close()
        finally:
            await srv.stop()
