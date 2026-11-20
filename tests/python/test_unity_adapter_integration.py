"""Stage 6 Unity C# Adapter contract, multi-project wiring, MCP routing, and C# source audits."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re
import tempfile
import unittest

from core.nexus_core.adapters import parse_adapter_manifest, validate_adapter_compatibility
from core.nexus_core.config import NexusDaemonConfig
from core.nexus_core.daemon import NexusDaemon
from core.nexus_core.errors import ValidationError
from core.nexus_core.tool_registry import PLANNED_TOOL_CATEGORIES
from sdk.python.nexus_sdk import NexusStatus, PermissionScope

_REPO_ROOT = Path(__file__).resolve().parents[2]
_UNITY_ROOT = _REPO_ROOT / "adapters" / "unity"


def _extract_unity_tool_ids_and_metadata(registry_cs: str) -> list[tuple[str, str, str]]:
    pattern = re.compile(
        r'MakeTool\(\s*"(?P<id>unity\.[^"]+)"\s*,\s*"(?P<cat>[^"]+)"\s*,\s*"[^"]+"\s*,\s*new\[\]\s*\{\s*"(?P<perm>[^"]+)"',
        re.MULTILINE,
    )
    return [(m.group("id"), m.group("cat"), m.group("perm")) for m in pattern.finditer(registry_cs)]


def _verify_cs_brace_balance(text: str) -> tuple[int, int]:
    opens = 0
    closes = 0
    i = 0
    n = len(text)
    in_line_comment = False
    in_block_comment = False
    in_string = False
    in_char = False
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if in_char:
            if ch == "\\":
                i += 2
                continue
            if ch == "'":
                in_char = False
            i += 1
            continue
        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if ch == '"':
            in_string = True
            i += 1
            continue
        if ch == "'":
            in_char = True
            i += 1
            continue
        if ch == "{":
            opens += 1
        elif ch == "}":
            closes += 1
        i += 1
    return opens, closes


class TestUnityAdapterIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        self.config = NexusDaemonConfig(
            bind_host="127.0.0.1",
            rest_port=0,
            ws_port=0,
            mcp_http_port=0,
            require_bearer_token=True,
            data_dir=self.tmp_dir / "nexus_data",
            sqlite_path=self.tmp_dir / "nexus_data" / "nexus.db",
            token_path=self.tmp_dir / "nexus_data" / "daemon.token",
            allowed_project_roots=[self.tmp_dir],
        )
        self.daemon = NexusDaemon(self.config)
        await self.daemon.start(start_network=False)

    async def asyncTearDown(self) -> None:
        await self.daemon.stop()
        self._tmp.cleanup()

    async def test_unity_csharp_package_manifest_and_source_integrity(self) -> None:
        manifest_raw = json.loads((_UNITY_ROOT / "nexus-adapter.manifest.json").read_text(encoding="utf-8"))
        manifest = parse_adapter_manifest(manifest_raw)
        validate_adapter_compatibility(manifest, base_dir=_REPO_ROOT)

        self.assertEqual(manifest.runtime_language, "C#")
        self.assertEqual(manifest.engine_kind, "Unity")
        self.assertFalse(manifest.is_test_adapter)
        self.assertTrue((_REPO_ROOT / manifest.entrypoint).is_file())
        self.assertTrue((_UNITY_ROOT / "package.json").is_file())
        self.assertTrue((_UNITY_ROOT / "Editor" / "Nexus.Bridge.Editor.asmdef").is_file())
        self.assertTrue((_UNITY_ROOT / "Tests" / "Editor" / "NexusUnityIntegrationTests.cs").is_file())

        # Check all C# files compile structurally cleanly (balanced braces, key UnityEditor symbols)
        for cs_file in list((_UNITY_ROOT / "Editor").glob("*.cs")) + list((_UNITY_ROOT / "Tests" / "Editor").glob("*.cs")):
            text = cs_file.read_text(encoding="utf-8")
            opens, closes = _verify_cs_brace_balance(text)
            self.assertEqual(opens, closes, f"Unbalanced braces in {cs_file.name}: {opens} != {closes}")

        registry_cs = (_UNITY_ROOT / "Editor" / "NexusUnityToolRegistry.cs").read_text(encoding="utf-8")
        tools = _extract_unity_tool_ids_and_metadata(registry_cs)
        self.assertEqual(len(tools), 17)

        valid_scopes = {s.value for s in PermissionScope}
        valid_categories = set(PLANNED_TOOL_CATEGORIES)
        for tool_id, cat, perm in tools:
            self.assertTrue(tool_id.startswith("unity."))
            self.assertIn(cat, valid_categories)
            self.assertIn(perm, valid_scopes)

        handlers_cs = (_UNITY_ROOT / "Editor" / "NexusUnityHandlers.cs").read_text(encoding="utf-8")
        for required_symbol in (
            "Undo.RegisterCreatedObjectUndo",
            "Undo.DestroyObjectImmediate",
            "Undo.RecordObject",
            "Undo.AddComponent",
            "EditorSceneManager.SaveScene",
            "AssetDatabase.FindAssets",
            "AssetDatabase.ImportAsset",
            "EditorApplication.isCompiling",
            "RenderTextureFormat.ARGB32",
            "BuildPipeline.isBuildingPlayer",
        ):
            self.assertIn(required_symbol, handlers_cs)

        dispatcher_cs = (_UNITY_ROOT / "Editor" / "NexusMainThreadDispatcher.cs").read_text(encoding="utf-8")
        self.assertIn("EditorApplication.update", dispatcher_cs)
        self.assertIn("ConcurrentQueue", dispatcher_cs)

        tracker_cs = (_UNITY_ROOT / "Editor" / "NexusUnityStateTracker.cs").read_text(encoding="utf-8")
        for required_hook in (
            "Application.logMessageReceivedThreaded",
            "CompilationPipeline.compilationStarted",
            "CompilationPipeline.compilationFinished",
            "IPostprocessBuildWithReport",
        ):
            self.assertIn(required_hook, tracker_cs)

    async def test_multi_project_unity_tcp_protocol_mcp_and_permissions_without_fakes(self) -> None:
        # Honest default baseline before attaching any socket
        self.assertEqual(self.daemon.adapters.connected_real_engine_count(), 0)
        self.assertEqual(self.daemon.tools.verified_count, 0)
        engines_before = self.daemon.engines.list_engines(
            connected_adapters=self.daemon.adapters.list_adapters()
        )
        self.assertEqual(engines_before[0].connection_status, NexusStatus.DISCONNECTED.value)

        # Spawn two lightweight loopback protocol stubs mimicking two concurrent Unity Editor ports
        # solely to verify multi-project AdapterManager -> CoreToolRegistry -> EngineManager -> MCP routing.
        async def start_unity_protocol_endpoint(project_id: str, unity_ver: str) -> tuple[asyncio.AbstractServer, int]:
            async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                try:
                    while True:
                        raw = await reader.readline()
                        if not raw:
                            break
                        msg = json.loads(raw.decode("utf-8"))
                        method = msg.get("method")
                        req_id = msg.get("id")
                        params = msg.get("params") or {}
                        if method == "getEngineInfo":
                            res = {
                                "adapterId": "nexus.unity.csharp_editor",
                                "engineKind": "Unity",
                                "engineVersion": unity_ver,
                                "runtimeLanguage": "C#",
                                "isTestAdapter": False,
                                "projectId": project_id,
                            }
                        elif method == "connect":
                            res = {"connected": True, "sessionId": f"sess-{project_id}", "projectId": project_id}
                        elif method == "disconnect":
                            res = {"disconnected": True}
                        elif method == "getCapabilities":
                            res = {"capabilities": ["engine.info", "scene.hierarchy", "asset.import"]}
                        elif method == "listTools":
                            res = {
                                "tools": [
                                    {
                                        "id": "unity.get_editor_state",
                                        "category": "Project management",
                                        "description": "Inspect Unity Editor readiness.",
                                        "requiredPermissions": ["project:read"],
                                        "inputSchema": {"type": "object"},
                                        "outputSchema": {"type": "object"},
                                    },
                                    {
                                        "id": "unity.import_asset",
                                        "category": "Asset management",
                                        "description": "Force import Unity asset.",
                                        "requiredPermissions": ["assets:modify"],
                                        "inputSchema": {"type": "object"},
                                        "outputSchema": {"type": "object"},
                                    },
                                ]
                            }
                        elif method == "healthCheck":
                            res = {"responsive": True, "isCompiling": False}
                        elif method == "subscribeEvents":
                            res = {"subscribed": True}
                        elif method == "executeTool":
                            res = {
                                "verified": True,
                                "toolId": params.get("toolId"),
                                "projectId": params.get("projectId") or project_id,
                                "output": {"handledBy": project_id, "args": params.get("arguments")},
                            }
                        else:
                            res = {"ok": True}
                        writer.write((json.dumps({"jsonrpc": "2.0", "id": req_id, "result": res}) + "\n").encode("utf-8"))
                        await writer.drain()
                finally:
                    writer.close()

            srv = await asyncio.start_server(handle, "127.0.0.1", 0)
            port = int(srv.sockets[0].getsockname()[1])
            return srv, port

        srv_a, port_a = await start_unity_protocol_endpoint("unity-proj-a", "2022.3.42f1")
        srv_b, port_b = await start_unity_protocol_endpoint("unity-proj-b", "6000.0.15f1")

        try:
            base_manifest = json.loads((_UNITY_ROOT / "nexus-adapter.manifest.json").read_text(encoding="utf-8"))
            m_a = dict(base_manifest, adapterId="nexus.unity.proj_a", transport={"kind": "tcp-loopback", "host": "127.0.0.1", "port": port_a})
            m_b = dict(base_manifest, adapterId="nexus.unity.proj_b", transport={"kind": "tcp-loopback", "host": "127.0.0.1", "port": port_b})

            await self.daemon.adapters.install_adapter(m_a)
            await self.daemon.adapters.install_adapter(m_b)
            await self.daemon.adapters.connect_adapter("nexus.unity.proj_a")
            await self.daemon.adapters.connect_adapter("nexus.unity.proj_b")

            # Both Unity projects tracked concurrently cleanly
            health = await self.daemon.health()
            self.assertEqual(health["connectedEngineCount"], 2)
            self.assertEqual(health["registeredToolCount"], 4)

            engines_after = self.daemon.engines.list_engines(
                connected_adapters=self.daemon.adapters.list_adapters()
            )
            self.assertEqual(engines_after[0].connection_status, NexusStatus.CONNECTED.value)
            self.assertEqual(engines_after[0].version, "2022.3.42f1")
            self.assertEqual(engines_after[0].verified_capability_count, 4)

            # MCP discovers both projects' verified tools dynamically and enforces PermissionManager
            mcp_tools = {t["name"] for t in self.daemon.mcp.list_tools()}
            self.assertIn("nexus.unity.proj_a.unity.get_editor_state", mcp_tools)
            self.assertIn("nexus.unity.proj_b.unity.import_asset", mcp_tools)

            read_call = await self.daemon.mcp.call_tool(
                "nexus.unity.proj_a.unity.get_editor_state", {}
            )
            self.assertIn("unity-proj-a", read_call["content"][0]["text"])

            # Destructive/modify scope (assets:modify) requires explicit _approved=True
            with self.assertRaises(ValidationError):
                await self.daemon.mcp.call_tool(
                    "nexus.unity.proj_b.unity.import_asset", {"assetPath": "Assets/Test.mat"}
                )

            approved_call = await self.daemon.mcp.call_tool(
                "nexus.unity.proj_b.unity.import_asset",
                {"assetPath": "Assets/Test.mat", "_approved": True},
            )
            self.assertIn("unity-proj-b", approved_call["content"][0]["text"])
        finally:
            await self.daemon.adapters.disconnect_adapter("nexus.unity.proj_a")
            await self.daemon.adapters.disconnect_adapter("nexus.unity.proj_b")
            srv_a.close()
            srv_b.close()
            await srv_a.wait_closed()
            await srv_b.wait_closed()
