"""Automated Stage 5 tests for NEXUS Universal Engine Adapter Framework & Wire Protocol."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from core.nexus_core.adapters import (
    ADAPTER_REQUIRED_METHODS,
    AdapterLifecycleState,
    ReconnectionPolicy,
    parse_adapter_manifest,
    validate_adapter_compatibility,
)
from core.nexus_core.config import NexusDaemonConfig
from core.nexus_core.daemon import NexusDaemon
from core.nexus_core.errors import AdapterCompatibilityError, ValidationError
from core.nexus_core.rest_gateway import dispatch_rest_request


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_manifest_json(rel_path: str) -> dict:
    return json.loads((_REPO_ROOT / rel_path).read_text(encoding="utf-8"))


class UniversalAdapterFrameworkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.config = NexusDaemonConfig(
            bind_host="127.0.0.1",
            rest_port=0,
            ws_port=0,
            mcp_http_port=0,
            require_bearer_token=True,
            data_dir=self.base_dir / "nexus_data",
            sqlite_path=self.base_dir / "nexus_data" / "nexus.db",
            token_path=self.base_dir / "nexus_data" / "daemon.token",
            allowed_project_roots=[self.base_dir],
        )
        self.daemon = NexusDaemon(self.config)
        self.daemon.adapters.reconnection_policy = ReconnectionPolicy(
            auto_reconnect=True,
            max_attempts=3,
            base_delay_seconds=0.05,
            backoff_multiplier=1.5,
            max_delay_seconds=0.2,
        )
        await self.daemon.start(start_network=False)

    async def asyncTearDown(self) -> None:
        await self.daemon.stop()
        self.temp_dir.cleanup()

    async def test_native_language_and_test_manifests_validate(self) -> None:
        for rel in (
            "adapters/unity/nexus-adapter.manifest.json",
            "adapters/godot/nexus-adapter.manifest.json",
            "adapters/cpp/nexus-adapter.manifest.json",
            "adapters/test-adapter/nexus-adapter.manifest.json",
        ):
            manifest = parse_adapter_manifest(_load_manifest_json(rel))
            validate_adapter_compatibility(manifest, base_dir=_REPO_ROOT)

        self.assertEqual(len(ADAPTER_REQUIRED_METHODS), 11)

    async def test_manifest_compatibility_rejects_unsafe_or_dishonest_specs(self) -> None:
        base_manifest = _load_manifest_json("adapters/unity/nexus-adapter.manifest.json")

        bad_version = dict(base_manifest, manifestVersion="2.0")
        with self.assertRaises(AdapterCompatibilityError):
            validate_adapter_compatibility(parse_adapter_manifest(bad_version))

        bad_proto = dict(base_manifest, protocolVersion="2.0.0")
        with self.assertRaises(AdapterCompatibilityError):
            validate_adapter_compatibility(parse_adapter_manifest(bad_proto))

        bad_range = dict(base_manifest, minDaemonProtocolVersion="1.9.0")
        with self.assertRaises(AdapterCompatibilityError):
            validate_adapter_compatibility(parse_adapter_manifest(bad_range))

        bad_host = dict(
            base_manifest,
            transport={"kind": "tcp-loopback", "host": "0.0.0.0", "port": 47201},
        )
        with self.assertRaises(AdapterCompatibilityError):
            validate_adapter_compatibility(parse_adapter_manifest(bad_host))

        bad_perm = dict(base_manifest, requestedPermissions=["kernel:root"])
        with self.assertRaises(AdapterCompatibilityError):
            validate_adapter_compatibility(parse_adapter_manifest(bad_perm))

        dishonest_harness = dict(
            _load_manifest_json("adapters/test-adapter/nexus-adapter.manifest.json"),
            isTestAdapter=False,
        )
        with self.assertRaises(AdapterCompatibilityError):
            parse_adapter_manifest(dishonest_harness)

        test_claiming_unity = dict(
            _load_manifest_json("adapters/test-adapter/nexus-adapter.manifest.json"),
            engineKind="Unity",
            isTestAdapter=True,
        )
        with self.assertRaises(AdapterCompatibilityError):
            validate_adapter_compatibility(parse_adapter_manifest(test_claiming_unity))

        bad_checksum = dict(
            _load_manifest_json("adapters/test-adapter/nexus-adapter.manifest.json"),
            checksumSha256="0" * 64,
        )
        with self.assertRaises(AdapterCompatibilityError):
            validate_adapter_compatibility(
                parse_adapter_manifest(bad_checksum), base_dir=_REPO_ROOT
            )

        # Matching SHA-256 succeeds
        entrypoint_bytes = (_REPO_ROOT / "adapters/test-adapter/test_adapter_server.py").read_bytes()
        good_checksum = dict(
            _load_manifest_json("adapters/test-adapter/nexus-adapter.manifest.json"),
            checksumSha256=hashlib.sha256(entrypoint_bytes).hexdigest(),
        )
        validate_adapter_compatibility(parse_adapter_manifest(good_checksum), base_dir=_REPO_ROOT)

    async def test_stdio_test_adapter_protocol_and_strict_isolation(self) -> None:
        raw = _load_manifest_json("adapters/test-adapter/nexus-adapter.manifest.json")
        installed = await self.daemon.adapters.install_adapter(raw, base_dir=_REPO_ROOT)
        self.assertEqual(installed["lifecycleState"], AdapterLifecycleState.VALIDATED.value)
        self.assertTrue(installed["isTestAdapter"])

        connected = await self.daemon.adapters.connect_adapter(installed["adapterId"])
        self.assertEqual(connected["lifecycleState"], AdapterLifecycleState.CONNECTED.value)
        self.assertEqual(connected["engineInfo"]["isTestAdapter"], True)
        self.assertEqual(connected["engineInfo"]["engineKind"], "TestHarness")

        # Strict isolation: Test Adapter MUST NEVER count as a real engine or register real tools
        health = await self.daemon.health()
        self.assertEqual(health["connectedEngineCount"], 0)
        self.assertEqual(health["connectedTestAdaptersCount"], 1)
        self.assertEqual(health["installedAdaptersCount"], 1)
        self.assertEqual(health["registeredToolCount"], 0)
        self.assertEqual(self.daemon.tools.verified_count, 0)

        tools = self.daemon.adapters.list_tools_for_adapter(installed["adapterId"])
        self.assertEqual([t["id"] for t in tools], ["synthetic_echo", "synthetic_ping_scene"])

        discovered = await self.daemon.adapters.discover_projects(
            installed["adapterId"], [str(self.base_dir)]
        )
        self.assertTrue(discovered["isTestAdapter"])
        self.assertEqual(discovered["projects"][0]["id"], "synthetic-test-project-01")

        exec_res = await self.daemon.adapters.execute_tool(
            installed["adapterId"],
            "synthetic_echo",
            "synthetic-test-project-01",
            {"ping": "pong"},
        )
        self.assertTrue(exec_res["verified"])
        self.assertTrue(exec_res["isSyntheticTestArtifact"])
        self.assertEqual(exec_res["output"]["echo"], {"ping": "pong"})

        state = await self.daemon.adapters.get_project_state(
            installed["adapterId"], "synthetic-test-project-01"
        )
        self.assertEqual(state["activeScene"], "SyntheticTestScene.scene")

        shot = await self.daemon.adapters.capture_screenshot(
            installed["adapterId"], "synthetic-test-project-01", "SceneView"
        )
        self.assertEqual(shot["mimeType"], "image/png")
        self.assertTrue(shot["isSyntheticTestArtifact"])

        hb = await self.daemon.adapters.health_check_adapter(installed["adapterId"])
        self.assertEqual(hb["lifecycleState"], AdapterLifecycleState.CONNECTED.value)
        self.assertTrue(hb["health"]["responsive"])

        # Async notification emitted on subscribeEvents must arrive in daemon EventManager
        await asyncio.sleep(0.08)
        recent = self.daemon.events.recent_events(limit=20)
        self.assertTrue(
            any(
                e["source"] == f"adapter:{installed['adapterId']}"
                and e["data"].get("isSyntheticTestArtifact") is True
                for e in recent
            )
        )

        # Install persists across daemon restart
        await self.daemon.stop()
        restarted = NexusDaemon(self.config)
        await restarted.start(start_network=False)
        try:
            restored = restarted.adapters.list_adapters()
            self.assertEqual(len(restored), 1)
            self.assertEqual(restored[0]["adapterId"], installed["adapterId"])
            await restarted.adapters.uninstall_adapter(installed["adapterId"])
            self.assertEqual(restarted.adapters.list_adapters(), [])
        finally:
            await restarted.stop()

    async def test_tcp_loopback_test_adapter_transport_and_rest_api(self) -> None:
        # Start standalone out-of-process Test Adapter in --tcp mode (language-neutral C#/GDScript/C++ equivalent)
        server_proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "adapters/test-adapter/test_adapter_server.py",
            "--tcp",
            "--host",
            "127.0.0.1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(_REPO_ROOT),
        )
        try:
            assert server_proc.stdout is not None
            ready_line = await asyncio.wait_for(server_proc.stdout.readline(), timeout=5.0)
            ready = json.loads(ready_line.decode("utf-8"))
            tcp_port = int(ready["port"])

            tcp_manifest = {
                "manifestVersion": "1.0",
                "adapterId": "nexus.test.tcp_harness",
                "displayName": "[TEST ADAPTER] TCP Loopback Harness",
                "version": "1.0.0",
                "runtimeLanguage": "Other",
                "engineKind": "TestHarness",
                "isTestAdapter": True,
                "protocolVersion": "1.0.0",
                "transport": {
                    "kind": "tcp-loopback",
                    "host": "127.0.0.1",
                    "port": tcp_port,
                },
                "entrypoint": "adapters/test-adapter/test_adapter_server.py",
                "requestedPermissions": ["project:read"],
            }
            token = self.daemon.config.get_or_create_api_token()
            headers = {"authorization": f"Bearer {token}"}

            status, body = await dispatch_rest_request(
                self.daemon,
                "POST",
                "/api/v1/adapters/install",
                headers,
                json.dumps({"manifest": tcp_manifest}).encode("utf-8"),
            )
            self.assertEqual(status, 201)
            self.assertEqual(body["adapter"]["transportKind"], "tcp-loopback")

            status, body = await dispatch_rest_request(
                self.daemon,
                "POST",
                "/api/v1/adapters/nexus.test.tcp_harness/connect",
                headers,
            )
            self.assertEqual(status, 200)
            self.assertEqual(body["adapter"]["lifecycleState"], "Connected")

            status, body = await dispatch_rest_request(
                self.daemon,
                "POST",
                "/api/v1/adapters/nexus.test.tcp_harness/tools/execute",
                headers,
                json.dumps(
                    {
                        "toolId": "synthetic_ping_scene",
                        "projectId": "synthetic-test-project-01",
                        "arguments": {},
                    }
                ).encode("utf-8"),
            )
            self.assertEqual(status, 200)
            self.assertEqual(body["result"]["output"]["activeScene"], "SyntheticTestScene.scene")

            status, body = await dispatch_rest_request(
                self.daemon,
                "GET",
                "/api/v1/adapters",
                headers,
            )
            self.assertEqual(status, 200)
            self.assertEqual(len(body["capabilities"]["realEngineAdapters"]), 0)
            self.assertEqual(len(body["capabilities"]["testHarnessAdapters"]), 1)

            status, body = await dispatch_rest_request(
                self.daemon,
                "DELETE",
                "/api/v1/adapters/nexus.test.tcp_harness",
                headers,
            )
            self.assertEqual(status, 200)
            self.assertTrue(body["uninstalled"])
        finally:
            server_proc.terminate()
            await server_proc.wait()

    async def test_unexpected_disconnect_triggers_automatic_reconnection(self) -> None:
        raw = _load_manifest_json("adapters/test-adapter/nexus-adapter.manifest.json")
        await self.daemon.adapters.install_adapter(raw, base_dir=_REPO_ROOT)
        adapter_id = raw["adapterId"]
        await self.daemon.adapters.connect_adapter(adapter_id)

        record = self.daemon.adapters.get_record(adapter_id)
        assert record.client is not None
        # Kill underlying stdio child process unexpectedly to exercise reconnection manager
        transport = record.client.transport
        proc = getattr(transport, "_proc", None)
        assert proc is not None
        proc.kill()
        await proc.wait()

        # Poll briefly until auto-reconnect brings the adapter back to Connected
        for _ in range(40):
            if record.lifecycle_state == AdapterLifecycleState.CONNECTED and record.client is not None:
                new_proc = getattr(record.client.transport, "_proc", None)
                if new_proc is not None and new_proc.pid != proc.pid:
                    break
            await asyncio.sleep(0.05)

        self.assertEqual(record.lifecycle_state, AdapterLifecycleState.CONNECTED)
        errors = self.daemon.adapters.list_errors()
        self.assertTrue(any(e["code"] == "NEXUS_ADAPTER_DISCONNECTED" for e in errors))

    async def test_reconnection_exhaustion_transitions_to_failed(self) -> None:
        bad_tcp = {
            "manifestVersion": "1.0",
            "adapterId": "nexus.test.unreachable_tcp",
            "displayName": "[TEST ADAPTER] Unreachable Endpoint",
            "version": "1.0.0",
            "runtimeLanguage": "C++",
            "engineKind": "TestHarness",
            "isTestAdapter": True,
            "protocolVersion": "1.0.0",
            "transport": {"kind": "tcp-loopback", "host": "127.0.0.1", "port": 49998},
            "entrypoint": "adapters/cpp/src/missing.cpp",
            "requestedPermissions": ["project:read"],
        }
        await self.daemon.adapters.install_adapter(bad_tcp)
        record = self.daemon.adapters.get_record("nexus.test.unreachable_tcp")
        with self.assertRaises(Exception):
            await self.daemon.adapters.connect_adapter("nexus.test.unreachable_tcp")
        self.assertEqual(record.lifecycle_state, AdapterLifecycleState.FAILED)
        with self.assertRaises(ValidationError):
            await self.daemon.adapters.execute_tool(
                "nexus.test.unreachable_tcp", "synthetic_echo", "p1", {}
            )
