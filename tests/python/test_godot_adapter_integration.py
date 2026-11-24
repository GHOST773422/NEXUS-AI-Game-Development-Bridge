"""Stage 7 Godot 4.x GDScript Adapter contract, test project, version compatibility, recovery & MCP routing tests."""

from __future__ import annotations

import asyncio
import configparser
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from core.nexus_core.adapters import parse_adapter_manifest, validate_adapter_compatibility
from core.nexus_core.config import NexusDaemonConfig
from core.nexus_core.daemon import NexusDaemon
from core.nexus_core.errors import AdapterCompatibilityError, ValidationError
from core.nexus_core.tool_registry import PLANNED_TOOL_CATEGORIES
from sdk.python.nexus_sdk import NexusStatus, PermissionScope

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GODOT_ROOT = _REPO_ROOT / "adapters" / "godot"
_ADDON_DIR = _GODOT_ROOT / "addons" / "nexus_bridge"
_TEST_PROJECT_DIR = _GODOT_ROOT / "test_project"
_TEST_ADDON_DIR = _TEST_PROJECT_DIR / "addons" / "nexus_bridge"


def _extract_godot_tools(registry_gd: str) -> list[tuple[str, str, str]]:
    pattern = re.compile(
        r'_make_tool\(\s*"(?P<id>godot\.[^"]+)"\s*,\s*"(?P<cat>[^"]+)"\s*,\s*"[^"]+"\s*,\s*\["(?P<perm>[^"]+)"\]',
        re.MULTILINE,
    )
    return [(m.group("id"), m.group("cat"), m.group("perm")) for m in pattern.finditer(registry_gd)]


def _verify_gd_delimiter_balance(text: str) -> tuple[int, int, int, int, int, int]:
    """Counts (), [], {} outside GDScript comments and string literals."""
    p_open = p_close = b_open = b_close = c_open = c_close = 0
    i = 0
    n = len(text)
    in_line_comment = False
    quote_char: str | None = None
    while i < n:
        ch = text[i]
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if quote_char is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote_char:
                quote_char = None
            i += 1
            continue
        if ch == "#":
            in_line_comment = True
            i += 1
            continue
        if ch in {'"', "'"}:
            quote_char = ch
            i += 1
            continue
        if ch == "(":
            p_open += 1
        elif ch == ")":
            p_close += 1
        elif ch == "[":
            b_open += 1
        elif ch == "]":
            b_close += 1
        elif ch == "{":
            c_open += 1
        elif ch == "}":
            c_close += 1
        i += 1
    return p_open, p_close, b_open, b_close, c_open, c_close


