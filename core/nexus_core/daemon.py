"""NEXUS Independent Background Daemon Manager."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
import platform
import signal
from typing import Any

from core.nexus_core.adapters import AdapterManager
from core.nexus_core.capability_discovery import CapabilityDiscoveryService
from core.nexus_core.checkpoints import CheckpointManager
from core.nexus_core.concurrency import MultiAgentCoordinator
from core.nexus_core.config import APP_VERSION, NexusDaemonConfig
from core.nexus_core.diagnostics import DiagnosticsService
from core.nexus_core.engine_manager import EngineManager
from core.nexus_core.event_manager import EventManager
from core.nexus_core.logging_config import configure_structured_logging
from core.nexus_core.mcp_server import MCPStreamableHttpServer, NexusMCPServer
from core.nexus_core.orchestrator import AutonomousOrchestrator
from core.nexus_core.project_registry import ProjectRegistry
from core.nexus_core.providers import AIProviderManager, CredentialStore
from core.nexus_core.rest_gateway import StdlibLoopbackHttpServer
from core.nexus_core.security import PermissionManager
from core.nexus_core.storage import SQLiteStorageManager
from core.nexus_core.task_manager import TaskManager
from core.nexus_core.tool_registry import CoreToolRegistry
from integrations.websocket.service import WebSocketEventService, WebSocketServiceConfig
from sdk.python.nexus_sdk import NexusStatus


class NexusDaemon:
    """Coordinates all 12 NEXUS Core backend subsystems independently of any GUI."""

    def __init__(self, config: NexusDaemonConfig | None = None) -> None:
        self.config = config or NexusDaemonConfig.from_env()
        self.logger = configure_structured_logging(
            level=self.config.log_level,
            log_file=self.config.log_file,
        )

        self.storage = SQLiteStorageManager(self.config.sqlite_path)
        self.vault = CredentialStore(vault_path=self.config.data_dir / "secrets.vault.json")
        self.events = EventManager()
        self.providers = AIProviderManager(
            storage=self.storage,
            vault=self.vault,
            events=self.events,
        )
        self.permissions = PermissionManager(
            allowed_roots=self.config.allowed_project_roots,
            require_auth=self.config.require_bearer_token,
        )
        self.projects = ProjectRegistry(
            storage=self.storage,
            permissions=self.permissions,
            events=self.events,
        )
        self.engines = EngineManager()
        self.tools = CoreToolRegistry()
        self.adapters = AdapterManager(
            storage=self.storage,
            permissions=self.permissions,
            events=self.events,
            tool_registry=self.tools,
        )
        self.capabilities = CapabilityDiscoveryService(
            storage=self.storage,
            projects=self.projects,
            engines=self.engines,
            tools=self.tools,
            adapters=self.adapters,
        )
        self.concurrency = MultiAgentCoordinator()
        self.checkpoints = CheckpointManager(
            checkpoints_dir=self.config.data_dir / "checkpoints",
            storage=self.storage,
            permissions=self.permissions,
        )
        self.orchestrator = AutonomousOrchestrator(
            adapters=self.adapters,
            permissions=self.permissions,
            checkpoints=self.checkpoints,
            concurrency=self.concurrency,
            events=self.events,
            storage=self.storage,
        )
        self.tasks = TaskManager(
            storage=self.storage,
            projects=self.projects,
            events=self.events,
            orchestrator=self.orchestrator,
        )
        self.mcp = NexusMCPServer(self)

        self.started_at: str | None = None
        self.diagnostics = DiagnosticsService(
            config=self.config,
            storage=self.storage,
            projects=self.projects,
            engines=self.engines,
            adapters=self.adapters,
            started_at=self.started_at,
        )

        self._http_server: StdlibLoopbackHttpServer | None = None
        self._ws_server: WebSocketEventService | None = None
        self._mcp_http_server: MCPStreamableHttpServer | None = None
        self._stop_event: asyncio.Event | None = None
        self._running = False
        self.stop_requested = False
        self.recovered_interrupted_tasks: list[dict[str, Any]] = []

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def http_port(self) -> int | None:
        return self._http_server.bound_port if self._http_server else None

    @property
    def ws_port(self) -> int | None:
        return self._ws_server.bound_port if self._ws_server else None

    @property
    def mcp_port(self) -> int | None:
        return self._mcp_http_server.bound_port if self._mcp_http_server else None

    async def start(self, *, start_network: bool = True) -> None:
        if self._running:
            return

        self.stop_requested = False
        self._stop_event = asyncio.Event()
        self.permissions.assert_loopback_bind(self.config.bind_host)
        self.config.ensure_data_dir()
        token = self.config.get_or_create_api_token()
        self.permissions.set_api_token(token)

        await self.storage.initialize()
        await self.providers.seed_defaults()
        await self.adapters.restore_from_storage()
        self.recovered_interrupted_tasks = await self.tasks.recover_interrupted_tasks()
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.diagnostics.started_at = self.started_at

        if start_network:
            self._http_server = StdlibLoopbackHttpServer(
                self, self.config.bind_host, self.config.rest_port
            )
            bound_http = await self._http_server.start()

            self._ws_server = WebSocketEventService(
                self,
                WebSocketServiceConfig(
                    host=self.config.bind_host,
                    port=self.config.ws_port,
                ),
            )
            bound_ws = await self._ws_server.start()

            self._mcp_http_server = MCPStreamableHttpServer(
                self.mcp,
                host=self.config.bind_host,
                port=self.config.mcp_http_port,
            )
            bound_mcp = await self._mcp_http_server.start()

            self.logger.info(
                "Loopback gateways started",
                extra={
                    "event": "daemon.network_started",
                    "extra_data": {
                        "bindHost": self.config.bind_host,
                        "restPort": bound_http,
                        "wsPort": bound_ws,
                        "mcpHttpPort": bound_mcp,
                    },
                },
            )

        self._running = True
        await self.storage.record_audit("daemon", "daemon.start", "success")
        await self.events.publish(
            "bridge.status",
            "daemon",
            {"status": NexusStatus.RUNNING.value, "pid": os.getpid()},
        )
        self.logger.info(
            "NEXUS core daemon started",
            extra={"event": "daemon.started", "extra_data": {"pid": os.getpid()}},
        )

    def request_shutdown(self) -> None:
        self.stop_requested = True
        if self._stop_event is not None:
            self._stop_event.set()

    async def stop(self) -> None:
        if not self._running and not self.storage.is_initialized:
            return

        self.stop_requested = True
        await self.adapters.stop_all()
        await self.events.publish(
            "bridge.status",
            "daemon",
            {"status": NexusStatus.DISCONNECTED.value},
        )
        await asyncio.sleep(0)
        if self._mcp_http_server is not None:
            await self._mcp_http_server.stop()
            self._mcp_http_server = None
        if self._ws_server is not None:
            await self._ws_server.stop()
            self._ws_server = None
        if self._http_server is not None:
            await self._http_server.stop()
            self._http_server = None

        if self.storage.is_initialized:
            await self.storage.record_audit("daemon", "daemon.stop", "success")
            await self.storage.close()

        self._running = False
        self.logger.info(
            "NEXUS core daemon stopped gracefully",
            extra={"event": "daemon.stopped"},
        )

    async def health(self) -> dict[str, Any]:
        project_count = 0
        if self.storage.is_initialized:
            count_rows = await self.storage.fetch_tuples("SELECT COUNT(*) FROM projects")
            if count_rows:
                project_count = int(count_rows[0][0])
        real_engine_count = (
            self.engines.connected_adapter_count + self.adapters.connected_real_engine_count()
        )
        return {
            "service": "nexus-python-daemon",
            "version": APP_VERSION,
            "status": NexusStatus.CONNECTED.value if self._running else NexusStatus.DISCONNECTED.value,
            "daemonState": NexusStatus.RUNNING.value if self._running else NexusStatus.DISCONNECTED.value,
            "os": platform.system(),
            "pid": os.getpid(),
            "startedAt": self.started_at,
            "logFile": str(self.config.log_file) if self.config.log_file is not None else None,
            "sqliteInitialized": self.storage.is_initialized,
            "registeredProjectCount": project_count,
            "connectedEngineCount": real_engine_count,
            "connectedTestAdaptersCount": self.adapters.connected_test_adapter_count(),
            "installedAdaptersCount": len(self.adapters.list_adapters()),
            "registeredToolCount": self.tools.verified_count,
            "mcpToolsCount": len(self.mcp.list_tools()),
            "restPort": self.http_port,
            "wsPort": self.ws_port,
            "mcpHttpPort": self.mcp_port,
            "recoveredInterruptedTasks": len(self.recovered_interrupted_tasks),
            "permissionCategories": sorted(self.permissions.list_permission_categories().keys()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def serve_forever(self) -> None:
        await self.start(start_network=True)
        loop = asyncio.get_running_loop()

        def _signal_handler() -> None:
            self.request_shutdown()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _signal_handler)
            except (NotImplementedError, ValueError):
                # Windows ProactorEventLoop does not support add_signal_handler;
                # fall back to standard signal.signal below.
                signal.signal(sig, lambda _s, _f: self.request_shutdown())

        sigbreak = getattr(signal, "SIGBREAK", None)
        if sigbreak is not None:
            signal.signal(sigbreak, lambda _s, _f: self.request_shutdown())

        try:
            assert self._stop_event is not None
            await self._stop_event.wait()
        finally:
            await self.stop()
