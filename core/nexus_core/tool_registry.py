"""NEXUS Tool Registry (Core Backend Integration)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from core.nexus_core.errors import NotFoundError, ValidationError
from sdk.python.nexus_sdk import NexusStatus, ToolContract

PLANNED_TOOL_CATEGORIES: tuple[str, ...] = (
    "Project management",
    "Scene management",
    "Object management",
    "Component management",
    "Script management",
    "Asset management",
    "Material management",
    "Shader management",
    "Lighting",
    "Physics",
    "Animation",
    "Audio",
    "UI",
    "Navigation",
    "Rendering",
    "Debugging",
    "Testing",
    "Profiling",
    "Build and export",
)


class CoreToolRegistry:
    """Tracks only verified executable tools registered by connected engine adapters."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolContract] = {}

    def register_verified_tool(self, contract: ToolContract) -> None:
        if contract.implementation_status in {NexusStatus.PLANNED, NexusStatus.UNAVAILABLE}:
            raise ValidationError(
                f"Refusing to register unimplemented tool '{contract.id}'.",
                details={"toolId": contract.id, "status": contract.implementation_status.value},
            )
        self._tools[contract.id] = contract

    def unregister_tools_for_prefix(self, prefix: str) -> int:
        keys = [k for k in self._tools if k.startswith(prefix)]
        for k in keys:
            del self._tools[k]
        return len(keys)

    def get_tool(self, tool_id: str) -> ToolContract:
        tool = self._tools.get(tool_id)
        if tool is None:
            raise NotFoundError(
                f"Tool '{tool_id}' is not registered or no engine adapter is connected.",
                details={"toolId": tool_id},
            )
        return tool

    def list_tools(self) -> list[dict[str, Any]]:
        return [asdict(t) for t in self._tools.values()]

    @property
    def verified_count(self) -> int:
        return len(self._tools)
