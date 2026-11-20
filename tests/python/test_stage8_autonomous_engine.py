"""Stage 8 Automated Verification: Autonomous Development Engine (16-Phase Workflow, DAG, Gates, Bounded Repairs, Concurrency)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from typing import Any

from core.nexus_core.config import NexusDaemonConfig
from core.nexus_core.daemon import NexusDaemon
from core.nexus_core.errors import ConflictError, PermissionDeniedError, ValidationError


class _LoopbackAutonomousAdapterServer:
    """Real loopback JSON-RPC 2.0 TCP engine adapter that executes disk/scene mutations for testing."""

    def __init__(self, *, project_root: Path, engine_kind: str = "Godot") -> None:
        self.project_root = project_root
        self.engine_kind = engine_kind
        self.server: asyncio.AbstractServer | None = None
        self.port: int = 0
        self.executed_calls: list[dict[str, Any]] = []
        self.clients: list[asyncio.StreamWriter] = []
        self.created_files: dict[str, str] = {}

    async def start(self) -> int:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = int(self.server.sockets[0].getsockname()[1])
        return self.port

    async def stop(self) -> None:
        for w in list(self.clients):
            w.close()
        self.clients.clear()
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.clients.append(writer)
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                msg = json.loads(line.decode("utf-8"))
                req_id = msg.get("id")
                method = str(msg.get("method", ""))
                params = msg.get("params") or {}
                if req_id is None:
                    continue
                try:
                    result = self._dispatch(method, params)
                    resp = {"jsonrpc": "2.0", "id": req_id, "result": result}
                except Exception as exc:  # noqa: BLE001
                    resp = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": str(exc)}}
                writer.write((json.dumps(resp) + "\n").encode("utf-8"))
                await writer.drain()
        except Exception:  # noqa: BLE001
            pass
        finally:
            if writer in self.clients:
                self.clients.remove(writer)
            writer.close()

    def _dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            return {"protocolVersion": "1.0.0", "adapterId": f"test-{self.engine_kind.lower()}-live"}
        if method == "getEngineInfo":
            return {
                "engine": self.engine_kind,
                "engineVersion": "4.3.0-stable" if self.engine_kind == "Godot" else "2022.3.42f1",
                "projectName": self.project_root.name,
                "projectId": "engine-proj-1",
                "activeScene": "res://scenes/main.tscn",
                "isCompiling": False,
            }
        if method == "healthCheck":
            return {"status": "Connected", "mainThreadResponsive": True, "isCompiling": False}
        if method == "getProjectState":
            return {
                "activeScene": "res://scenes/main.tscn",
                "activeScenePath": "res://scenes/main.tscn",
                "isCompiling": False,
                "openFiles": list(self.created_files.keys()),
            }
        if method == "getCapabilities":
            return {
                "engine": self.engine_kind,
                "capabilities": ["scene_inspect", "script_write", "screenshot_capture", "test_run"],
            }
        if method == "listTools":
            prefix = "godot" if self.engine_kind == "Godot" else "unity"
            return {
                "tools": [
                    {
                        "id": f"{prefix}.get_node_hierarchy" if prefix == "godot" else f"{prefix}.get_scene_hierarchy",
                        "category": "Scene Inspection",
                        "description": "Inspect live hierarchy",
                        "requiredPermissions": ["project:read"],
                        "inputSchema": {"type": "object"},
                        "outputSchema": {"type": "object"},
                    },
                    {
                        "id": f"{prefix}.inspect_assets",
                        "category": "Asset Management",
                        "description": "Inspect project assets",
                        "requiredPermissions": ["project:read"],
                        "inputSchema": {"type": "object"},
                        "outputSchema": {"type": "object"},
                    },
                    {
                        "id": f"{prefix}.create_script",
                        "category": "Script Editing",
                        "description": "Create or overwrite engine script",
                        "requiredPermissions": ["script:write"],
                        "inputSchema": {"type": "object"},
                        "outputSchema": {"type": "object"},
                    },
                    {
                        "id": f"{prefix}.modify_asset_protected",
                        "category": "Asset Management",
                        "description": "Protected asset mutation requiring approval",
                        "requiredPermissions": ["assets:modify"],
                        "inputSchema": {"type": "object"},
                        "outputSchema": {"type": "object"},
                    },
                    {
                        "id": f"{prefix}.get_errors",
                        "category": "Diagnostics",
                        "description": "Inspect engine errors",
                        "requiredPermissions": ["project:read"],
                        "inputSchema": {"type": "object"},
                        "outputSchema": {"type": "object"},
                    },
                ]
            }
        if method == "captureScreenshot":
            return {
                "viewport": params.get("viewport", "SceneView"),
                "mimeType": "image/png",
                "width": 1280,
                "height": 720,
                "byteLength": 4096,
                "capturedAt": datetime.now(timezone.utc).isoformat(),
            }
        if method == "executeTool":
            tool_id = str(params.get("toolId", ""))
            args = dict(params.get("arguments") or {})
            self.executed_calls.append({"toolId": tool_id, "arguments": args})

            if tool_id.endswith(".create_script"):
                rel = str(args.get("path", "")).replace("res://", "").lstrip("/")
                target = (self.project_root / rel).resolve()
                if args.get("forceDuplicateFail"):
                    return {"verified": False, "isError": True, "message": "Script compile syntax error"}
                if target.exists() and not args.get("overwrite"):
                    return {"verified": False, "isError": True, "message": "Target script already exists"}
                target.parent.mkdir(parents=True, exist_ok=True)
                content = str(args.get("content", "# generated by NEXUS\n"))
                target.write_text(content, encoding="utf-8")
                self.created_files[rel] = content
                return {"verified": True, "status": "Succeeded", "output": {"writtenPath": rel}}

            if tool_id.endswith(".modify_asset_protected"):
                if not args.get("_approved"):
                    raise RuntimeError("Missing _approved token for protected asset tool")
                rel = str(args.get("assetPath", "")).replace("res://", "").lstrip("/")
                target = (self.project_root / rel).resolve()
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("protected-asset-updated", encoding="utf-8")
                return {"verified": True, "status": "Succeeded", "output": {"assetPath": rel}}

            if tool_id.endswith(".inspect_assets"):
                return {"verified": True, "output": {"assets": [{"path": "scripts/hero.gd"}]}}

            if tool_id.endswith(".get_errors"):
                if args.get("returnErrors"):
                    return {
                        "verified": True,
                        "output": {
                            "errors": ["Compile error in scripts/bad.gd"],
                            "errorCount": 1,
                        },
                    }
                return {"verified": True, "output": {"errors": [], "errorCount": 0}}

            return {"verified": True, "output": {"ok": True}}
        return {"ok": True}


class TestStage8AutonomousEngine(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_root = Path(self.tmp.name).resolve()
        self.data_dir = self.tmp_root / "daemon_data"
        self.proj_a = self.tmp_root / "GodotProjA"
        self.proj_b = self.tmp_root / "GodotProjB"
        self.proj_a.mkdir()
        self.proj_b.mkdir()
        (self.proj_a / "scripts").mkdir()
        (self.proj_a / "scripts" / "existing.gd").write_text("# original\n", encoding="utf-8")

        config = NexusDaemonConfig(
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
        self.daemon = NexusDaemon(config)
        await self.daemon.start(start_network=False)

    async def asyncTearDown(self) -> None:
        await self.daemon.stop()
        self.tmp.cleanup()

    async def _attach_live_adapter(
        self, adapter_id: str, project_root: Path, *, engine_kind: str = "Godot"
    ) -> _LoopbackAutonomousAdapterServer:
        server = _LoopbackAutonomousAdapterServer(project_root=project_root, engine_kind=engine_kind)
        port = await server.start()
        manifest = {
            "manifestVersion": "1.0",
            "adapterId": adapter_id,
            "displayName": f"Live {engine_kind} Adapter",
            "version": "1.0.0",
            "runtimeLanguage": "GDScript" if engine_kind == "Godot" else "C#",
            "engineKind": engine_kind,
            "isTestAdapter": False,
            "protocolVersion": "1.0.0",
            "minDaemonProtocolVersion": "1.0.0",
            "maxDaemonProtocolVersion": "1.99.99",
            "transport": {"kind": "tcp-loopback", "host": "127.0.0.1", "port": port},
            "entrypoint": "plugin.gd",
            "capabilities": ["scene_inspect", "script_write", "screenshot_capture"],
            "requestedPermissions": ["project:read", "script:write", "assets:modify"],
            "supportedEngineVersions": ["4.3"],
        }
        await self.daemon.adapters.install_adapter(manifest)
        await self.daemon.adapters.connect_adapter(adapter_id)
        return server

    async def test_16_phase_workflow_with_repair_screenshot_and_report(self) -> None:
        adapter_srv = await self._attach_live_adapter("nexus-godot-a", self.proj_a)
        try:
            proj = await self.daemon.projects.register_project(
                name="GodotProjA",
                engine="Godot",
                root_path=str(self.proj_a),
                require_existing_dir=True,
            )
            # existing.gd exists -> first create_script fails ("already exists"),
            # Phase 13 repairs it cleanly once by setting overwrite=True!
            task = await self.daemon.tasks.create_task_draft(
                project_id=proj.id,
                title="Update existing script cleanly with verification",
                priority="high",
                agent_id="planner-agent",
                adapter_id="nexus-godot-a",
                operations=[
                    {
                        "opId": "op-write",
                        "title": "Write existing script",
                        "toolId": "godot.create_script",
                        "arguments": {"path": "res://scripts/existing.gd", "content": "# repaired\n"},
                    },
                    {
                        "opId": "op-verify",
                        "title": "Run post-write error check",
                        "toolId": "godot.get_errors",
                        "dependsOn": ["op-write"],
                        "isTest": True,
                    },
                ],
            )
            self.assertEqual(len(task["steps"]), 16)
            executed = await self.daemon.tasks.execute_task(task["id"], adapter_id="nexus-godot-a")
            self.assertEqual(executed["status"], "Connected")
            self.assertEqual(executed["progress"], 100)
            self.assertEqual(executed["report"]["outcome"], "Succeeded")
            self.assertEqual(executed["report"]["repairAttempts"], 1)
            self.assertGreaterEqual(executed["report"]["screenshotsCaptured"], 1)
            self.assertEqual(
                (self.proj_a / "scripts" / "existing.gd").read_text(encoding="utf-8"),
                "# repaired\n",
            )
            self.assertIsNotNone(executed["report"]["fileChangeManifest"])
        finally:
            await adapter_srv.stop()

    async def test_duplicate_failure_prevention_blocks_identical_retry(self) -> None:
        adapter_srv = await self._attach_live_adapter("nexus-godot-dup", self.proj_a)
        try:
            proj = await self.daemon.projects.register_project(
                name="GodotProjDup",
                engine="Godot",
                root_path=str(self.proj_a),
                require_existing_dir=True,
            )
            task = await self.daemon.tasks.create_task_draft(
                project_id=proj.id,
                title="Fail once and never retry identical failed fingerprint",
                adapter_id="nexus-godot-dup",
                operations=[
                    {
                        "opId": "op-broken",
                        "title": "Broken syntax script",
                        "toolId": "godot.create_script",
                        "arguments": {
                            "path": "res://scripts/broken.gd",
                            "forceDuplicateFail": True,
                        },
                    }
                ],
            )
            with self.assertRaises(ValidationError):
                await self.daemon.tasks.execute_task(task["id"], adapter_id="nexus-godot-dup")
            create_calls = [c for c in adapter_srv.executed_calls if c["toolId"] == "godot.create_script"]
            self.assertEqual(len(create_calls), 1)
        finally:
            await adapter_srv.stop()

    async def test_dag_cycle_rejection_and_approval_gate(self) -> None:
        proj = await self.daemon.projects.register_project(
            name="GodotProjDAG",
            engine="Godot",
            root_path=str(self.proj_a),
            require_existing_dir=True,
        )
        with self.assertRaises(ValidationError):
            await self.daemon.tasks.create_task_draft(
                project_id=proj.id,
                title="Cyclic plan rejected",
                operations=[
                    {"opId": "a", "toolId": "godot.get_errors", "dependsOn": ["b"]},
                    {"opId": "b", "toolId": "godot.get_errors", "dependsOn": ["a"]},
                ],
            )

        adapter_srv = await self._attach_live_adapter("nexus-godot-gate", self.proj_a)
        try:
            task = await self.daemon.tasks.create_task_draft(
                project_id=proj.id,
                title="Protected asset edit paused at gate",
                adapter_id="nexus-godot-gate",
                operations=[
                    {
                        "opId": "op-asset",
                        "toolId": "godot.modify_asset_protected",
                        "arguments": {"assetPath": "res://scripts/protected.txt"},
                    }
                ],
            )
            paused = await self.daemon.tasks.execute_task(task["id"], adapter_id="nexus-godot-gate")
            self.assertEqual(paused["status"], "Unavailable")
            self.assertEqual(paused["plan"]["approvalPending"]["requiredScopes"], ["assets:modify"])
            self.assertFalse((self.proj_a / "scripts" / "protected.txt").exists())

            approved = await self.daemon.tasks.approve_task_checkpoint(
                task["id"],
                approved=True,
                adapter_id="nexus-godot-gate",
            )
            self.assertEqual(approved["status"], "Connected")
            self.assertTrue((self.proj_a / "scripts" / "protected.txt").is_file())
        finally:
            await adapter_srv.stop()

    async def test_multi_agent_same_project_conflict_and_multi_project_isolation(self) -> None:
        adapter_a = await self._attach_live_adapter("nexus-godot-pa", self.proj_a)
        try:
            proj_a = await self.daemon.projects.register_project(
                name="ProjA",
                engine="Godot",
                root_path=str(self.proj_a),
                require_existing_dir=True,
            )
            proj_b = await self.daemon.projects.register_project(
                name="ProjB",
                engine="Godot",
                root_path=str(self.proj_b),
                require_existing_dir=True,
            )
            # Manual lock held by rival agent on proj_a collides cleanly with new task on proj_a
            self.daemon.concurrency.acquire_project_lock(proj_a.id, "task-rival", "agent-rival")
            task_a = await self.daemon.tasks.create_task_draft(
                project_id=proj_a.id,
                title="Conflicting task on locked project",
                agent_id="agent-2",
                adapter_id="nexus-godot-pa",
                operations=[{"opId": "op1", "toolId": "godot.get_errors"}],
            )
            with self.assertRaises(ConflictError):
                await self.daemon.tasks.execute_task(task_a["id"], adapter_id="nexus-godot-pa")

            # Different project proj_b succeeds concurrently with zero lock conflict
            task_b = await self.daemon.tasks.create_task_draft(
                project_id=proj_b.id,
                title="Independent project succeeds concurrently",
                agent_id="agent-2",
                adapter_id="nexus-godot-pa",
                operations=[{"opId": "op2", "toolId": "godot.get_errors"}],
            )
            res_b = await self.daemon.tasks.execute_task(task_b["id"], adapter_id="nexus-godot-pa")
            self.assertEqual(res_b["status"], "Connected")
            self.daemon.concurrency.release_project_lock(proj_a.id, "task-rival")
        finally:
            await adapter_a.stop()

    async def test_phase14_rejects_failing_test_output_instead_of_hardcoding_pass(self) -> None:
        adapter_srv = await self._attach_live_adapter("nexus-godot-testfail", self.proj_a)
        try:
            proj = await self.daemon.projects.register_project(
                name="GodotProjTestFail",
                engine="Godot",
                root_path=str(self.proj_a),
                require_existing_dir=True,
            )
            task = await self.daemon.tasks.create_task_draft(
                project_id=proj.id,
                title="Fail honestly when test verification reports errors",
                adapter_id="nexus-godot-testfail",
                operations=[
                    {
                        "opId": "verify-errors",
                        "toolId": "godot.get_errors",
                        "arguments": {"returnErrors": True},
                        "isTest": True,
                    }
                ],
            )
            with self.assertRaises(ValidationError) as ctx:
                await self.daemon.tasks.execute_task(task["id"], adapter_id="nexus-godot-testfail")
            self.assertIn("errorCount=1", ctx.exception.message)
            failed_task = await self.daemon.tasks.get_task(task["id"])
            self.assertEqual(failed_task["status"], "Failed")
            self.assertEqual(failed_task["steps"][13]["status"], "Failed")

            # Also verify diagnostics reflects the live connected Godot adapter
            diag = await self.daemon.diagnostics.collect()
            godot_diag = next(e for e in diag["engines"] if e["engine"] == "Godot")
            self.assertEqual(godot_diag["connection_status"], "Connected")
        finally:
            await adapter_srv.stop()
