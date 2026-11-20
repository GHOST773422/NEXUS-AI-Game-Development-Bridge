"""NEXUS WebSocket Event Service (RFC-6455 Async Loopback + EventManager Bridge)."""

from __future__ import annotations

import asyncio
import base64
import contextlib
from dataclasses import dataclass, field
import hashlib
import json
import socket
import struct
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

from core.nexus_core.errors import AuthenticationError

if TYPE_CHECKING:
    from core.nexus_core.daemon import NexusDaemon
    from core.nexus_core.event_manager import NexusEvent

_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_JSON_SEPARATORS = (",", ":")


@dataclass(slots=True)
class WebSocketServiceConfig:
    host: str = "127.0.0.1"
    port: int = 47101
    heartbeat_interval_sec: int = 15
    topics: list[str] = field(
        default_factory=lambda: [
            "bridge.status",
            "engine.health",
            "engine.log",
            "engine.scene_changed",
            "task.step_updated",
            "error.diagnostic",
        ]
    )


def encode_ws_text_frame(text: str) -> bytes:
    """Encodes a server-to-client unmasked RFC-6455 text frame."""
    payload = text.encode("utf-8")
    length = len(payload)
    if length < 126:
        header = bytes([0x81, length])
    elif length < 65536:
        header = struct.pack("!BBH", 0x81, 126, length)
    else:
        header = struct.pack("!BBQ", 0x81, 127, length)
    return header + payload


def encode_ws_close_frame(code: int = 1001, reason: str = "Server shutting down") -> bytes:
    """Encodes an RFC-6455 Connection Close frame (0x88)."""
    payload = struct.pack("!H", code) + reason.encode("utf-8")[:123]
    return bytes([0x88, len(payload)]) + payload


