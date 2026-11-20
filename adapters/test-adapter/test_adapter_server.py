"""Explicit Out-of-Process NEXUS Test Adapter (JSON-RPC 2.0 over stdio or TCP loopback).

IMPORTANT:
- This process is an explicit synthetic protocol harness (isTestAdapter=True, engineKind="TestHarness").
- It MUST NEVER masquerade as Unity, Godot, Unreal, or any real game engine.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import sys
from typing import Any
import uuid

# Valid 1x1 transparent PNG bytes encoded as base64 (synthetic screenshot fixture only).
_SYNTHETIC_1X1_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)

_TOOLS: list[dict[str, Any]] = [
    {
        "id": "synthetic_echo",
        "category": "Debugging",
        "description": "[TEST ADAPTER] Echoes structured arguments over the wire protocol.",
        "inputSchema": {"type": "object"},
        "outputSchema": {"type": "object"},
        "requiredPermissions": ["project:read"],
        "executionContext": "BridgeDaemon",
        "isTestAdapterTool": True,
    },
    {
        "id": "synthetic_ping_scene",
        "category": "Scene Management",
        "description": "[TEST ADAPTER] Returns synthetic node tree without accessing any real game engine.",
        "inputSchema": {"type": "object"},
        "outputSchema": {"type": "object"},
        "requiredPermissions": ["project:read"],
        "executionContext": "BridgeDaemon",
        "isTestAdapterTool": True,
    },
]


class SyntheticTestAdapterHandler:
    def __init__(self) -> None:
        self.connected = False
        self.session_id = ""
        self.request_count = 0
        self.subscribed_topics: list[str] = []

    def handle_request(
        self, msg: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        req_id = msg.get("id")
        method = str(msg.get("method", ""))
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        self.request_count += 1

        try:
            result, notification = self._dispatch(method, params)
            response = (
                {"jsonrpc": "2.0", "id": req_id, "result": result}
                if req_id is not None
                else None
            )
            return response, notification
        except KeyError as exc:
            err = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": str(exc)},
            }
            return (err if req_id is not None else None), None
        except ValueError as exc:
            err = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": str(exc)},
            }
            return (err if req_id is not None else None), None

    def _dispatch(
        self, method: str, params: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        now = datetime.now(timezone.utc).isoformat()

        if method == "getEngineInfo":
            return (
                {
                    "adapterId": "nexus.test.protocol_harness",
                    "displayName": "[TEST ADAPTER] Synthetic Protocol Harness",
                    "engineKind": "TestHarness",
                    "engineVersion": "0.0.0-synthetic",
                    "runtimeLanguage": "Python",
                    "protocolVersion": "1.0.0",
                    "isTestAdapter": True,
                    "warning": "SYNTHETIC_TEST_ADAPTER_ONLY_NOT_A_REAL_ENGINE",
                },
                None,
            )

        if method == "discoverProjects":
            roots = params.get("searchRoots") if isinstance(params.get("searchRoots"), list) else []
            return (
                {
                    "isTestAdapter": True,
                    "searchRoots": roots,
                    "projects": [
                        {
                            "id": "synthetic-test-project-01",
                            "name": "[TEST FIXTURE] Synthetic Scene Sandbox",
                            "engine": "TestHarness",
                            "rootPath": "/tmp/nexus-synthetic-test-project",
                            "engineVersion": "0.0.0-synthetic",
                            "isSyntheticTestArtifact": True,
                        }
                    ],
                },
                None,
            )

        if method == "connect":
            self.connected = True
            self.session_id = f"test-session-{uuid.uuid4().hex[:8]}"
            return (
                {
                    "connected": True,
                    "isTestAdapter": True,
                    "sessionId": self.session_id,
                    "protocolVersion": "1.0.0",
                    "timestamp": now,
                },
                None,
            )

        if method == "disconnect":
            self.connected = False
            return ({"disconnected": True, "isTestAdapter": True, "timestamp": now}, None)

        if method == "getCapabilities":
            return (
                {
                    "isTestAdapter": True,
                    "capabilities": [
                        "protocol.echo",
                        "protocol.state_inspection",
                        "protocol.screenshot_stub",
                        "protocol.event_stream",
                    ],
                },
                None,
            )

        if method == "listTools":
            return ({"isTestAdapter": True, "tools": _TOOLS}, None)

        if method == "executeTool":
            tool_id = str(params.get("toolId", ""))
            project_id = str(params.get("projectId", ""))
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            req_id = str(params.get("requestId", ""))
            if not project_id:
                raise ValueError("executeTool requires a non-empty projectId.")
            if tool_id == "synthetic_echo":
                return (
                    {
                        "requestId": req_id,
                        "toolId": tool_id,
                        "projectId": project_id,
                        "status": "Available",
                        "verified": True,
                        "isTestAdapter": True,
                        "isSyntheticTestArtifact": True,
                        "output": {"echo": arguments, "timestamp": now},
                    },
                    None,
                )
            if tool_id == "synthetic_ping_scene":
                return (
                    {
                        "requestId": req_id,
                        "toolId": tool_id,
                        "projectId": project_id,
                        "status": "Available",
                        "verified": True,
                        "isTestAdapter": True,
                        "isSyntheticTestArtifact": True,
                        "output": {"activeScene": "SyntheticTestScene.scene", "nodeCount": 2},
                    },
                    None,
                )
            raise KeyError(f"Unknown test adapter tool '{tool_id}'.")

        if method == "getProjectState":
            project_id = str(params.get("projectId", ""))
            return (
                {
                    "projectId": project_id,
                    "isTestAdapter": True,
                    "isSyntheticTestArtifact": True,
                    "activeScene": "SyntheticTestScene.scene",
                    "nodeCount": 2,
                    "nodes": ["SyntheticRoot", "SyntheticCamera"],
                    "timestamp": now,
                },
                None,
            )

        if method == "subscribeEvents":
            topics = [str(t) for t in (params.get("topics") or [])]
            self.subscribed_topics = topics
            notification = {
                "jsonrpc": "2.0",
                "method": "adapter.event",
                "params": {
                    "topics": topics,
                    "isTestAdapter": True,
                    "isSyntheticTestArtifact": True,
                    "message": "Synthetic protocol harness subscribed.",
                    "timestamp": now,
                },
            }
            return (
                {
                    "subscribed": True,
                    "topics": topics,
                    "isTestAdapter": True,
                },
                notification,
            )

        if method == "captureScreenshot":
            project_id = str(params.get("projectId", ""))
            viewport = str(params.get("viewport", "SceneView"))
            return (
                {
                    "projectId": project_id,
                    "viewport": viewport,
                    "mimeType": "image/png",
                    "width": 1,
                    "height": 1,
                    "capturedAt": now,
                    "isTestAdapter": True,
                    "isSyntheticTestArtifact": True,
                    "dataBase64": _SYNTHETIC_1X1_PNG_B64,
                },
                None,
            )

        if method == "healthCheck":
            return (
                {
                    "responsive": True,
                    "connected": self.connected,
                    "isTestAdapter": True,
                    "sessionId": self.session_id,
                    "uptimeRequests": self.request_count,
                    "timestamp": now,
                },
                None,
            )

        raise KeyError(f"Method '{method}' not supported by test adapter.")


async def run_stdio_loop() -> None:
    handler = SyntheticTestAdapterHandler()
    loop = asyncio.get_running_loop()
    write_lock = asyncio.Lock()

    async def write_frame(payload: dict[str, Any]) -> None:
        line = (json.dumps(payload, ensure_ascii=True) + "\n").encode("utf-8")
        async with write_lock:
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()

    while True:
        raw_line = await loop.run_in_executor(None, sys.stdin.buffer.readline)
        if not raw_line:
            break
        text = raw_line.decode("utf-8", errors="replace").strip()
        if not text:
            continue
        try:
            msg = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict):
            continue
        resp, note = handler.handle_request(msg)
        if resp is not None:
            await write_frame(resp)
        if note is not None:
            await asyncio.sleep(0.01)
            await write_frame(note)


async def run_tcp_server(host: str, port: int) -> None:
    async def handle_client(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        handler = SyntheticTestAdapterHandler()
        write_lock = asyncio.Lock()

        async def send_frame(payload: dict[str, Any]) -> None:
            line = (json.dumps(payload, ensure_ascii=True) + "\n").encode("utf-8")
            async with write_lock:
                writer.write(line)
                await writer.drain()

        try:
            while True:
                raw_line = await reader.readline()
                if not raw_line:
                    break
                text = raw_line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                try:
                    msg = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if not isinstance(msg, dict):
                    continue
                resp, note = handler.handle_request(msg)
                if resp is not None:
                    await send_frame(resp)
                if note is not None:
                    await asyncio.sleep(0.01)
                    await send_frame(note)
        finally:
            writer.close()
            with _suppress_oserror():
                await writer.wait_closed()

    server = await asyncio.start_server(handle_client, host, port)
    actual_port = int(server.sockets[0].getsockname()[1]) if server.sockets else port
    sys.stdout.write(
        json.dumps({"listening": True, "host": host, "port": actual_port}, ensure_ascii=True)
        + "\n"
    )
    sys.stdout.flush()
    async with server:
        await server.serve_forever()


class _suppress_oserror:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        return exc_type is not None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NEXUS Synthetic Test Adapter Server")
    parser.add_argument("--tcp-port", type=int, default=0, help="Run loopback TCP NDJSON server instead of stdio.")
    parser.add_argument("--host", default="127.0.0.1", help="Loopback bind host when --tcp-port is set.")
    parser.add_argument("--tcp", action="store_true", help="Bind an ephemeral loopback TCP port.")
    args = parser.parse_args(argv)

    if args.tcp or args.tcp_port > 0:
        asyncio.run(run_tcp_server(args.host, args.tcp_port))
    else:
        asyncio.run(run_stdio_loop())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
