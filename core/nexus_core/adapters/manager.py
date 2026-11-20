"""NEXUS Universal Adapter Manager, Lifecycle FSM, Health Monitor & Reconnection Engine."""

from __future__ import annotations

import asyncio
from collections import deque
import contextlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import json
from pathlib import Path
from typing import Any
import uuid

from core.nexus_core.adapters.interface import (
    ProtocolEngineAdapter,
    build_transport_for_manifest,
)
from core.nexus_core.adapters.manifest import (
    DAEMON_ADAPTER_PROTOCOL_VERSION,
    AdapterManifest,
    parse_adapter_manifest,
    validate_adapter_compatibility,
)
from core.nexus_core.errors import (
    AdapterCompatibilityError,
    AdapterProtocolError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from core.nexus_core.event_manager import EventManager
from core.nexus_core.security import PermissionManager
from core.nexus_core.storage import SQLiteStorageManager
from core.nexus_core.tool_registry import CoreToolRegistry
from sdk.python.nexus_sdk import EngineKind, NexusStatus, PermissionScope, ToolContract


class AdapterLifecycleState(StrEnum):
    INSTALLED = "Installed"
    VALIDATED = "Validated"
    CONNECTING = "Connecting"
    CONNECTED = "Connected"
    DEGRADED = "Degraded"
    RECONNECTING = "Reconnecting"
    DISCONNECTED = "Disconnected"
    FAILED = "Failed"


@dataclass(slots=True)
class ReconnectionPolicy:
    auto_reconnect: bool = True
    max_attempts: int = 3
    base_delay_seconds: float = 0.05
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 5.0

    def delay_for_attempt(self, attempt: int) -> float:
        raw = self.base_delay_seconds * (self.backoff_multiplier ** max(0, attempt - 1))
        return min(self.max_delay_seconds, raw)


@dataclass(slots=True)
class AdapterErrorRecord:
    timestamp: str
    adapter_id: str
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "adapter_id": self.adapter_id,
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class AdapterCapabilityRegistry:
    """Tracks declared and verified capabilities cleanly separating real engines vs test harnesses."""

    def __init__(self) -> None:
        self._caps: dict[str, dict[str, Any]] = {}

    def register(
        self, adapter_id: str, *, is_test_adapter: bool, engine_kind: str, capabilities: list[str]
    ) -> None:
        self._caps[adapter_id] = {
            "adapterId": adapter_id,
            "isTestAdapter": is_test_adapter,
            "engineKind": engine_kind,
            "capabilities": sorted(set(capabilities)),
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }

    def unregister(self, adapter_id: str) -> None:
        self._caps.pop(adapter_id, None)

    def summary(self) -> dict[str, Any]:
        real = {k: v for k, v in self._caps.items() if not v["isTestAdapter"]}
        test = {k: v for k, v in self._caps.items() if v["isTestAdapter"]}
        return {
            "realEngineAdapters": real,
            "testHarnessAdapters": test,
            "realCapabilityCount": sum(len(v["capabilities"]) for v in real.values()),
            "testCapabilityCount": sum(len(v["capabilities"]) for v in test.values()),
        }


@dataclass(slots=True)
class AdapterRuntimeRecord:
    manifest: AdapterManifest
    base_dir: Path | None = None
    lifecycle_state: AdapterLifecycleState = AdapterLifecycleState.INSTALLED
    engine_info: dict[str, Any] = field(default_factory=dict)
    health_report: dict[str, Any] = field(default_factory=dict)
    registered_tool_ids: list[str] = field(default_factory=list)
    test_tool_descriptors: dict[str, dict[str, Any]] = field(default_factory=dict)
    reconnect_attempts: int = 0
    last_error: AdapterErrorRecord | None = None
    last_heartbeat_at: str | None = None
    client: ProtocolEngineAdapter | None = None
    manual_disconnect: bool = False
    reconnect_task: asyncio.Task[None] | None = None

    def to_descriptor(self) -> dict[str, Any]:
        return {
            "adapterId": self.manifest.adapter_id,
            "displayName": self.manifest.display_name,
            "version": self.manifest.version,
            "engineKind": self.manifest.engine_kind,
            "runtimeLanguage": self.manifest.runtime_language,
            "isTestAdapter": self.manifest.is_test_adapter,
            "protocolVersion": self.manifest.protocol_version,
            "lifecycleState": self.lifecycle_state.value,
            "transportKind": self.manifest.transport.kind,
            "registeredToolCount": len(self.registered_tool_ids),
            "testToolCount": len(self.test_tool_descriptors),
            "reconnectAttempts": self.reconnect_attempts,
            "lastHeartbeatAt": self.last_heartbeat_at,
            "engineInfo": self.engine_info,
            "healthReport": self.health_report,
            "lastError": self.last_error.to_dict() if self.last_error else None,
        }


class AdapterManager:
    """Manages installation, compatibility validation, lifecycle, health checks, and reconnection."""

    def __init__(
        self,
        *,
        storage: SQLiteStorageManager,
        permissions: PermissionManager,
        events: EventManager,
        tool_registry: CoreToolRegistry,
        reconnection_policy: ReconnectionPolicy | None = None,
        daemon_protocol_version: str = DAEMON_ADAPTER_PROTOCOL_VERSION,
    ) -> None:
        self.storage = storage
        self.permissions = permissions
        self.events = events
        self.tool_registry = tool_registry
        self.reconnection_policy = reconnection_policy or ReconnectionPolicy()
        self.daemon_protocol_version = daemon_protocol_version
        self.capabilities = AdapterCapabilityRegistry()
        self._records: dict[str, AdapterRuntimeRecord] = {}
        self._errors: deque[AdapterErrorRecord] = deque(maxlen=100)
        self._project_root_cache: dict[str, Path] = {}
        self._health_task: asyncio.Task[None] | None = None
        self._monitor_interval_seconds: float | None = None

    async def restore_from_storage(self) -> None:
        """Restores installed adapter manifests persisted in SQLite across daemon restarts."""
        rows = await self.storage.execute(
            "SELECT * FROM installed_adapters ORDER BY is_test_adapter ASC, adapter_id ASC"
        )
        for row in rows:
            try:
                raw_manifest = json.loads(str(row["manifest_json"]))
                manifest = parse_adapter_manifest(raw_manifest)
                self._records[manifest.adapter_id] = AdapterRuntimeRecord(
                    manifest=manifest,
                    lifecycle_state=AdapterLifecycleState.INSTALLED,
                )
            except Exception as exc:
                self._record_error(str(row.get("adapter_id", "unknown")), "NEXUS_RESTORE_FAILED", str(exc))

    def start_health_monitor(self, interval_seconds: float = 5.0) -> None:
        if self._health_task is not None:
            return
        self._monitor_interval_seconds = interval_seconds
        self._health_task = asyncio.create_task(self._health_monitor_loop(interval_seconds))

    async def stop_all(self) -> None:
        if self._health_task is not None:
            self._health_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._health_task
            self._health_task = None

        for adapter_id in list(self._records.keys()):
            record = self._records[adapter_id]
            record.manual_disconnect = True
            if record.reconnect_task is not None:
                record.reconnect_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await record.reconnect_task
                record.reconnect_task = None
            if record.lifecycle_state in {
                AdapterLifecycleState.CONNECTED,
                AdapterLifecycleState.CONNECTING,
                AdapterLifecycleState.DEGRADED,
                AdapterLifecycleState.RECONNECTING,
            }:
                with contextlib.suppress(Exception):
                    await self.disconnect_adapter(adapter_id)

    def _record_error(
        self,
        adapter_id: str,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> AdapterErrorRecord:
        err = AdapterErrorRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            adapter_id=adapter_id,
            code=code,
            message=message,
            details=details or {},
        )
        self._errors.append(err)
        rec = self._records.get(adapter_id)
        if rec is not None:
            rec.last_error = err
        return err

    def list_adapters(self) -> list[dict[str, Any]]:
        return [rec.to_descriptor() for rec in self._records.values()]

    def list_errors(self) -> list[dict[str, Any]]:
        return [err.to_dict() for err in reversed(self._errors)]

    def connected_real_engine_count(self) -> int:
        return sum(
            1
            for rec in self._records.values()
            if not rec.manifest.is_test_adapter
            and rec.lifecycle_state == AdapterLifecycleState.CONNECTED
        )

    def connected_test_adapter_count(self) -> int:
        return sum(
            1
            for rec in self._records.values()
            if rec.manifest.is_test_adapter
            and rec.lifecycle_state == AdapterLifecycleState.CONNECTED
        )

    def get_record(self, adapter_id: str) -> AdapterRuntimeRecord:
        rec = self._records.get(adapter_id)
        if rec is None:
            raise NotFoundError(
                f"Adapter '{adapter_id}' is not installed.",
                details={"adapterId": adapter_id},
            )
        return rec

    async def install_adapter(
        self,
        raw_manifest: dict[str, Any],
        *,
        base_dir: Path | None = None,
    ) -> dict[str, Any]:
        manifest = parse_adapter_manifest(raw_manifest)
        validate_adapter_compatibility(
            manifest,
            daemon_protocol_version=self.daemon_protocol_version,
            base_dir=base_dir,
        )
        if manifest.adapter_id in self._records:
            raise ConflictError(
                f"Adapter '{manifest.adapter_id}' is already installed.",
                details={"adapterId": manifest.adapter_id},
            )

        now = datetime.now(timezone.utc).isoformat()
        await self.storage.execute(
            """
            INSERT INTO installed_adapters (
                adapter_id, display_name, version, engine_kind, runtime_language,
                is_test_adapter, manifest_json, status, installed_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                manifest.adapter_id,
                manifest.display_name,
                manifest.version,
                manifest.engine_kind,
                manifest.runtime_language,
                1 if manifest.is_test_adapter else 0,
                json.dumps(manifest.to_dict(), ensure_ascii=True),
                AdapterLifecycleState.VALIDATED.value,
                now,
                now,
            ),
        )
        record = AdapterRuntimeRecord(
            manifest=manifest,
            base_dir=base_dir,
            lifecycle_state=AdapterLifecycleState.VALIDATED,
        )
        self._records[manifest.adapter_id] = record
        await self.storage.record_audit(
            "daemon",
            "adapter.install",
            "success",
            target=manifest.adapter_id,
            detail={"isTestAdapter": manifest.is_test_adapter, "runtime": manifest.runtime_language},
        )
        return record.to_descriptor()

    async def uninstall_adapter(self, adapter_id: str) -> None:
        record = self.get_record(adapter_id)
        record.manual_disconnect = True
        if record.reconnect_task is not None:
            record.reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await record.reconnect_task
            record.reconnect_task = None
        if record.client is not None:
            with contextlib.suppress(Exception):
                await self.disconnect_adapter(adapter_id)
        self._cleanup_adapter_registrations(record)
        await self.storage.execute(
            "DELETE FROM installed_adapters WHERE adapter_id = ?",
            (adapter_id,),
        )
        del self._records[adapter_id]
        await self.storage.record_audit(
            "daemon", "adapter.uninstall", "success", target=adapter_id
        )

    def _cleanup_adapter_registrations(self, record: AdapterRuntimeRecord) -> None:
        self.capabilities.unregister(record.manifest.adapter_id)
        if not record.manifest.is_test_adapter:
            self.tool_registry.unregister_tools_for_prefix(f"{record.manifest.adapter_id}.")
        record.registered_tool_ids.clear()
        record.test_tool_descriptors.clear()

    def validate_for_activation(self, adapter_id: str) -> AdapterRuntimeRecord:
        record = self.get_record(adapter_id)
        validate_adapter_compatibility(
            record.manifest,
            daemon_protocol_version=self.daemon_protocol_version,
            base_dir=record.base_dir,
        )
        if record.lifecycle_state == AdapterLifecycleState.INSTALLED:
            record.lifecycle_state = AdapterLifecycleState.VALIDATED
        return record

    async def connect_adapter(self, adapter_id: str) -> dict[str, Any]:
        record = self.validate_for_activation(adapter_id)
        record.manual_disconnect = False
        record.lifecycle_state = AdapterLifecycleState.CONNECTING

        transport = build_transport_for_manifest(
            record.manifest,
            working_dir_fallback=str(record.base_dir) if record.base_dir else None,
        )
        client = ProtocolEngineAdapter(record.manifest, transport)

        async def _on_event(event: dict[str, Any]) -> None:
            method_name = str(event.get("method", "adapter.event"))
            params = dict(event.get("params") or {})
            params.setdefault("adapterId", adapter_id)
            params.setdefault("isTestAdapter", record.manifest.is_test_adapter)
            await self.events.publish(
                "engine.log" if method_name == "adapter.log" else "engine.scene_changed",
                f"adapter:{adapter_id}",
                params,
            )

        async def _on_unexpected_disconnect(reason: str) -> None:
            if record.manual_disconnect:
                return
            self._record_error(
                adapter_id,
                "NEXUS_ADAPTER_DISCONNECTED",
                f"Adapter connection lost unexpectedly ({reason}).",
            )
            record.lifecycle_state = AdapterLifecycleState.RECONNECTING
            self._cleanup_adapter_registrations(record)
            await self.events.publish(
                "error.diagnostic",
                f"adapter:{adapter_id}",
                {"adapterId": adapter_id, "reason": reason, "reconnecting": True},
            )
            if self.reconnection_policy.auto_reconnect and (
                record.reconnect_task is None or record.reconnect_task.done()
            ):
                record.reconnect_task = asyncio.create_task(self._reconnect_loop(adapter_id))

        transport.set_disconnect_callback(_on_unexpected_disconnect)

        try:
            await client.open_transport()
            connect_ack = await client.connect()
            engine_info = await client.getEngineInfo()

            # Enforce honesty guard: test adapters cannot claim real Unity/Godot engine identity
            if record.manifest.is_test_adapter and engine_info.get("isTestAdapter") is not True:
                raise AdapterCompatibilityError(
                    "Test adapter getEngineInfo() failed explicit isTestAdapter=true attestation."
                )

            if engine_info.get("compatible") is False:
                reasons = engine_info.get("compatibilityReasons") or [
                    f"Unsupported {record.manifest.engine_kind} version '{engine_info.get('engineVersion', 'unknown')}'."
                ]
                raise AdapterCompatibilityError(
                    "; ".join(str(r) for r in reasons),
                    details={"adapterId": adapter_id, "engineInfo": engine_info},
                )

            cap_resp = await client.getCapabilities()
            tools_resp = await client.listTools()
            health_resp = await client.healthCheck()
            await client.subscribeEvents(
                ["engine.log", "engine.scene_changed", "adapter.heartbeat"], _on_event
            )
        except Exception as exc:
            await client.close_transport()
            record.lifecycle_state = AdapterLifecycleState.FAILED
            err = self._record_error(adapter_id, "NEXUS_ADAPTER_CONNECT_FAILED", str(exc))
            await self.storage.record_audit(
                "daemon", "adapter.connect", "failed", target=adapter_id, detail=err.to_dict()
            )
            raise

        record.client = client
        record.engine_info = engine_info
        record.health_report = health_resp
        record.last_heartbeat_at = str(
            health_resp.get("timestamp") or datetime.now(timezone.utc).isoformat()
        )
        record.reconnect_attempts = 0
        record.lifecycle_state = AdapterLifecycleState.CONNECTED

        caps = [str(c) for c in (cap_resp.get("capabilities") or record.manifest.capabilities)]

        # Register tools cleanly: test adapter tools stay isolated from real CoreToolRegistry counts
        self._cleanup_adapter_registrations(record)
        self.capabilities.register(
            adapter_id,
            is_test_adapter=record.manifest.is_test_adapter,
            engine_kind=record.manifest.engine_kind,
            capabilities=caps,
        )
        raw_tools = tools_resp.get("tools") or []
        for tool in raw_tools:
            if not isinstance(tool, dict):
                continue
            tool_id = str(tool.get("id", "")).strip()
            if not tool_id:
                continue
            if record.manifest.is_test_adapter:
                record.test_tool_descriptors[tool_id] = {
                    **tool,
                    "adapterId": adapter_id,
                    "isTestAdapter": True,
                }
            else:
                if record.manifest.engine_kind not in {EngineKind.UNITY.value, EngineKind.GODOT.value}:
                    continue
                contract = ToolContract(
                    id=f"{adapter_id}.{tool_id}",
                    category=str(tool.get("category", "Debugging")),
                    description=str(tool.get("description", "")),
                    input_schema=tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {},
                    output_schema=tool.get("outputSchema") if isinstance(tool.get("outputSchema"), dict) else {},
                    engine_compatibility=[EngineKind(record.manifest.engine_kind)],
                    required_permissions=[
                        PermissionScope(p)
                        for p in (tool.get("requiredPermissions") or ["project:read"])
                    ],
                    execution_context=str(tool.get("executionContext", "EditorMainThread")),
                    error_handling=str(tool.get("errorHandling", "Structured error envelope")),
                    implementation_status=NexusStatus.CONNECTED,
                )
                self.tool_registry.register_verified_tool(contract)
                record.registered_tool_ids.append(contract.id)

        await self.storage.execute(
            "UPDATE installed_adapters SET status = ?, updated_at = ? WHERE adapter_id = ?",
            (
                AdapterLifecycleState.CONNECTED.value,
                datetime.now(timezone.utc).isoformat(),
                adapter_id,
            ),
        )
        await self.storage.record_audit(
            "daemon",
            "adapter.connect",
            "success",
            target=adapter_id,
            detail={
                "isTestAdapter": record.manifest.is_test_adapter,
                "sessionId": connect_ack.get("sessionId"),
            },
        )
        await self.events.publish(
            "bridge.status",
            f"adapter:{adapter_id}",
            {
                "adapterId": adapter_id,
                "lifecycleState": record.lifecycle_state.value,
                "isTestAdapter": record.manifest.is_test_adapter,
            },
        )
        return record.to_descriptor()

    async def disconnect_adapter(self, adapter_id: str) -> dict[str, Any]:
        record = self.get_record(adapter_id)
        record.manual_disconnect = True
        if record.reconnect_task is not None:
            record.reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await record.reconnect_task
            record.reconnect_task = None
        if record.client is not None:
            with contextlib.suppress(Exception):
                await record.client.disconnect()
            await record.client.close_transport()
            record.client = None
        self._cleanup_adapter_registrations(record)
        record.lifecycle_state = AdapterLifecycleState.DISCONNECTED
        await self.storage.execute(
            "UPDATE installed_adapters SET status = ?, updated_at = ? WHERE adapter_id = ?",
            (
                AdapterLifecycleState.DISCONNECTED.value,
                datetime.now(timezone.utc).isoformat(),
                adapter_id,
            ),
        )
        await self.storage.record_audit(
            "daemon", "adapter.disconnect", "success", target=adapter_id
        )
        return record.to_descriptor()

    async def _reconnect_loop(self, adapter_id: str) -> None:
        record = self._records.get(adapter_id)
        if record is None:
            return
        for attempt in range(1, self.reconnection_policy.max_attempts + 1):
            if record.manual_disconnect:
                return
            record.reconnect_attempts = attempt
            delay = self.reconnection_policy.delay_for_attempt(attempt)
            await asyncio.sleep(delay)
            if record.manual_disconnect:
                return
            try:
                await self.connect_adapter(adapter_id)
                return
            except Exception as exc:
                self._record_error(
                    adapter_id,
                    "NEXUS_ADAPTER_RECONNECT_ATTEMPT_FAILED",
                    f"Reconnect attempt {attempt} failed: {exc}",
                )
        record.lifecycle_state = AdapterLifecycleState.FAILED

    async def _health_monitor_loop(self, interval_seconds: float) -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            connected_ids = [
                adapter_id
                for adapter_id, rec in list(self._records.items())
                if rec.lifecycle_state == AdapterLifecycleState.CONNECTED
            ]
            if connected_ids:
                await asyncio.gather(
                    *(self.health_check_adapter(aid) for aid in connected_ids),
                    return_exceptions=True,
                )

    async def health_check_adapter(self, adapter_id: str) -> dict[str, Any]:
        record = self.get_record(adapter_id)
        if record.client is None or not record.client.transport.is_connected:
            raise AdapterProtocolError(
                f"Adapter '{adapter_id}' is not connected.",
                details={"adapterId": adapter_id, "lifecycleState": record.lifecycle_state.value},
            )
        try:
            report = await record.client.healthCheck()
            record.health_report = report
            record.last_heartbeat_at = str(
                report.get("timestamp") or datetime.now(timezone.utc).isoformat()
            )
            record.lifecycle_state = (
                AdapterLifecycleState.CONNECTED
                if bool(report.get("responsive", True))
                else AdapterLifecycleState.DEGRADED
            )
            return {
                "adapterId": adapter_id,
                "isTestAdapter": record.manifest.is_test_adapter,
                "lifecycleState": record.lifecycle_state.value,
                "health": report,
            }
        except Exception as exc:
            record.lifecycle_state = AdapterLifecycleState.DEGRADED
            self._record_error(adapter_id, "NEXUS_ADAPTER_HEALTH_FAILED", str(exc))
            raise

    def list_tools_for_adapter(self, adapter_id: str) -> list[dict[str, Any]]:
        record = self.get_record(adapter_id)
        if record.manifest.is_test_adapter:
            return list(record.test_tool_descriptors.values())
        return [
            t
            for t in self.tool_registry.list_tools()
            if str(t["id"]).startswith(f"{adapter_id}.")
        ]

    async def discover_projects(
        self, adapter_id: str, search_roots: list[str] | None = None
    ) -> dict[str, Any]:
        record = self.get_record(adapter_id)
        if record.client is None or record.lifecycle_state != AdapterLifecycleState.CONNECTED:
            raise ValidationError(f"Adapter '{adapter_id}' is not connected.")
        return await record.client.discoverProjects(search_roots)

    async def execute_tool(
        self,
        adapter_id: str,
        tool_id: str,
        project_id: str,
        arguments: dict[str, Any] | None = None,
        *,
        approved: bool = False,
        approved_scopes: list[str] | None = None,
        project_root: Path | None = None,
    ) -> dict[str, Any]:
        record = self.get_record(adapter_id)
        if record.client is None or record.lifecycle_state != AdapterLifecycleState.CONNECTED:
            raise ValidationError(f"Adapter '{adapter_id}' is not connected.")

        raw_args = dict(arguments or {})
        effective_approved = bool(approved or raw_args.get("_approved") or raw_args.get("approved"))
        clean_args = {k: v for k, v in raw_args.items() if k not in {"_approved", "approved"}}

        resolved_root = project_root
        if resolved_root is None and project_id:
            cached_root = self._project_root_cache.get(project_id)
            if cached_root is not None:
                resolved_root = cached_root
            elif self.storage.is_initialized:
                rows = await self.storage.execute(
                    "SELECT root_path FROM projects WHERE id = ?",
                    (project_id,),
                )
                if rows:
                    resolved_root = Path(str(rows[0]["root_path"]))
                    if len(self._project_root_cache) >= 512:
                        self._project_root_cache.clear()
                    self._project_root_cache[project_id] = resolved_root
        if resolved_root is None:
            raw_engine_path = (record.engine_info or {}).get("projectPath")
            if isinstance(raw_engine_path, str) and raw_engine_path.strip():
                candidate_path = Path(raw_engine_path.strip())
                if candidate_path.is_absolute():
                    resolved_root = candidate_path

        self.permissions.validate_tool_arguments(
            tool_id,
            clean_args,
            project_root=resolved_root,
        )

        tool_scopes: list[PermissionScope] = []
        full_tool_id = f"{adapter_id}.{tool_id}"
        try:
            contract = self.tool_registry.get_tool(full_tool_id)
            tool_scopes = list(contract.required_permissions)
        except NotFoundError:
            test_desc = record.test_tool_descriptors.get(tool_id)
            if isinstance(test_desc, dict):
                tool_scopes = [
                    PermissionScope(p)
                    for p in (test_desc.get("requiredPermissions") or [])
                    if isinstance(p, str)
                ]

        granted_set = {str(s) for s in (approved_scopes or []) if isinstance(s, str)}
        gated_scopes = self.permissions.requires_approval_for_tool(tool_id, tool_scopes)
        scope_approved = bool(
            gated_scopes and all(s.value in granted_set for s in gated_scopes)
        )
        self.permissions.validate_destructive_operation(
            tool_scopes,
            approved=effective_approved or scope_approved,
            tool_id=tool_id,
        )

        req_id = uuid.uuid4().hex
        result = await record.client.executeTool(
            tool_id=tool_id,
            project_id=project_id,
            arguments=clean_args,
            request_id=req_id,
        )
        await self.storage.record_audit(
            "daemon",
            "adapter.execute_tool",
            "success",
            target=f"{adapter_id}:{tool_id}",
            detail={"isTestAdapter": record.manifest.is_test_adapter, "projectId": project_id},
        )
        return result

    async def get_project_state(self, adapter_id: str, project_id: str) -> dict[str, Any]:
        record = self.get_record(adapter_id)
        if record.client is None or record.lifecycle_state != AdapterLifecycleState.CONNECTED:
            raise ValidationError(f"Adapter '{adapter_id}' is not connected.")
        return await record.client.getProjectState(project_id)

    async def capture_screenshot(
        self, adapter_id: str, project_id: str, viewport: str = "SceneView"
    ) -> dict[str, Any]:
        record = self.get_record(adapter_id)
        if record.client is None or record.lifecycle_state != AdapterLifecycleState.CONNECTED:
            raise ValidationError(f"Adapter '{adapter_id}' is not connected.")
        return await record.client.captureScreenshot(project_id, viewport)
