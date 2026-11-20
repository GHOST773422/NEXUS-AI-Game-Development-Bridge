"""NEXUS Language-Neutral Local Adapter Protocol (JSON-RPC 2.0 over stdio / TCP loopback)."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from collections.abc import Awaitable, Callable
import contextlib
import json
import socket
import sys
from typing import Any
import uuid

from core.nexus_core.errors import AdapterProtocolError

ADAPTER_PROTOCOL_VERSION = "1.0.0"

ADAPTER_REQUIRED_METHODS: tuple[str, ...] = (
    "getEngineInfo",
    "discoverProjects",
    "connect",
    "disconnect",
    "getCapabilities",
    "listTools",
    "executeTool",
    "getProjectState",
    "subscribeEvents",
    "captureScreenshot",
    "healthCheck",
)

EventCallback = Callable[[dict[str, Any]], Awaitable[None]]
DisconnectCallback = Callable[[str], Awaitable[None]]


class JsonRpcAdapterTransport(ABC):
    """Transport abstraction speaking language-neutral JSON-RPC 2.0 NDJSON frames."""

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._event_tasks: set[asyncio.Task[None]] = set()
        self._event_cb: EventCallback | None = None
        self._disconnect_cb: DisconnectCallback | None = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def set_event_callback(self, callback: EventCallback | None) -> None:
        self._event_cb = callback

    def set_disconnect_callback(self, callback: DisconnectCallback | None) -> None:
        self._disconnect_cb = callback

    @abstractmethod
    async def open(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def _send_line(self, line: str) -> None:
        raise NotImplementedError

    async def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        if not self._connected:
            raise AdapterProtocolError(
                f"Cannot invoke '{method}': adapter transport is disconnected.",
                details={"method": method},
            )
        req_id = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[req_id] = future

        frame = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
                "params": params or {},
            },
            separators=(",", ":"),
            ensure_ascii=True,
        )
        try:
            await self._send_line(frame)
            response = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError as exc:
            self._pending.pop(req_id, None)
            raise AdapterProtocolError(
                f"Adapter RPC '{method}' timed out after {timeout:.1f}s.",
                details={"method": method},
            ) from exc

        if "error" in response and response["error"] is not None:
            err = response["error"]
            raise AdapterProtocolError(
                str(err.get("message", f"Adapter RPC error in {method}")),
                details={"method": method, "rpcCode": err.get("code"), "data": err.get("data")},
            )
        result = response.get("result")
        return result if isinstance(result, dict) else {"value": result}

    async def _dispatch_incoming_line(self, raw_line: bytes) -> None:
        text = raw_line.decode("utf-8", errors="replace").strip()
        if not text:
            return
        try:
            msg = json.loads(text)
        except json.JSONDecodeError:
            return
        if not isinstance(msg, dict):
            return

        req_id = msg.get("id")
        if req_id is not None and str(req_id) in self._pending:
            fut = self._pending.pop(str(req_id))
            if not fut.done():
                fut.set_result(msg)
            return

        # Notification frame emitted asynchronously by adapter (e.g. adapter.event / engine.log)
        if "method" in msg and self._event_cb is not None:
            payload = {
                "method": str(msg["method"]),
                "params": msg.get("params") if isinstance(msg.get("params"), dict) else {},
            }
            task = asyncio.create_task(self._run_event_callback(self._event_cb, payload))
            self._event_tasks.add(task)
            task.add_done_callback(self._event_tasks.discard)

    @staticmethod
    async def _run_event_callback(cb: EventCallback, payload: dict[str, Any]) -> None:
        with contextlib.suppress(Exception):
            await cb(payload)

    def _cancel_event_tasks(self) -> None:
        for task in list(self._event_tasks):
            if not task.done():
                task.cancel()
        self._event_tasks.clear()

    def _fail_all_pending(self, reason: str) -> None:
        for req_id, fut in list(self._pending.items()):
            self._pending.pop(req_id, None)
            if not fut.done():
                fut.set_exception(AdapterProtocolError(reason))


class StdioAdapterTransport(JsonRpcAdapterTransport):
    """Spawns a language-neutral local subprocess speaking NDJSON JSON-RPC 2.0 on stdio."""

    def __init__(self, command: list[str], cwd: str | None = None) -> None:
        super().__init__()
        self.command = command
        self.cwd = cwd
        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._closing = False

    def _resolved_command(self) -> list[str]:
        if not self.command:
            return []
        if self.command[0] in {"python", "python3"}:
            return [sys.executable, *self.command[1:]]
        return list(self.command)

    async def open(self) -> None:
        if self._connected:
            return
        self._closing = False
        cmd = self._resolved_command()
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
        )
        self._connected = True
        self._reader_task = asyncio.create_task(self._read_loop())

    async def close(self) -> None:
        self._closing = True
        self._connected = False
        if self._reader_task is not None:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
            self._reader_task = None
        if self._proc is not None:
            if self._proc.stdin and not self._proc.stdin.is_closing():
                self._proc.stdin.close()
            if self._proc.returncode is None:
                self._proc.terminate()
                try:
                    await asyncio.wait_for(self._proc.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    self._proc.kill()
                    await self._proc.wait()
            self._proc = None
        self._cancel_event_tasks()
        self._fail_all_pending("Adapter stdio transport closed.")

    async def _send_line(self, line: str) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise AdapterProtocolError("Adapter stdio process stdin unavailable.")
        self._proc.stdin.write((line + "\n").encode("utf-8"))
        await self._proc.stdin.drain()

    async def _read_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        try:
            while True:
                line = await self._proc.stdout.readline()
                if not line:
                    break
                await self._dispatch_incoming_line(line)
        except asyncio.CancelledError:
            return
        finally:
            self._connected = False
            self._fail_all_pending("Adapter stdio pipe closed unexpectedly.")
            if not self._closing and self._disconnect_cb is not None:
                await self._disconnect_cb("stdio_eof")


class TcpLoopbackAdapterTransport(JsonRpcAdapterTransport):
    """Connects over 127.0.0.1 TCP using NDJSON JSON-RPC 2.0 (C# / GDScript / C++ plugins)."""

    def __init__(self, host: str, port: int) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._closing = False

    async def open(self) -> None:
        if self._connected:
            return
        self._closing = False
        try:
            self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        except OSError as exc:
            raise AdapterProtocolError(
                f"Failed connecting to adapter TCP endpoint {self.host}:{self.port}: {exc}",
                details={"host": self.host, "port": self.port},
            ) from exc
        sock = self._writer.get_extra_info("socket")
        if sock is not None:
            with contextlib.suppress(OSError):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._connected = True
        self._reader_task = asyncio.create_task(self._read_loop())

    async def close(self) -> None:
        self._closing = True
        self._connected = False
        if self._reader_task is not None:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
            self._reader_task = None
        self._cancel_event_tasks()
        if self._writer is not None:
            self._writer.close()
            with contextlib.suppress(Exception):
                await self._writer.wait_closed()
            self._writer = None
        self._reader = None
        self._fail_all_pending("Adapter TCP transport closed.")

    async def _send_line(self, line: str) -> None:
        if self._writer is None:
            raise AdapterProtocolError("Adapter TCP writer unavailable.")
        self._writer.write((line + "\n").encode("utf-8"))
        await self._writer.drain()

    async def _read_loop(self) -> None:
        assert self._reader is not None
        try:
            while True:
                line = await self._reader.readline()
                if not line:
                    break
                await self._dispatch_incoming_line(line)
        except asyncio.CancelledError:
            return
        finally:
            self._connected = False
            self._fail_all_pending("Adapter TCP connection lost.")
            if not self._closing and self._disconnect_cb is not None:
                await self._disconnect_cb("tcp_eof")
