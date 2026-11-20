"""NEXUS Universal Adapter Interface & Remote JSON-RPC Implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from core.nexus_core.adapters.manifest import AdapterManifest
from core.nexus_core.adapters.protocol import (
    ADAPTER_REQUIRED_METHODS,
    JsonRpcAdapterTransport,
    StdioAdapterTransport,
    TcpLoopbackAdapterTransport,
)


class UniversalEngineAdapter(ABC):
    """Language-neutral adapter contract exposing the 11 canonical lifecycle & tool operations."""

    @abstractmethod
    async def getEngineInfo(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def discoverProjects(self, search_roots: list[str] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def connect(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def disconnect(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def getCapabilities(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def listTools(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def executeTool(
        self,
        tool_id: str,
        project_id: str,
        arguments: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def getProjectState(self, project_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def subscribeEvents(
        self,
        topics: list[str],
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def captureScreenshot(
        self, project_id: str, viewport: str = "SceneView"
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def healthCheck(self) -> dict[str, Any]:
        raise NotImplementedError


def build_transport_for_manifest(
    manifest: AdapterManifest,
    *,
    working_dir_fallback: str | None = None,
) -> JsonRpcAdapterTransport:
    if manifest.transport.kind == "stdio":
        return StdioAdapterTransport(
            command=list(manifest.transport.command),
            cwd=manifest.transport.working_dir or working_dir_fallback,
        )
    return TcpLoopbackAdapterTransport(
        host=manifest.transport.host,
        port=manifest.transport.port,
    )


class ProtocolEngineAdapter(UniversalEngineAdapter):
    """Executes all 11 UniversalEngineAdapter operations over JSON-RPC 2.0 wire transport."""

    def __init__(
        self,
        manifest: AdapterManifest,
        transport: JsonRpcAdapterTransport,
    ) -> None:
        self.manifest = manifest
        self.transport = transport

    @staticmethod
    def required_methods() -> tuple[str, ...]:
        return ADAPTER_REQUIRED_METHODS

    async def open_transport(self) -> None:
        await self.transport.open()

    async def close_transport(self) -> None:
        await self.transport.close()

    async def getEngineInfo(self) -> dict[str, Any]:
        return await self.transport.call("getEngineInfo", {})

    async def discoverProjects(self, search_roots: list[str] | None = None) -> dict[str, Any]:
        return await self.transport.call(
            "discoverProjects", {"searchRoots": search_roots or []}
        )

    async def connect(self) -> dict[str, Any]:
        return await self.transport.call(
            "connect",
            {
                "adapterId": self.manifest.adapter_id,
                "protocolVersion": self.manifest.protocol_version,
            },
        )

    async def disconnect(self) -> dict[str, Any]:
        if not self.transport.is_connected:
            return {"disconnected": True}
        return await self.transport.call("disconnect", {})

    async def getCapabilities(self) -> dict[str, Any]:
        return await self.transport.call("getCapabilities", {})

    async def listTools(self) -> dict[str, Any]:
        return await self.transport.call("listTools", {})

    async def executeTool(
        self,
        tool_id: str,
        project_id: str,
        arguments: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        return await self.transport.call(
            "executeTool",
            {
                "requestId": request_id or "",
                "toolId": tool_id,
                "projectId": project_id,
                "arguments": arguments or {},
            },
        )

    async def getProjectState(self, project_id: str) -> dict[str, Any]:
        return await self.transport.call("getProjectState", {"projectId": project_id})

    async def subscribeEvents(
        self,
        topics: list[str],
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> dict[str, Any]:
        self.transport.set_event_callback(callback)
        return await self.transport.call("subscribeEvents", {"topics": topics})

    async def captureScreenshot(
        self, project_id: str, viewport: str = "SceneView"
    ) -> dict[str, Any]:
        return await self.transport.call(
            "captureScreenshot", {"projectId": project_id, "viewport": viewport}
        )

    async def healthCheck(self) -> dict[str, Any]:
        return await self.transport.call("healthCheck", {})