class _LoopbackGodotProtocolServer:
    """Lightweight protocol harness modeling Godot EditorPlugin loopback TCP JSON-RPC 2.0 responses."""

    def __init__(
        self,
        *,
        project_id: str,
        project_name: str,
        godot_version: str = "4.3.0.stable",
        compatible: bool = True,
    ) -> None:
        self.project_id = project_id
        self.project_name = project_name
        self.godot_version = godot_version
        self.compatible = compatible
        self.server: asyncio.AbstractServer | None = None
        self.port: int = 0
        self.executed_calls: list[dict] = []
        self._writers: list[asyncio.StreamWriter] = []

    async def start(self, port: int = 0) -> int:
        self.server = await asyncio.start_server(self._handle_client, "127.0.0.1", port)
        sock = self.server.sockets[0]
        self.port = int(sock.getsockname()[1])
        return self.port

    async def stop(self) -> None:
        for w in list(self._writers):
            w.close()
        self._writers.clear()
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._writers.append(writer)
        try:
            while not reader.at_eof():
                line = await reader.readline()
                if not line:
                    break
                msg = json.loads(line.decode("utf-8"))
                req_id = msg.get("id")
                method = msg.get("method")
                params = msg.get("params") or {}

                result: object
                if method == "connect":
                    result = {
                        "connected": True,
                        "isTestAdapter": False,
                        "projectId": self.project_id,
                        "godotVersion": self.godot_version,
                        "compatible": self.compatible,
                    }
                elif method == "getEngineInfo":
                    result = {
                        "adapterId": "nexus.godot.gdscript_editor",
                        "engineKind": "Godot",
                        "engineVersion": self.godot_version,
                        "compatible": self.compatible,
                        "compatibilityReasons": (
                            [] if self.compatible else [f"Godot {self.godot_version} is below 4.2.0"]
                        ),
                        "isTestAdapter": False,
                        "projectId": self.project_id,
                        "projectName": self.project_name,
                        "listenerPort": self.port,
                    }
                elif method == "discoverProjects":
                    result = {
                        "isTestAdapter": False,
                        "projects": [
                            {
                                "id": self.project_id,
                                "name": self.project_name,
                                "engine": "Godot",
                                "rootPath": f"C:/GodotProjects/{self.project_name}",
                                "engineVersion": self.godot_version,
                                "listenerPort": self.port,
                            }
                        ],
                    }
                elif method == "getCapabilities":
                    result = {
                        "isTestAdapter": False,
                        "compatible": self.compatible,
                        "capabilities": [
                            "engine.info",
                            "project.discover",
                            "scene.inspect",
                            "node.create",
                            "resource.manage",
                            "debugger.inspect",
                            "screenshot.capture",
                            "export.status",
                        ],
                    }
                elif method == "listTools":
                    result = {
                        "isTestAdapter": False,
                        "compatible": self.compatible,
                        "tools": [
                            {
                                "id": "godot.inspect_assets",
                                "category": "Asset management",
                                "description": "Inspect EditorFileSystem assets.",
                                "requiredPermissions": ["project:read"],
                                "inputSchema": {"type": "object", "properties": {}},
                                "outputSchema": {"type": "object"},
                            },
                            {
                                "id": "godot.manage_resource",
                                "category": "Asset management",
                                "description": "Create or edit .tres/.res resource.",
                                "requiredPermissions": ["assets:modify"],
                                "inputSchema": {"type": "object", "properties": {}},
                                "outputSchema": {"type": "object"},
                            },
                            {
                                "id": "godot.capture_screenshot",
                                "category": "Rendering",
                                "description": "Capture viewport PNG.",
                                "requiredPermissions": ["editor:execute"],
                                "inputSchema": {"type": "object", "properties": {}},
                                "outputSchema": {"type": "object"},
                            },
                        ],
                    }
                elif method == "getProjectState":
                    result = {
                        "projectId": self.project_id,
                        "projectName": self.project_name,
                        "godotVersion": self.godot_version,
                        "activeScenePath": "res://scenes/main.tscn",
                    }
                elif method == "subscribeEvents":
                    result = {"subscribed": True, "topics": params.get("topics", []), "isTestAdapter": False}
                elif method == "healthCheck":
                    result = {"responsive": True, "connected": True, "isTestAdapter": False}
                elif method == "captureScreenshot":
                    result = {"projectId": self.project_id, "mimeType": "image/png", "isTestAdapter": False}
                elif method == "executeTool":
                    self.executed_calls.append(params)
                    result = {
                        "requestId": params.get("requestId", ""),
                        "toolId": params.get("toolId", ""),
                        "projectId": self.project_id,
                        "status": "Available",
                        "verified": True,
                        "isTestAdapter": False,
                        "output": {
                            "handledBy": self.project_id,
                            "arguments": params.get("arguments", {}),
                        },
                    }
                elif method == "disconnect":
                    result = {"disconnected": True}
                else:
                    result = {}

                if req_id is not None:
                    writer.write((json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}) + "\n").encode("utf-8"))
                    await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()


