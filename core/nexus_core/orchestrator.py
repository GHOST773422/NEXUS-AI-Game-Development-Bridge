"""NEXUS Stage 8 Autonomous Development Engine & 16-Phase Task Orchestrator."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
import uuid

from core.nexus_core.checkpoints import CheckpointManager
from core.nexus_core.concurrency import MultiAgentCoordinator
from core.nexus_core.errors import (
    ConflictError,
    DaemonUnavailableError,
    NexusCoreError,
    PermissionDeniedError,
    ValidationError,
)
from core.nexus_core.event_manager import EventManager
from core.nexus_core.security import PermissionManager, redact_sensitive_fields
from core.nexus_core.storage import SQLiteStorageManager
from sdk.python.nexus_sdk import NexusStatus, PermissionScope, TaskExecutionStep

if TYPE_CHECKING:
    from core.nexus_core.adapters.manager import AdapterManager, AdapterRuntimeRecord
    from core.nexus_core.project_registry import ProjectRecord

TASK_PRIORITIES: tuple[str, ...] = ("low", "normal", "high", "critical")
PRIORITY_WEIGHT: dict[str, int] = {
    "critical": 4,
    "high": 3,
    "normal": 2,
    "low": 1,
}

AUTONOMOUS_PHASES: tuple[tuple[str, str, bool], ...] = (
    ("Receive Task", "Task Orchestrator", False),
    ("Identify Target Project", "Project Context Engine", False),
    ("Inspect Engine State", "Engine Manager", False),
    ("Analyze Requirements", "Context Analyzer", False),
    ("Generate Execution Plan", "Execution Planner", False),
    ("Identify Dependencies", "Dependency Resolver", False),
    ("Validate Tool Availability", "Tool Registry", False),
    ("Validate Permissions", "Permission Manager", True),
    ("Create Checkpoint", "Checkpoint Manager", False),
    ("Execute Operations", "Universal Adapter Runtime", False),
    ("Inspect Results", "Scene & Visual Verifier", False),
    ("Diagnose Errors", "Diagnostics & Engine Logs", False),
    ("Perform Bounded Repairs", "Autonomous Repair Engine", True),
    ("Run Tests", "Verification Runner", False),
    ("Verify Completion", "Completion Verifier", False),
    ("Generate Report", "Storage & Reporting", False),
)

# Backwards-compatible alias while upgrading to the full 16-phase workflow
TWELVE_STEP_TEMPLATE = list(AUTONOMOUS_PHASES)


@dataclass(slots=True)
class RetryPolicy:
    max_repair_attempts: int = 3
    max_step_retries: int = 1
    prevent_duplicate_failures: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "maxRepairAttempts": self.max_repair_attempts,
            "maxStepRetries": self.max_step_retries,
            "preventDuplicateFailures": self.prevent_duplicate_failures,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "RetryPolicy":
        if not raw:
            return cls()
        return cls(
            max_repair_attempts=max(0, min(10, int(raw.get("maxRepairAttempts", 3)))),
            max_step_retries=max(0, min(5, int(raw.get("maxStepRetries", 1)))),
            prevent_duplicate_failures=bool(raw.get("preventDuplicateFailures", True)),
        )


@dataclass(slots=True)
class ExecutionLimits:
    max_operations: int = 25
    step_timeout_sec: float = 30.0
    require_checkpoint_for_mutations: bool = True
    capture_visual_verification: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "maxOperations": self.max_operations,
            "stepTimeoutSec": self.step_timeout_sec,
            "requireCheckpointForMutations": self.require_checkpoint_for_mutations,
            "captureVisualVerification": self.capture_visual_verification,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "ExecutionLimits":
        if not raw:
            return cls()
        return cls(
            max_operations=max(1, min(100, int(raw.get("maxOperations", 25)))),
            step_timeout_sec=max(1.0, min(300.0, float(raw.get("stepTimeoutSec", 30.0)))),
            require_checkpoint_for_mutations=bool(
                raw.get("requireCheckpointForMutations", True)
            ),
            capture_visual_verification=bool(raw.get("captureVisualVerification", True)),
        )


@dataclass(slots=True)
class PlannedOperation:
    op_id: str
    title: str
    tool_id: str
    arguments: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    target_resources: list[str] = field(default_factory=list)
    required_permissions: list[str] = field(default_factory=list)
    is_mutation: bool = False
    is_test: bool = False
    status: str = NexusStatus.PLANNED.value
    attempts: int = 0
    error: str | None = None
    output: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "opId": self.op_id,
            "title": self.title,
            "toolId": self.tool_id,
            "arguments": self.arguments,
            "dependsOn": list(self.depends_on),
            "targetResources": list(self.target_resources),
            "requiredPermissions": list(self.required_permissions),
            "isMutation": self.is_mutation,
            "isTest": self.is_test,
            "status": self.status,
            "attempts": self.attempts,
            "error": self.error,
            "output": self.output,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any], index: int) -> "PlannedOperation":
        op_id = str(raw.get("opId") or f"step-{index + 1:02d}").strip()
        tool_id = str(raw.get("toolId", "")).strip()
        if not tool_id:
            raise ValidationError(f"Operation '{op_id}' is missing required 'toolId'.")
        args = raw.get("arguments")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            raise ValidationError(f"Operation '{op_id}' arguments must be a JSON object.")
        deps = [str(d).strip() for d in (raw.get("dependsOn") or []) if str(d).strip()]
        resources = [str(r).strip() for r in (raw.get("targetResources") or []) if str(r).strip()]
        for key in ("assetPath", "resourcePath", "scenePath", "nodePath", "objectName", "path"):
            val = args.get(key)
            if isinstance(val, str) and val.strip() and val.strip() not in resources:
                resources.append(val.strip())
        return cls(
            op_id=op_id,
            title=str(raw.get("title") or tool_id).strip(),
            tool_id=tool_id,
            arguments=dict(args),
            depends_on=deps,
            target_resources=resources,
            required_permissions=[
                str(p).strip() for p in (raw.get("requiredPermissions") or []) if str(p).strip()
            ],
            is_mutation=bool(raw.get("isMutation", False)),
            is_test=bool(raw.get("isTest", False)),
            status=str(raw.get("status") or NexusStatus.PLANNED.value),
            attempts=int(raw.get("attempts", 0)),
            error=raw.get("error"),
            output=raw.get("output") if isinstance(raw.get("output"), dict) else None,
        )


@dataclass(slots=True)
class TaskPlan:
    task_id: str
    project_id: str
    goal: str
    status: NexusStatus = NexusStatus.PLANNED
    steps: list[TaskExecutionStep] = field(default_factory=list)

    @classmethod
    def create_template(cls, task_id: str, project_id: str, goal: str) -> "TaskPlan":
        steps = [
            TaskExecutionStep(step_number=idx + 1, name=name, subsystem=sub, gate_required=gate)
            for idx, (name, sub, gate) in enumerate(AUTONOMOUS_PHASES)
        ]
        return cls(task_id=task_id, project_id=project_id, goal=goal, steps=steps)


def _operation_fingerprint(tool_id: str, arguments: dict[str, Any]) -> str:
    clean_args = {k: v for k, v in arguments.items() if k != "_approved"}
    canonical = json.dumps({"toolId": tool_id, "arguments": clean_args}, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _topo_sort_operations(ops: list[PlannedOperation]) -> list[PlannedOperation]:
    """Validates dependency DAG and returns deterministic topological execution order."""
    by_id = {op.op_id: op for op in ops}
    if len(by_id) != len(ops):
        raise ValidationError("Execution plan contains duplicate operation IDs.")
    for op in ops:
        for dep in op.depends_on:
            if dep == op.op_id:
                raise ValidationError(f"Operation '{op.op_id}' cannot depend on itself.")
            if dep not in by_id:
                raise ValidationError(
                    f"Operation '{op.op_id}' declares unknown dependency '{dep}'."
                )

    ordered: list[PlannedOperation] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def _visit(op_id: str) -> None:
        if op_id in visited:
            return
        if op_id in visiting:
            raise ValidationError(f"Cyclic dependency detected involving '{op_id}'.")
        visiting.add(op_id)
        for dep_id in by_id[op_id].depends_on:
            _visit(dep_id)
        visiting.remove(op_id)
        visited.add(op_id)
        ordered.append(by_id[op_id])

    for op in ops:
        _visit(op.op_id)
    return ordered


class AutonomousOrchestrator:
    """Executes bounded, checkpointed, permission-gated, multi-step tasks across real adapters."""

    def __init__(
        self,
        *,
        adapters: "AdapterManager",
        permissions: PermissionManager,
        checkpoints: CheckpointManager,
        concurrency: MultiAgentCoordinator,
        events: EventManager,
        storage: SQLiteStorageManager,
    ) -> None:
        self.adapters = adapters
        self.permissions = permissions
        self.checkpoints = checkpoints
        self.concurrency = concurrency
        self.events = events
        self.storage = storage
        self._pause_flags: set[str] = set()
        self._cancel_flags: set[str] = set()

    def request_pause(self, task_id: str) -> None:
        self._pause_flags.add(task_id)

    def clear_pause(self, task_id: str) -> None:
        self._pause_flags.discard(task_id)

    def request_cancel(self, task_id: str) -> None:
        self._cancel_flags.add(task_id)

    def resolve_adapter_for_project(
        self,
        *,
        project: "ProjectRecord",
        preferred_adapter_id: str | None = None,
    ) -> "AdapterRuntimeRecord":
        if preferred_adapter_id:
            record = self.adapters.get_record(preferred_adapter_id)
            if record.client is None or record.lifecycle_state.value != "Connected":
                raise DaemonUnavailableError(
                    f"Adapter '{preferred_adapter_id}' is not connected.",
                    details={"adapterId": preferred_adapter_id, "projectId": project.id},
                )
            return record

        # Prefer connected adapter matching the project engine (or explicit projectId)
        candidates = [
            rec
            for rec in self.adapters._records.values()  # noqa: SLF001
            if rec.client is not None
            and rec.lifecycle_state.value == "Connected"
            and (
                rec.manifest.engine_kind == project.engine
                or (
                    rec.engine_info.get("projectId") == project.id
                    and not rec.manifest.is_test_adapter
                )
            )
        ]
        if not candidates:
            raise DaemonUnavailableError(
                f"No connected engine adapter available for {project.engine} project '{project.name}'.",
                details={"projectId": project.id, "engine": project.engine},
            )
        # Prefer adapter whose engineInfo.projectId matches project.id if available
        for c in candidates:
            if c.engine_info.get("projectId") == project.id:
                return c
        return candidates[0]

    def _lookup_tool_descriptor(
        self, record: "AdapterRuntimeRecord", tool_id: str
    ) -> dict[str, Any] | None:
        if record.manifest.is_test_adapter:
            return record.test_tool_descriptors.get(tool_id)
        full_id = f"{record.manifest.adapter_id}.{tool_id}"
        try:
            contract = self.adapters.tool_registry.get_tool(full_id)
            return {
                "id": tool_id,
                "fullId": full_id,
                "requiredPermissions": [p.value for p in contract.required_permissions],
                "category": contract.category,
                "status": contract.implementation_status.value,
            }
        except Exception:
            # Also try exact tool_id match if registered directly
            try:
                contract = self.adapters.tool_registry.get_tool(tool_id)
                return {
                    "id": tool_id,
                    "fullId": tool_id,
                    "requiredPermissions": [p.value for p in contract.required_permissions],
                    "category": contract.category,
                    "status": contract.implementation_status.value,
                }
            except Exception:
                return None

    async def _build_default_operations(
        self,
        *,
        record: "AdapterRuntimeRecord",
        goal: str,
    ) -> list[PlannedOperation]:
        """Generates a real diagnostic & verification plan using live discovered tools."""
        tools_resp = await record.client.listTools()  # type: ignore[union-attr]
        available_ids = [str(t.get("id", "")) for t in (tools_resp.get("tools") or [])]

        ops: list[PlannedOperation] = []
        if record.manifest.engine_kind == "Godot":
            if "godot.get_scene_state" in available_ids:
                ops.append(
                    PlannedOperation(
                        op_id="op-01-scene",
                        title="Inspect Godot scene state",
                        tool_id="godot.get_scene_state",
                    )
                )
            if "godot.get_node_hierarchy" in available_ids:
                ops.append(
                    PlannedOperation(
                        op_id="op-02-hierarchy",
                        title="Inspect Godot node hierarchy",
                        tool_id="godot.get_node_hierarchy",
                        depends_on=["op-01-scene"] if ops else [],
                    )
                )
            if "godot.get_errors" in available_ids:
                ops.append(
                    PlannedOperation(
                        op_id="op-03-errors",
                        title="Verify zero Godot script/editor errors",
                        tool_id="godot.get_errors",
                        is_test=True,
                        depends_on=[ops[-1].op_id] if ops else [],
                    )
                )
        elif record.manifest.engine_kind == "Unity":
            if "unity.get_editor_state" in available_ids:
                ops.append(
                    PlannedOperation(
                        op_id="op-01-editor",
                        title="Inspect Unity Editor state",
                        tool_id="unity.get_editor_state",
                    )
                )
            if "unity.get_scene_hierarchy" in available_ids:
                ops.append(
                    PlannedOperation(
                        op_id="op-02-hierarchy",
                        title="Inspect Unity scene hierarchy",
                        tool_id="unity.get_scene_hierarchy",
                        depends_on=["op-01-editor"] if ops else [],
                    )
                )
            if "unity.get_compilation_status" in available_ids:
                ops.append(
                    PlannedOperation(
                        op_id="op-03-compile",
                        title="Verify clean Unity C# compilation status",
                        tool_id="unity.get_compilation_status",
                        is_test=True,
                        depends_on=[ops[-1].op_id] if ops else [],
                    )
                )
        elif available_ids:
            ops.append(
                PlannedOperation(
                    op_id="op-01-default",
                    title=f"Execute baseline diagnostic for: {goal}",
                    tool_id=available_ids[0],
                    arguments={"echo": goal},
                )
            )
        if not ops:
            raise ValidationError(
                f"Connected adapter '{record.manifest.adapter_id}' exposes no executable tools for planning."
            )
        return ops

    def _synthesize_bounded_repair(
        self,
        *,
        failed_op: PlannedOperation,
        error_text: str,
        diagnostics: dict[str, Any],
        failed_fingerprints: set[str],
    ) -> dict[str, Any] | None:
        """Generates a distinct corrective argument patch from real error text without repeating failures."""
        lower_err = error_text.lower()
        patched_args = dict(failed_op.arguments)

        # Case 1: script/file already exists without overwrite flag
        if ("exists" in lower_err or "already" in lower_err) and not patched_args.get("overwrite"):
            patched_args["overwrite"] = True
            fp = _operation_fingerprint(failed_op.tool_id, patched_args)
            if fp not in failed_fingerprints:
                return {
                    "strategy": "enable_overwrite_on_existing_target",
                    "toolId": failed_op.tool_id,
                    "arguments": patched_args,
                }

        # Case 2: repair hint embedded cleanly via structured repairArguments in error diagnostics
        hinted_args = diagnostics.get("suggestedArguments") or failed_op.arguments.get("_repairArguments")
        if isinstance(hinted_args, dict) and hinted_args:
            candidate_args = {**patched_args, **hinted_args}
            candidate_args.pop("_repairArguments", None)
            fp = _operation_fingerprint(failed_op.tool_id, candidate_args)
            if fp not in failed_fingerprints:
                return {
                    "strategy": "apply_diagnostic_suggested_arguments",
                    "toolId": failed_op.tool_id,
                    "arguments": candidate_args,
                }

        # Case 3: node name conflict or missing parent fallback to root "."
        if "parent" in lower_err and patched_args.get("parentPath") not in (None, "."):
            patched_args["parentPath"] = "."
            fp = _operation_fingerprint(failed_op.tool_id, patched_args)
            if fp not in failed_fingerprints:
                return {
                    "strategy": "fallback_parent_to_scene_root",
                    "toolId": failed_op.tool_id,
                    "arguments": patched_args,
                }

        # Do NOT retry with the identical failed fingerprint
        return None

    async def _collect_engine_diagnostics(
        self, record: "AdapterRuntimeRecord", target_project_id: str
    ) -> dict[str, Any]:
        diag: dict[str, Any] = {"adapterErrors": [], "engineLogs": []}
        assert record.client is not None
        for tool_candidate in (
            "godot.get_errors",
            "godot.inspect_debugger",
            "unity.get_compilation_status",
            "unity.get_console_logs",
        ):
            if self._lookup_tool_descriptor(record, tool_candidate) is not None:
                try:
                    res = await record.client.executeTool(
                        tool_candidate, target_project_id, {"limit": 20}
                    )
                    diag[tool_candidate] = res.get("output", res)
                except Exception as exc:  # noqa: BLE001
                    diag["adapterErrors"].append(str(exc))
        return diag

    async def run_task(
        self,
        *,
        task: dict[str, Any],
        project: "ProjectRecord",
        adapter_id: str | None = None,
        approved_scopes: set[str] | None = None,
        on_persist: Callable[[dict[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        """Executes the 16-phase workflow with locks, checkpoints, permissions, visual check & repairs."""
        task_id = str(task["id"])
        agent_id = str(task.get("agentId") or "operator")
        goal = str(task.get("title", ""))
        plan_cfg = dict(task.get("plan") or {})
        retry_policy = RetryPolicy.from_dict(plan_cfg.get("retryPolicy"))
        limits = ExecutionLimits.from_dict(plan_cfg.get("executionLimits"))
        granted_scopes: set[str] = set(plan_cfg.get("approvedScopes") or [])
        if approved_scopes:
            granted_scopes.update(approved_scopes)

        steps: list[dict[str, Any]] = [dict(s) for s in task["steps"]]
        logs: list[str] = list(task["logs"])
        context: dict[str, Any] = dict(
            task.get("context")
            or {
                "project": {"id": project.id, "name": project.name, "engine": project.engine},
                "activeScene": None,
                "relevantObjects": [],
                "scripts": [],
                "assets": [],
                "engineState": {},
                "previousOperations": [],
                "recentErrors": [],
                "screenshots": [],
                "repairHistory": [],
            }
        )

        failed_fingerprints: set[str] = set(plan_cfg.get("failedFingerprints") or [])
        checkpoint_id: str | None = task.get("checkpointId")
        repair_attempts = int(plan_cfg.get("repairAttempts", 0))
        started_at = datetime.now(timezone.utc).isoformat()
        project_lock_acquired = False

        async def _sync_state(
            phase_idx: int | None,
            phase_status: str,
            task_status: str,
            current_op: str,
            *,
            progress: int | None = None,
            approval_pending: dict[str, Any] | None = None,
            report: dict[str, Any] | None = None,
        ) -> None:
            if phase_idx is not None and 0 <= phase_idx < len(steps):
                steps[phase_idx]["status"] = phase_status
            if progress is None:
                done = sum(
                    1 for s in steps if s["status"] in {NexusStatus.CONNECTED.value, NexusStatus.AVAILABLE.value}
                )
                computed_progress = int(round((done / max(1, len(steps))) * 100))
            else:
                computed_progress = progress

            plan_cfg["retryPolicy"] = retry_policy.to_dict()
            plan_cfg["executionLimits"] = limits.to_dict()
            plan_cfg["approvedScopes"] = sorted(granted_scopes)
            plan_cfg["failedFingerprints"] = sorted(failed_fingerprints)
            plan_cfg["repairAttempts"] = repair_attempts
            plan_cfg["approvalPending"] = approval_pending

            task["status"] = task_status
            task["currentOperation"] = current_op
            task["progress"] = computed_progress
            task["checkpointId"] = checkpoint_id
            task["steps"] = steps
            task["logs"] = logs
            task["plan"] = plan_cfg
            task["context"] = context
            if report is not None:
                task["report"] = report

            if on_persist is not None:
                maybe = on_persist(task)
                if asyncio.iscoroutine(maybe):
                    await maybe

            await self.events.publish(
                "task.step_updated",
                "orchestrator",
                {
                    "taskId": task_id,
                    "projectId": project.id,
                    "agentId": agent_id,
                    "status": task_status,
                    "progress": computed_progress,
                    "currentOperation": current_op,
                },
            )

        self.clear_pause(task_id)
        try:
            # Phase 1 & 2: Receive Task + Identify Target Project
            logs.append(f"[{datetime.now(timezone.utc).isoformat()}] Orchestration started by '{agent_id}'.")
            await _sync_state(0, NexusStatus.CONNECTED.value, NexusStatus.RUNNING.value, "Received task & agent identity.")
            await _sync_state(1, NexusStatus.CONNECTED.value, NexusStatus.RUNNING.value, f"Identified target project '{project.name}'.")

            # Phase 3: Inspect Engine State (verifies live adapter exists cleanly)
            record = self.resolve_adapter_for_project(
                project=project, preferred_adapter_id=adapter_id or plan_cfg.get("adapterId")
            )
            assert record.client is not None
            plan_cfg["adapterId"] = record.manifest.adapter_id
            engine_info = await record.client.getEngineInfo()
            target_engine_proj_id = str(engine_info.get("projectId") or project.id)
            project_state = await asyncio.wait_for(
                record.client.getProjectState(target_engine_proj_id),
                timeout=limits.step_timeout_sec,
            )
            health_state = await asyncio.wait_for(
                record.client.healthCheck(), timeout=limits.step_timeout_sec
            )
            if project_state.get("isCompiling") or health_state.get("isCompiling"):
                raise DaemonUnavailableError(
                    "Target engine is currently compiling; deferring autonomous task execution."
                )

            context["engineState"] = {
                "adapterId": record.manifest.adapter_id,
                "engineInfo": engine_info,
                "projectState": project_state,
                "health": health_state,
            }
            context["activeScene"] = (
                project_state.get("activeScenePath")
                or project_state.get("activeScene")
                or engine_info.get("activeScene")
            )
            await _sync_state(2, NexusStatus.CONNECTED.value, NexusStatus.RUNNING.value, "Inspected live engine state.")

            # Phase 4: Analyze Requirements (pull scene/asset/error context cleanly)
            for h_tool in ("godot.get_node_hierarchy", "unity.get_scene_hierarchy"):
                if self._lookup_tool_descriptor(record, h_tool) is not None:
                    try:
                        h_res = await record.client.executeTool(h_tool, target_engine_proj_id, {"maxDepth": 4})
                        context["relevantObjects"] = [h_res.get("output", h_res)]
                    except Exception:
                        pass
            for a_tool in ("godot.inspect_assets", "unity.inspect_assets"):
                if self._lookup_tool_descriptor(record, a_tool) is not None:
                    try:
                        a_res = await record.client.executeTool(a_tool, target_engine_proj_id, {"limit": 50})
                        assets_out = (a_res.get("output") or {}).get("assets") or []
                        context["assets"] = assets_out
                        context["scripts"] = [
                            a for a in assets_out if str(a.get("path", "")).endswith((".cs", ".gd"))
                        ]
                    except Exception:
                        pass
            diag_init = await self._collect_engine_diagnostics(record, target_engine_proj_id)
            context["recentErrors"] = diag_init.get("adapterErrors", [])
            await _sync_state(3, NexusStatus.CONNECTED.value, NexusStatus.RUNNING.value, "Analyzed requirements and project context.")

            # Phase 5 & 6: Generate Execution Plan + Identify Dependencies
            raw_ops = plan_cfg.get("operations") or []
            if raw_ops:
                planned_ops = [
                    PlannedOperation.from_dict(op, idx) for idx, op in enumerate(raw_ops)
                ]
            else:
                planned_ops = await self._build_default_operations(record=record, goal=goal)

            if len(planned_ops) > limits.max_operations:
                raise ValidationError(
                    f"Plan contains {len(planned_ops)} operations exceeding limit ({limits.max_operations})."
                )
            ordered_ops = _topo_sort_operations(planned_ops)
            plan_cfg["operations"] = [op.to_dict() for op in ordered_ops]
            await _sync_state(4, NexusStatus.CONNECTED.value, NexusStatus.RUNNING.value, f"Generated {len(ordered_ops)}-operation execution plan.")
            await _sync_state(5, NexusStatus.CONNECTED.value, NexusStatus.RUNNING.value, "Validated operation dependency DAG.")

            # Phase 7: Validate Tool Availability
            resolved_scopes: dict[str, list[PermissionScope]] = {}
            for op in ordered_ops:
                desc = self._lookup_tool_descriptor(record, op.tool_id)
                if desc is None:
                    raise ValidationError(
                        f"Planned tool '{op.tool_id}' is not registered on adapter '{record.manifest.adapter_id}'."
                    )
                if desc.get("status") in {NexusStatus.PLANNED.value, NexusStatus.UNAVAILABLE.value}:
                    raise ValidationError(
                        f"Planned tool '{op.tool_id}' has status '{desc.get('status')}' and cannot run."
                    )
                raw_perms = op.required_permissions or list(desc.get("requiredPermissions") or ["project:read"])
                op_scopes = [PermissionScope(p) for p in raw_perms]
                resolved_scopes[op.op_id] = op_scopes
                if any(
                    s
                    in {
                        PermissionScope.WRITE_SCENE,
                        PermissionScope.WRITE_SCRIPT,
                        PermissionScope.MODIFY_ASSETS,
                        PermissionScope.BUILD_EXPORT,
                    }
                    for s in op_scopes
                ):
                    op.is_mutation = True
            await _sync_state(6, NexusStatus.CONNECTED.value, NexusStatus.RUNNING.value, "Validated availability of all planned tools.")

            # Phase 8: Validate Permissions, Inputs & Never Bypass PermissionManager / OS Process Rules
            pending_scopes: list[str] = []
            project_root_path = Path(project.root_path)
            for op in ordered_ops:
                self.permissions.validate_tool_arguments(
                    op.tool_id, op.arguments, project_root=project_root_path
                )
                for scope in resolved_scopes[op.op_id]:
                    if scope == PermissionScope.PROCESS_SPAWN_RESTRICTED:
                        raise PermissionDeniedError(
                            f"Autonomous task cannot execute unrestricted OS process scope '{scope.value}' on operation '{op.op_id}'."
                        )
                for scope in self.permissions.requires_approval_for_tool(
                    op.tool_id, resolved_scopes[op.op_id]
                ):
                    if scope.value not in granted_scopes and scope.value not in pending_scopes:
                        pending_scopes.append(scope.value)

            if pending_scopes:
                steps[7]["status"] = NexusStatus.UNAVAILABLE.value
                logs.append(f"Paused at Approval Gate awaiting operator approval for scopes: {pending_scopes}.")
                await _sync_state(
                    7,
                    NexusStatus.UNAVAILABLE.value,
                    NexusStatus.UNAVAILABLE.value,
                    f"Awaiting approval gate for: {', '.join(pending_scopes)}",
                    approval_pending={"requiredScopes": pending_scopes, "reason": "Substantial/restricted scope gate"},
                )
                return task

            await _sync_state(7, NexusStatus.CONNECTED.value, NexusStatus.RUNNING.value, "Verified sandbox, tool inputs & approval permissions.")

            # Phase 9: Acquire Multi-Agent Project Lock + Resource Claims + Create Checkpoint
            self.concurrency.acquire_project_lock(project.id, task_id, agent_id)
            project_lock_acquired = True
            all_resources = [res for op in ordered_ops for res in op.target_resources]
            if all_resources:
                self.concurrency.claim_resources(project.id, task_id, agent_id, all_resources)

            has_mutations = any(op.is_mutation for op in ordered_ops)
            if limits.require_checkpoint_for_mutations and (has_mutations or all_resources):
                ckpt = await self.checkpoints.create_checkpoint(
                    task_id=task_id,
                    project_id=project.id,
                    project_root=Path(project.root_path),
                    target_paths=all_resources,
                    engine_state=project_state,
                )
                checkpoint_id = ckpt["checkpointId"]
                logs.append(f"Created reversible checkpoint {checkpoint_id} ({ckpt['trackedFiles']} tracked targets).")
            await _sync_state(8, NexusStatus.CONNECTED.value, NexusStatus.RUNNING.value, f"Acquired project lock & checkpoint ({checkpoint_id or 'read-only'}).")

            # Phase 10, 11, 12, 13, 14: Execute Operations + Inspect + Diagnose + Bounded Repairs + Tests
            any_errors_recorded: list[str] = []
            executed_count = 0
            completed_ops: set[str] = {
                op.op_id for op in ordered_ops if op.status == NexusStatus.CONNECTED.value
            }

            for op in ordered_ops:
                if op.op_id in completed_ops:
                    continue

                if task_id in self._cancel_flags:
                    self._cancel_flags.discard(task_id)
                    logs.append("Task cancelled cleanly by operator.")
                    await _sync_state(9, NexusStatus.DISCONNECTED.value, NexusStatus.DISCONNECTED.value, "Cancelled by operator.")
                    return task

                if task_id in self._pause_flags:
                    self._pause_flags.discard(task_id)
                    logs.append(f"Task paused cooperatively before operation '{op.op_id}'.")
                    await _sync_state(9, NexusStatus.UNAVAILABLE.value, NexusStatus.UNAVAILABLE.value, f"Paused before {op.op_id}.")
                    return task

                if any(dep not in completed_ops for dep in op.depends_on):
                    raise ValidationError(f"Dependencies not met for '{op.op_id}'.")

                if op.target_resources:
                    self.concurrency.claim_resources(project.id, task_id, agent_id, op.target_resources)

                current_tool = op.tool_id
                current_args = dict(op.arguments)
                # Inject _approved only after Phase 8 explicit PermissionManager gate validation
                if self.permissions.requires_approval_for_tool(
                    current_tool, resolved_scopes[op.op_id]
                ):
                    current_args["_approved"] = True

                op_succeeded = False
                while not op_succeeded:
                    fp = _operation_fingerprint(current_tool, current_args)
                    if retry_policy.prevent_duplicate_failures and fp in failed_fingerprints:
                        msg = (
                            f"DuplicateFailurePrevented: Refusing to re-apply identical failed operation "
                            f"'{current_tool}' on '{op.op_id}'."
                        )
                        op.status = NexusStatus.FAILED.value
                        op.error = msg
                        any_errors_recorded.append(msg)
                        logs.append(msg)
                        raise ValidationError(msg, details={"opId": op.op_id, "fingerprint": fp})

                    op.attempts += 1
                    op.status = NexusStatus.RUNNING.value
                    op_started_at = datetime.now(timezone.utc).isoformat()
                    await self.storage.execute(
                        """
                        INSERT INTO operation_journal (
                            task_id, op_id, project_id, tool_id, target_resources_json,
                            fingerprint, status, reversible, started_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(task_id, op_id) DO UPDATE SET
                            tool_id = excluded.tool_id,
                            fingerprint = excluded.fingerprint,
                            status = excluded.status,
                            started_at = excluded.started_at,
                            error_code = NULL,
                            error_message = NULL,
                            finished_at = NULL
                        """,
                        (
                            task_id,
                            op.op_id,
                            project.id,
                            current_tool,
                            json.dumps(op.target_resources, ensure_ascii=True),
                            fp,
                            NexusStatus.RUNNING.value,
                            1 if checkpoint_id else 0,
                            op_started_at,
                        ),
                    )
                    op_entry = self.concurrency.begin_operation(
                        task_id=task_id,
                        project_id=project.id,
                        agent_id=agent_id,
                        tool_id=current_tool,
                        resources=op.target_resources,
                    )
                    try:
                        raw_result = await asyncio.wait_for(
                            record.client.executeTool(
                                current_tool,
                                target_engine_proj_id,
                                current_args,
                                request_id=f"{task_id}:{op.op_id}:{op.attempts}",
                            ),
                            timeout=limits.step_timeout_sec,
                        )
                        if isinstance(raw_result, dict) and (
                            raw_result.get("verified") is False
                            or raw_result.get("isError") is True
                            or raw_result.get("success") is False
                            or raw_result.get("status") == NexusStatus.FAILED.value
                            or bool(raw_result.get("error"))
                        ):
                            raise ValidationError(
                                str(
                                    raw_result.get("message")
                                    or raw_result.get("error")
                                    or f"Tool '{current_tool}' reported engine failure."
                                ),
                                details=raw_result,
                            )

                        self.concurrency.finish_operation(op_entry.op_id, status="Completed")
                        op_finished_at = datetime.now(timezone.utc).isoformat()
                        await self.storage.execute(
                            """
                            UPDATE operation_journal
                            SET status = ?, finished_at = ?, file_changes_json = ?
                            WHERE task_id = ? AND op_id = ?
                            """,
                            (
                                "Succeeded",
                                op_finished_at,
                                json.dumps(op.target_resources, ensure_ascii=True),
                                task_id,
                                op.op_id,
                            ),
                        )
                        op.status = NexusStatus.CONNECTED.value
                        op.output = raw_result if isinstance(raw_result, dict) else {"result": raw_result}
                        op.error = None
                        completed_ops.add(op.op_id)
                        executed_count += 1
                        context["previousOperations"].append(
                            {
                                "opId": op.op_id,
                                "toolId": current_tool,
                                "attempts": op.attempts,
                                "status": "Succeeded",
                            }
                        )
                        logs.append(f"Executed '{op.op_id}' ({current_tool}) successfully.")
                        op_succeeded = True
                    except Exception as exc:  # noqa: BLE001
                        self.concurrency.finish_operation(op_entry.op_id, status="Failed")
                        failed_fingerprints.add(fp)
                        err_msg = str(exc)
                        err_code = exc.code if isinstance(exc, NexusCoreError) else type(exc).__name__
                        any_errors_recorded.append(f"{op.op_id}: {err_msg}")
                        context["recentErrors"].append(
                            {"opId": op.op_id, "toolId": current_tool, "error": err_msg}
                        )
                        logs.append(f"Operation '{op.op_id}' failed: {err_msg}")

                        # Phase 12: Diagnose Errors via live engine state
                        await _sync_state(11, NexusStatus.AVAILABLE.value, NexusStatus.RUNNING.value, f"Diagnosing failure in {op.op_id}.")
                        live_diag = await self._collect_engine_diagnostics(record, target_engine_proj_id)

                        repair_plan = None
                        if repair_attempts < retry_policy.max_repair_attempts:
                            repair_plan = self._synthesize_bounded_repair(
                                failed_op=op,
                                error_text=err_msg,
                                diagnostics=live_diag,
                                failed_fingerprints=failed_fingerprints,
                            )

                        now_fail = datetime.now(timezone.utc).isoformat()
                        await self.storage.execute(
                            """
                            UPDATE operation_journal
                            SET status = ?, error_code = ?, error_message = ?, finished_at = ?
                            WHERE task_id = ? AND op_id = ?
                            """,
                            (NexusStatus.FAILED.value, err_code, err_msg, now_fail, task_id, op.op_id),
                        )
                        await self.storage.execute(
                            """
                            INSERT INTO failed_operations (
                                task_id, project_id, op_id, tool_id, arguments_json,
                                fingerprint, error_code, error_message, diagnostics_json,
                                repair_attempted, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                task_id,
                                project.id,
                                op.op_id,
                                current_tool,
                                json.dumps(redact_sensitive_fields(current_args), ensure_ascii=True),
                                fp,
                                err_code,
                                err_msg,
                                json.dumps(live_diag, ensure_ascii=True),
                                1 if repair_plan is not None else 0,
                                now_fail,
                            ),
                        )

                        # Phase 13: Perform Bounded Repairs (with strict deduplication + attempt limit)
                        if repair_attempts >= retry_policy.max_repair_attempts:
                            op.status = NexusStatus.FAILED.value
                            op.error = f"Exceeded maxRepairAttempts ({retry_policy.max_repair_attempts}): {err_msg}"
                            await _sync_state(12, NexusStatus.FAILED.value, NexusStatus.FAILED.value, op.error)
                            raise ValidationError(op.error) from exc
                        if repair_plan is None:
                            op.status = NexusStatus.FAILED.value
                            op.error = f"No distinct repair strategy for '{op.op_id}' (prevented duplicate retry): {err_msg}"
                            await _sync_state(12, NexusStatus.FAILED.value, NexusStatus.FAILED.value, op.error)
                            raise ValidationError(op.error) from exc

                        repair_attempts += 1
                        current_tool = str(repair_plan["toolId"])
                        current_args = dict(repair_plan["arguments"])
                        if any(self.permissions.requires_approval(s) for s in resolved_scopes[op.op_id]):
                            current_args["_approved"] = True
                        repair_entry = {
                            "attempt": repair_attempts,
                            "opId": op.op_id,
                            "strategy": repair_plan["strategy"],
                            "toolId": current_tool,
                        }
                        context["repairHistory"].append(repair_entry)
                        logs.append(
                            f"Bounded repair #{repair_attempts}/{retry_policy.max_repair_attempts}: {repair_plan['strategy']} on {op.op_id}."
                        )
                        steps[12]["status"] = NexusStatus.AVAILABLE.value

                plan_cfg["operations"] = [o.to_dict() for o in ordered_ops]
                await _sync_state(9, NexusStatus.RUNNING.value, NexusStatus.RUNNING.value, f"Completed operation {op.op_id} ({executed_count}/{len(ordered_ops)}).")

            steps[9]["status"] = NexusStatus.CONNECTED.value
            steps[11]["status"] = NexusStatus.CONNECTED.value
            steps[12]["status"] = NexusStatus.CONNECTED.value

            # Phase 11: Inspect Results + Visual Verification (Screenshot + Scene Info)
            if limits.capture_visual_verification:
                try:
                    shot = await asyncio.wait_for(
                        record.client.captureScreenshot(target_engine_proj_id, "SceneView"),
                        timeout=limits.step_timeout_sec,
                    )
                    if isinstance(shot, dict):
                        shot_summary = {
                            "viewport": shot.get("viewport", "SceneView"),
                            "mimeType": shot.get("mimeType", "image/png"),
                            "width": shot.get("width"),
                            "height": shot.get("height"),
                            "byteLength": shot.get("byteLength"),
                            "capturedAt": shot.get("capturedAt") or datetime.now(timezone.utc).isoformat(),
                        }
                        context["screenshots"].append(shot_summary)
                except Exception as exc:  # noqa: BLE001
                    logs.append(f"Visual verification screenshot skipped cleanly: {exc}")

            post_state = await asyncio.wait_for(
                record.client.getProjectState(target_engine_proj_id),
                timeout=limits.step_timeout_sec,
            )
            context["engineState"]["postProjectState"] = post_state
            await _sync_state(10, NexusStatus.CONNECTED.value, NexusStatus.RUNNING.value, "Completed structured scene & visual verification.")

            # Phase 14: Run Tests / Post-Op Verification Checks (inspect real output payloads)
            test_results: list[dict[str, Any]] = []
            failed_test_messages: list[str] = []
            for test_op in ordered_ops:
                if not test_op.is_test:
                    continue
                raw_out = test_op.output if isinstance(test_op.output, dict) else {}
                out_payload = raw_out.get("output") if isinstance(raw_out.get("output"), dict) else raw_out
                error_count = int(out_payload.get("errorCount", 0) or 0)
                failed_count = int(out_payload.get("failed", 0) or 0)
                adapter_errors = out_payload.get("adapterErrors")
                explicit_errors = out_payload.get("errors")
                passed = (
                    out_payload.get("passed") is not False
                    and raw_out.get("verified") is not False
                    and error_count == 0
                    and failed_count == 0
                    and not (isinstance(adapter_errors, list) and len(adapter_errors) > 0)
                    and not (isinstance(explicit_errors, list) and len(explicit_errors) > 0)
                )
                test_results.append(
                    {
                        "opId": test_op.op_id,
                        "toolId": test_op.tool_id,
                        "passed": passed,
                        "errorCount": error_count,
                        "failedCount": failed_count,
                    }
                )
                if not passed:
                    failed_test_messages.append(
                        f"Verification '{test_op.op_id}' ({test_op.tool_id}) reported failure "
                        f"(errorCount={error_count}, failed={failed_count})."
                    )
            final_diag = await self._collect_engine_diagnostics(record, target_engine_proj_id)
            if failed_test_messages:
                fail_msg = "; ".join(failed_test_messages)
                any_errors_recorded.extend(failed_test_messages)
                logs.append(f"Post-operation verification failed: {fail_msg}")
                await _sync_state(13, NexusStatus.FAILED.value, NexusStatus.RUNNING.value, fail_msg)
                raise ValidationError(
                    fail_msg,
                    details={"testResults": test_results, "diagnostics": final_diag},
                )
            await _sync_state(13, NexusStatus.CONNECTED.value, NexusStatus.RUNNING.value, f"Executed verification checks ({len(test_results)} test steps).")

            # Phase 15: Verify Completion
            if not ordered_ops or len(completed_ops) != len(ordered_ops):
                raise ValidationError(
                    f"Completion check failed: only {len(completed_ops)}/{len(ordered_ops)} operations completed."
                )
            await _sync_state(14, NexusStatus.CONNECTED.value, NexusStatus.RUNNING.value, "Verified completion criteria against engine state.")

            # Phase 16: Finalize File Change Manifest & Generate Completion Report
            file_change_manifest: dict[str, Any] | None = None
            if checkpoint_id:
                file_change_manifest = await self.checkpoints.finalize_file_change_manifest(
                    checkpoint_id,
                    project_root=Path(project.root_path),
                    extra_paths=all_resources,
                )
                context["fileChangeManifest"] = file_change_manifest

            finished_at = datetime.now(timezone.utc).isoformat()
            report = {
                "reportId": f"rep-{uuid.uuid4().hex[:10]}",
                "taskId": task_id,
                "projectId": project.id,
                "engine": project.engine,
                "adapterId": record.manifest.adapter_id,
                "agentId": agent_id,
                "outcome": "Succeeded",
                "startedAt": started_at,
                "finishedAt": finished_at,
                "operationsTotal": len(ordered_ops),
                "operationsSucceeded": len(completed_ops),
                "repairAttempts": repair_attempts,
                "checkpointId": checkpoint_id,
                "fileChangeManifest": file_change_manifest,
                "screenshotsCaptured": len(context["screenshots"]),
                "testResults": test_results,
                "errorsEncountered": any_errors_recorded,
                "postDiagnostics": final_diag,
            }
            steps[15]["status"] = NexusStatus.CONNECTED.value
            logs.append(
                f"Task completed & verified ({len(completed_ops)}/{len(ordered_ops)} operations, repairs={repair_attempts}, screenshots={len(context['screenshots'])})."
            )
            await _sync_state(
                15,
                NexusStatus.CONNECTED.value,
                NexusStatus.CONNECTED.value,
                f"Completed cleanly ({len(completed_ops)}/{len(ordered_ops)} ops verified).",
                progress=100,
                report=report,
            )
            await self.storage.record_audit(
                agent_id,
                "task.complete",
                "success",
                target=task_id,
                detail={"projectId": project.id, "repairAttempts": repair_attempts, "checkpointId": checkpoint_id},
            )
            return task

        except NexusCoreError as exc:
            logs.append(f"Orchestration stopped ({exc.code}): {exc.message}")
            file_change_manifest_err: dict[str, Any] | None = None
            if checkpoint_id:
                try:
                    file_change_manifest_err = await self.checkpoints.finalize_file_change_manifest(
                        checkpoint_id,
                        project_root=Path(project.root_path),
                    )
                    context["fileChangeManifest"] = file_change_manifest_err
                except Exception:  # noqa: BLE001
                    pass
            report = {
                "reportId": f"rep-{uuid.uuid4().hex[:10]}",
                "taskId": task_id,
                "projectId": project.id,
                "agentId": agent_id,
                "outcome": "Failed",
                "errorCode": exc.code,
                "errorMessage": exc.message,
                "checkpointId": checkpoint_id,
                "fileChangeManifest": file_change_manifest_err,
                "repairAttempts": repair_attempts,
                "finishedAt": datetime.now(timezone.utc).isoformat(),
            }
            if isinstance(exc, ConflictError):
                # Do NOT overwrite task status of a running rival if conflict happened cleanly; mark failed cleanly
                await _sync_state(None, NexusStatus.FAILED.value, NexusStatus.FAILED.value, exc.message, report=report)
            elif isinstance(exc, DaemonUnavailableError):
                await _sync_state(2, NexusStatus.UNAVAILABLE.value, NexusStatus.FAILED.value, exc.message, report=report)
            else:
                await _sync_state(None, NexusStatus.FAILED.value, NexusStatus.FAILED.value, exc.message, report=report)
            raise
        finally:
            if project_lock_acquired:
                self.concurrency.release_project_lock(project.id, task_id)
            else:
                self.concurrency.release_task_resources(task_id)