class WebSocketEventService:
    """Streams real EventManager events to authenticated local WebSocket clients."""

    def __init__(
        self,
        daemon: "NexusDaemon",
        config: WebSocketServiceConfig | None = None,
    ) -> None:
        self.daemon = daemon
        self.config = config or WebSocketServiceConfig()
        self._server: asyncio.AbstractServer | None = None
        self._stop_event: asyncio.Event = asyncio.Event()
        self._active_tasks: set[asyncio.Task[Any]] = set()
        self._active_writers: set[asyncio.StreamWriter] = set()
        self._frame_cache: dict[int, bytes] = {}
        self.bound_port: int | None = None

    def _encode_event_frame(self, event: "NexusEvent") -> bytes:
        cached = self._frame_cache.get(event.sequence)
        if cached is not None:
            return cached
        frame = encode_ws_text_frame(
            json.dumps(event.to_dict(), separators=_JSON_SEPARATORS)
        )
        if len(self._frame_cache) >= 256:
            self._frame_cache.clear()
        self._frame_cache[event.sequence] = frame
        return frame

    async def start(self) -> int:
        self._stop_event.clear()
        self._frame_cache.clear()
        self._server = await asyncio.start_server(
            self._handle_connection, self.config.host, self.config.port
        )
        sockets = self._server.sockets
        if sockets:
            self.bound_port = int(sockets[0].getsockname()[1])
        return self.bound_port or self.config.port

    async def stop(self) -> None:
        self._stop_event.set()
        for writer in list(self._active_writers):
            with contextlib.suppress(Exception):
                writer.write(encode_ws_close_frame())
                writer.close()
        for task in list(self._active_tasks):
            if not task.done():
                task.cancel()
        if self._active_tasks:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(
                    asyncio.gather(*list(self._active_tasks), return_exceptions=True),
                    timeout=0.5,
                )
        self._active_tasks.clear()
        self._active_writers.clear()
        self._frame_cache.clear()
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._server.wait_closed(), timeout=0.5)
            self._server = None

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        current_task = asyncio.current_task()
        if current_task is not None:
            self._active_tasks.add(current_task)
        self._active_writers.add(writer)
        sock = writer.get_extra_info("socket")
        if sock is not None:
            with contextlib.suppress(OSError):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        sub_id: str | None = None
        read_watch_task: asyncio.Task[None] | None = None
        stop_wait_task: asyncio.Task[bool] | None = None
        closed_wait_task: asyncio.Task[bool] | None = None
        get_task: asyncio.Task["NexusEvent"] | None = None
        client_closed = asyncio.Event()
        try:
            raw_head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5.0)
            lines = raw_head.decode("latin-1").split("\r\n")
            target = "/"
            if lines and " " in lines[0]:
                parts = lines[0].split(" ", 2)
                if len(parts) >= 2:
                    target = parts[1]

            headers: dict[str, str] = {}
            for line in lines[1:]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    headers[k.strip().lower()] = v.strip()

            query_params = parse_qs(urlparse(target).query)
            query_token = (query_params.get("token") or [None])[0]

            try:
                if headers.get("authorization"):
                    self.daemon.permissions.validate_bearer_header(headers.get("authorization"))
                elif query_token is not None:
                    self.daemon.permissions.validate_token_string(query_token)
                else:
                    self.daemon.permissions.validate_bearer_header(None)
            except AuthenticationError as exc:
                err_body = json.dumps(exc.to_envelope(), separators=_JSON_SEPARATORS).encode("utf-8")
                writer.write(
                    (
                        f"HTTP/1.1 401 Unauthorized\r\n"
                        f"Content-Type: application/json\r\n"
                        f"Content-Length: {len(err_body)}\r\nConnection: close\r\n\r\n"
                    ).encode("latin-1")
                    + err_body
                )
                await writer.drain()
                return

            ws_key = headers.get("sec-websocket-key", "")
            if not ws_key:
                writer.write(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
                await writer.drain()
                return

            accept_digest = hashlib.sha1((ws_key + _WS_GUID).encode("ascii")).digest()
            accept_key = base64.b64encode(accept_digest).decode("ascii")
            handshake = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept_key}\r\n\r\n"
            ).encode("latin-1")
            writer.write(handshake)
            await writer.drain()

            async def _watch_client_eof() -> None:
                try:
                    while not self._stop_event.is_set():
                        chunk = await reader.read(256)
                        if not chunk:
                            break
                        # Handle client WebSocket Close opcode (0x08)
                        if (chunk[0] & 0x0F) == 0x08:
                            break
                except Exception:
                    pass
                finally:
                    client_closed.set()

            read_watch_task = asyncio.create_task(_watch_client_eof())
            sub_id, queue = await self.daemon.events.subscribe(max_queue_size=512)
            welcome: dict[str, Any] = {
                "type": "bridge.status",
                "data": {"status": "Connected", "topics": self.config.topics},
            }
            writer.write(encode_ws_text_frame(json.dumps(welcome, separators=_JSON_SEPARATORS)))
            await writer.drain()

            stop_wait_task = asyncio.create_task(self._stop_event.wait())
            closed_wait_task = asyncio.create_task(client_closed.wait())
            heartbeat = float(self.config.heartbeat_interval_sec)

            while (
                not self.daemon.stop_requested
                and not self._stop_event.is_set()
                and not client_closed.is_set()
            ):
                if queue.empty():
                    get_task = asyncio.create_task(queue.get())
                    done, _ = await asyncio.wait(
                        {get_task, stop_wait_task, closed_wait_task},
                        timeout=heartbeat,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if (
                        self._stop_event.is_set()
                        or self.daemon.stop_requested
                        or client_closed.is_set()
                    ):
                        if not get_task.done():
                            get_task.cancel()
                        break
                    if get_task not in done:
                        get_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await get_task
                        get_task = None
                        # Heartbeat WebSocket Ping frame (0x89, length 0)
                        writer.write(b"\x89\x00")
                        await writer.drain()
                        continue
                    first_event = get_task.result()
                    get_task = None
                else:
                    first_event = queue.get_nowait()

                frames = [self._encode_event_frame(first_event)]
                while len(frames) < 64:
                    try:
                        nxt = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    frames.append(self._encode_event_frame(nxt))
                writer.write(frames[0] if len(frames) == 1 else b"".join(frames))
                await writer.drain()
        except Exception:
            pass
        finally:
            for t in (get_task, stop_wait_task, closed_wait_task, read_watch_task):
                if t is not None and not t.done():
                    t.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await t
            if sub_id is not None:
                await self.daemon.events.unsubscribe(sub_id)
            self._active_writers.discard(writer)
            if current_task is not None:
                self._active_tasks.discard(current_task)
            writer.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(writer.wait_closed(), timeout=0.2)