class TestGodotAdapterIntegration(unittest.IsolatedAsyncioTestCase):
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

    async def test_godot_plugin_manifest_gdscript_integrity_and_test_project_sync(self) -> None:
        manifest_raw = json.loads((_GODOT_ROOT / "nexus-adapter.manifest.json").read_text(encoding="utf-8"))
        manifest = parse_adapter_manifest(manifest_raw)
        validate_adapter_compatibility(manifest, base_dir=_REPO_ROOT)

        self.assertFalse(manifest.is_test_adapter)
        self.assertEqual(manifest.runtime_language, "GDScript")
        self.assertEqual(manifest.engine_kind, "Godot")
        self.assertIn("4.2", manifest.supported_engine_versions)
        self.assertGreaterEqual(len(manifest.capabilities), 20)

        plugin_cfg = configparser.ConfigParser()
        plugin_cfg.read(_ADDON_DIR / "plugin.cfg", encoding="utf-8")
        self.assertEqual(plugin_cfg.get("plugin", "script").strip('"'), "plugin.gd")
        self.assertEqual(plugin_cfg.get("plugin", "version").strip('"'), "1.0.0")

        gd_files = sorted(_ADDON_DIR.glob("*.gd"))
        self.assertGreaterEqual(len(gd_files), 8)
        all_source = ""
        preload_re = re.compile(r'preload\(\s*"res://addons/nexus_bridge/([^"]+)"\s*\)')

        for gd in gd_files:
            content = gd.read_text(encoding="utf-8")
            all_source += f"\n# {gd.name}\n{content}"
            po, pc, bo, bc, co, cc = _verify_gd_delimiter_balance(content)
            self.assertEqual(po, pc, f"Unbalanced () in {gd.name}: {po} != {pc}")
            self.assertEqual(bo, bc, f"Unbalanced [] in {gd.name}: {bo} != {bc}")
            self.assertEqual(co, cc, f"Unbalanced {{}} in {gd.name}: {co} != {cc}")

            for rel in preload_re.findall(content):
                self.assertTrue(
                    (_ADDON_DIR / rel).is_file(),
                    f"Broken preload reference res://addons/nexus_bridge/{rel} in {gd.name}",
                )

            # Verify test_project addon mirror stays byte-for-byte synced
            mirrored = _TEST_ADDON_DIR / gd.name
            self.assertTrue(mirrored.is_file(), f"Missing synced addon file: {mirrored}")
            self.assertEqual(content, mirrored.read_text(encoding="utf-8"))

        for required_api in (
            "extends EditorPlugin",
            "EditorInterface.",
            "get_undo_redo()",
            "extends EditorDebuggerPlugin",
            "extends EditorExportPlugin",
            "TCPServer.new()",
            "Engine.get_version_info()",
            "ClassDB.instantiate(",
            "ResourceLoader.load(",
            "ResourceSaver.save(",
            "Viewport",
            "ConfigFile.new()",
        ):
            self.assertIn(required_api, all_source, f"Expected native Godot API '{required_api}'")

        tools = _extract_godot_tools((_ADDON_DIR / "nexus_tool_registry.gd").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(tools), 18)
        valid_scopes = {s.value for s in PermissionScope}
        for tool_id, category, perm in tools:
            self.assertTrue(tool_id.startswith("godot."), tool_id)
            self.assertIn(category, PLANNED_TOOL_CATEGORIES, f"{tool_id} invalid category {category}")
            self.assertIn(perm, valid_scopes, f"{tool_id} invalid permission {perm}")
            self.assertIn(perm, manifest.requested_permissions)

        # Validate real Godot 4.x test project files
        project_godot = (_TEST_PROJECT_DIR / "project.godot").read_text(encoding="utf-8")
        self.assertIn("config_version=5", project_godot)
        self.assertIn("res://addons/nexus_bridge/plugin.cfg", project_godot)
        self.assertIn("res://scenes/main.tscn", project_godot)

        main_tscn = (_TEST_PROJECT_DIR / "scenes" / "main.tscn").read_text(encoding="utf-8")
        self.assertIn("[gd_scene", main_tscn)
        self.assertIn('node name="TestActor"', main_tscn)

        actor_gd = (_TEST_PROJECT_DIR / "scripts" / "test_actor.gd").read_text(encoding="utf-8")
        self.assertIn("signal status_changed", actor_gd)

        export_cfg = (_TEST_PROJECT_DIR / "export_presets.cfg").read_text(encoding="utf-8")
        self.assertIn("Windows Desktop", export_cfg)

        verify_gd = (_TEST_PROJECT_DIR / "tests" / "nexus_godot_verification.gd").read_text(encoding="utf-8")
        self.assertIn("NEXUS_GODOT_VERIFICATION_PASSED", verify_gd)

    def test_native_godot_verification_and_editor_plugin_load_when_available(self) -> None:
        godot = shutil.which("godot4") or shutil.which("godot")
        if godot is None:
            self.skipTest("Godot 4.2+ is not installed; native editor validation is optional.")

        version = subprocess.run(
            [godot, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        version_match = re.match(r"(\d+)\.(\d+)", version.stdout.strip())
        if (
            version.returncode != 0
            or version_match is None
            or int(version_match.group(1)) != 4
            or int(version_match.group(2)) < 2
        ):
            self.skipTest(f"Godot 4.2+ is required; found {version.stdout.strip()!r}.")

        with tempfile.TemporaryDirectory(prefix="nexus-godot-verification-") as temp_dir:
            project_dir = Path(temp_dir) / "test_project"
            shutil.copytree(
                _TEST_PROJECT_DIR,
                project_dir,
                ignore=shutil.ignore_patterns(".godot", "*.uid"),
            )

            verification = subprocess.run(
                [
                    godot,
                    "--headless",
                    "--path",
                    str(project_dir),
                    "--script",
                    "res://tests/nexus_godot_verification.gd",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            verification_output = verification.stdout + verification.stderr
            self.assertEqual(verification.returncode, 0, verification_output)
            self.assertIn("NEXUS_GODOT_VERIFICATION_PASSED", verification_output)

            editor_load = subprocess.Popen(
                [godot, "--headless", "--editor", "--path", str(project_dir)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            forced_stop = False
            try:
                editor_output, _ = editor_load.communicate(timeout=20)
            except subprocess.TimeoutExpired:
                # A headless editor remains open after plugin startup, like the GUI editor.
                forced_stop = True
                editor_load.terminate()
                try:
                    editor_output, _ = editor_load.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    editor_load.kill()
                    editor_output, _ = editor_load.communicate(timeout=5)

            self.assertIn("first_scan_filesystem: end", editor_output)
            if not forced_stop:
                self.assertEqual(editor_load.returncode, 0, editor_output)
            for error_marker in ("SCRIPT ERROR:", "Parse Error:", "Compile Error:", "Failed to load script"):
                self.assertNotIn(error_marker, editor_output, editor_output)

    async def test_rejects_incompatible_godot_version_without_fake_connection(self) -> None:
        legacy_server = _LoopbackGodotProtocolServer(
            project_id="godot-legacy41",
            project_name="Legacy41Project",
            godot_version="4.1.3.stable",
            compatible=False,
        )
        port = await legacy_server.start()
        try:
            manifest = {
                "manifestVersion": "1.0",
                "adapterId": "nexus.godot.legacy_check",
                "displayName": "Legacy Godot Check",
                "version": "1.0.0",
                "runtimeLanguage": "GDScript",
                "engineKind": "Godot",
                "isTestAdapter": False,
                "protocolVersion": "1.0.0",
                "minDaemonProtocolVersion": "1.0.0",
                "maxDaemonProtocolVersion": "1.99.99",
                "transport": {"kind": "tcp-loopback", "host": "127.0.0.1", "port": port},
                "entrypoint": "adapters/godot/addons/nexus_bridge/plugin.gd",
                "capabilities": ["engine.info"],
                "requestedPermissions": ["project:read"],
                "supportedEngineVersions": ["4.2", "4.3"],
            }
            await self.daemon.adapters.install_adapter(manifest, base_dir=_REPO_ROOT)
            with self.assertRaises(AdapterCompatibilityError):
                await self.daemon.adapters.connect_adapter("nexus.godot.legacy_check")

            health = await self.daemon.health()
            self.assertEqual(health["connectedEngineCount"], 0)
            self.assertEqual(self.daemon.tools.verified_count, 0)
        finally:
            await legacy_server.stop()

    async def test_multi_project_godot_sessions_recovery_and_mcp_routing(self) -> None:
        server_a = _LoopbackGodotProtocolServer(project_id="godot-projA", project_name="GodotProjA")
        server_b = _LoopbackGodotProtocolServer(project_id="godot-projB", project_name="GodotProjB")
        port_a = await server_a.start()
        port_b = await server_b.start()

        try:
            base_manifest = json.loads(
                (_GODOT_ROOT / "nexus-adapter.manifest.json").read_text(encoding="utf-8")
            )
            manifest_a = {
                **base_manifest,
                "adapterId": "nexus.godot.proj_a",
                "displayName": "Godot Project A",
                "transport": {"kind": "tcp-loopback", "host": "127.0.0.1", "port": port_a},
            }
            manifest_b = {
                **base_manifest,
                "adapterId": "nexus.godot.proj_b",
                "displayName": "Godot Project B",
                "transport": {"kind": "tcp-loopback", "host": "127.0.0.1", "port": port_b},
            }

            await self.daemon.adapters.install_adapter(manifest_a, base_dir=_REPO_ROOT)
            await self.daemon.adapters.install_adapter(manifest_b, base_dir=_REPO_ROOT)
            await self.daemon.adapters.connect_adapter("nexus.godot.proj_a")
            await self.daemon.adapters.connect_adapter("nexus.godot.proj_b")

            # Live EngineManager reflects both real Godot editors cleanly
            health = await self.daemon.health()
            self.assertEqual(health["connectedEngineCount"], 2)
            self.assertEqual(health["registeredToolCount"], 6)
            engines = self.daemon.engines.list_engines(
                connected_adapters=self.daemon.adapters.list_adapters()
            )
            godot_summary = next(e for e in engines if e.engine == "Godot")
            self.assertEqual(godot_summary.connection_status, NexusStatus.CONNECTED.value)
            self.assertEqual(godot_summary.verified_capability_count, 6)

            # MCP tool listing & guarded execution
            mcp_names = {t["name"] for t in self.daemon.mcp.list_tools()}
            self.assertIn("nexus.godot.proj_a.godot.inspect_assets", mcp_names)
            self.assertIn("nexus.godot.proj_b.godot.manage_resource", mcp_names)

            read_res = await self.daemon.mcp.call_tool(
                "nexus.godot.proj_a.godot.inspect_assets", {"folder": "res://"}
            )
            self.assertFalse(read_res["isError"])
            self.assertIn("godot-projA", read_res["content"][0]["text"])

            # PermissionDenied/ValidationError when assets:modify tool lacks _approved=True
            with self.assertRaises(ValidationError):
                await self.daemon.mcp.call_tool(
                    "nexus.godot.proj_b.godot.manage_resource",
                    {"action": "create", "resourcePath": "res://mat.tres"},
                )

            approved = await self.daemon.mcp.call_tool(
                "nexus.godot.proj_b.godot.manage_resource",
                {"action": "create", "resourcePath": "res://mat.tres", "_approved": True},
            )
            self.assertFalse(approved["isError"])
            self.assertEqual(server_b.executed_calls[-1]["toolId"], "godot.manage_resource")

            # Simulate socket interruption + connection recovery on Project A
            await server_a.stop()
            await asyncio.sleep(0.03)
            await server_a.start(port=port_a)
            recovered = False
            for _ in range(30):
                rec = self.daemon.adapters.get_record("nexus.godot.proj_a")
                if rec.lifecycle_state.value == "Connected":
                    recovered = True
                    break
                await asyncio.sleep(0.05)
            self.assertTrue(recovered, "Project A Godot adapter failed to recover after socket restart.")

            await self.daemon.adapters.disconnect_adapter("nexus.godot.proj_a")
            await self.daemon.adapters.disconnect_adapter("nexus.godot.proj_b")
            health_after = await self.daemon.health()
            self.assertEqual(health_after["connectedEngineCount"], 0)
            engines_after = self.daemon.engines.list_engines(
                connected_adapters=self.daemon.adapters.list_adapters()
            )
            godot_after = next(e for e in engines_after if e.engine == "Godot")
            self.assertEqual(godot_after.connection_status, NexusStatus.DISCONNECTED.value)
        finally:
            await server_a.stop()
            await server_b.stop()
