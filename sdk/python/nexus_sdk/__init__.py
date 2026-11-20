"""NEXUS Shared Python SDK Contracts (Python 3.12+ Target)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable


class NexusStatus(StrEnum):
    CONNECTED = "Connected"
    DISCONNECTED = "Disconnected"
    AVAILABLE = "Available"
    UNAVAILABLE = "Unavailable"
    RUNNING = "Running"
    FAILED = "Failed"
    PLANNED = "Planned"


class EngineKind(StrEnum):
    UNITY = "Unity"
    GODOT = "Godot"


class AIProviderKind(StrEnum):
    GOOGLE_GEMINI = "Google Gemini"
    ANTHROPIC_CLAUDE = "Anthropic Claude"
    OPENAI = "OpenAI"
    OPENAI_COMPATIBLE = "OpenAI-Compatible"
    CUSTOM = "Custom Provider"


class PermissionScope(StrEnum):
    READ_PROJECT = "project:read"
    WRITE_SCENE = "scene:write"
    WRITE_SCRIPT = "script:write"
    MODIFY_ASSETS = "assets:modify"
    EXECUTE_EDITOR_ACTION = "editor:execute"
    RUN_TESTS = "tests:run"
    BUILD_EXPORT = "build:export"
    PROCESS_SPAWN_RESTRICTED = "process:restricted"


@dataclass(slots=True)
class ToolContract:
    id: str
    category: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    engine_compatibility: list[EngineKind]
    required_permissions: list[PermissionScope]
    execution_context: str
    error_handling: str
    implementation_status: NexusStatus = NexusStatus.PLANNED


@dataclass(slots=True)
class EngineHealthReport:
    engine: EngineKind
    project_id: str
    status: NexusStatus
    main_thread_responsive: bool
    is_compiling: bool
    last_heartbeat_at: str
    message: str | None = None


@dataclass(slots=True)
class TaskExecutionStep:
    step_number: int
    name: str
    subsystem: str
    status: NexusStatus = NexusStatus.PLANNED
    gate_required: bool = False
    artifacts: list[str] = field(default_factory=list)


class EngineAdapter(ABC):
    """Abstract base contract for Unity C# and Godot GDScript bridge adapters."""

    engine_kind: EngineKind

    @abstractmethod
    async def detect_engine(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def identify_version(self, project_path: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def discover_projects(self, search_roots: list[str]) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def connect_project(self, project_id: str) -> EngineHealthReport:
        raise NotImplementedError

    @abstractmethod
    async def discover_capabilities(self, project_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def register_tools(self, project_id: str) -> list[ToolContract]:
        raise NotImplementedError

    @abstractmethod
    async def execute_tool(
        self, request_id: str, tool_id: str, project_id: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def inspect_project_state(self, project_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def subscribe_events(self, project_id: str, callback: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
        raise NotImplementedError

    @abstractmethod
    async def capture_screenshot(self, project_id: str, viewport: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def check_health(self, project_id: str) -> EngineHealthReport:
        raise NotImplementedError

    @abstractmethod
    def report_error(self, error: Exception) -> dict[str, str]:
        raise NotImplementedError

    @abstractmethod
    async def disconnect_and_reconnect(self, project_id: str) -> EngineHealthReport:
        raise NotImplementedError
