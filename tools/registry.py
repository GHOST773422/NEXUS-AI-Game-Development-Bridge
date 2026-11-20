"""NEXUS Dynamic Tool Registry (Python 3.12+ Target)."""

from __future__ import annotations

from sdk.python.nexus_sdk import NexusStatus, ToolContract


class ToolRegistry:
    """Stores only verified tools published by active EngineAdapters."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolContract] = {}

    def register(self, contract: ToolContract) -> None:
        if contract.implementation_status == NexusStatus.PLANNED:
            raise ValueError(f"Cannot register unimplemented tool '{contract.id}' as active.")
        self._tools[contract.id] = contract

    def list_tools(self) -> list[ToolContract]:
        return list(self._tools.values())

    def get(self, tool_id: str) -> ToolContract | None:
        return self._tools.get(tool_id)
