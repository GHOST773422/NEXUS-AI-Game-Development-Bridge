"""NEXUS Dynamic Capability Discovery Service."""

from __future__ import annotations

import platform
import sys
from typing import TYPE_CHECKING, Any

from core.nexus_core.engine_manager import EngineManager
from core.nexus_core.project_registry import ProjectRegistry
from core.nexus_core.storage import SQLiteStorageManager
from core.nexus_core.tool_registry import PLANNED_TOOL_CATEGORIES, CoreToolRegistry
from sdk.python.nexus_sdk import NexusStatus

if TYPE_CHECKING:
    from core.nexus_core.adapters import AdapterManager


class CapabilityDiscoveryService:
    """Reports real runtime capabilities of the Python daemon and connected adapters."""

    def __init__(
        self,
        *,
        storage: SQLiteStorageManager,
        projects: ProjectRegistry,
        engines: EngineManager,
        tools: CoreToolRegistry,
        adapters: "AdapterManager | None" = None,
    ) -> None:
        self.storage = storage
        self.projects = projects
        self.engines = engines
        self.tools = tools
        self.adapters = adapters

    async def discover(self) -> dict[str, Any]:
        project_list = await self.projects.list_projects()
        adapter_list = self.adapters.list_adapters() if self.adapters else []
        engine_list = self.engines.list_engines(connected_adapters=adapter_list)
        real_adapter_count = (
            self.adapters.connected_real_engine_count() if self.adapters else 0
        )
        payload: dict[str, Any] = {
            "daemonStatus": NexusStatus.RUNNING.value,
            "pythonVersion": sys.version.split()[0],
            "os": platform.system(),
            "platform": platform.platform(),
            "sqliteInitialized": self.storage.is_initialized,
            "registeredProjectCount": len(project_list),
            "connectedEngineCount": self.engines.connected_adapter_count + real_adapter_count,
            "engines": [e.to_dict() for e in engine_list],
            "registeredToolCount": self.tools.verified_count,
            "plannedCategoryCount": len(PLANNED_TOOL_CATEGORIES),
            "plannedCategories": list(PLANNED_TOOL_CATEGORIES),
        }
        if self.adapters is not None:
            payload["adapters"] = {
                "installed": self.adapters.list_adapters(),
                "capabilities": self.adapters.capabilities.summary(),
                "connectedTestAdaptersCount": self.adapters.connected_test_adapter_count(),
            }
        return payload
