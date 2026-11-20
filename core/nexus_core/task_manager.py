"""NEXUS Persistent Task Manager & Autonomous Execution Coordinator."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import uuid

from core.nexus_core.errors import NotFoundError, ValidationError
from core.nexus_core.event_manager import EventManager
from core.nexus_core.orchestrator import (
    PRIORITY_WEIGHT,
    TASK_PRIORITIES,
    AutonomousOrchestrator,
    ExecutionLimits,
    PlannedOperation,
    RetryPolicy,
    TaskPlan,
    _topo_sort_operations,
)
from core.nexus_core.project_registry import ProjectRegistry
from core.nexus_core.storage import SQLiteStorageManager
from sdk.python.nexus_sdk import NexusStatus


class TaskManager:
    """Manages persistent autonomous task plans, priorities, approvals, rollback & history."""

    def __init__(
        self,
        storage: SQLiteStorageManager,
        projects: ProjectRegistry,
        events: EventManager,
        orchestrator: AutonomousOrchestrator | None = None,
    ) -> None:
        self.storage = storage
        self.projects = projects
        self.events = events
        self.orchestrator = orchestrator

    def attach_orchestrator(self, orchestrator: AutonomousOrchestrator) -> None:
        self.orchestrator = orchestrator

    async def create_task_draft(
        self,
        *,
        project_id: str,
        title: str,
        priority: str = "normal",
        agent_id: str = "operator",
        operations: list[dict[str, Any]] | None = None,
        retry_policy: dict[str, Any] | None = None,
        execution_limits: dict[str, Any] | None = None,
        adapter_id: str | None = None,
        approved_scopes: list[str] | None = None,
    ) -> dict[str, Any]:
        clean_title = title.strip()
        if not clean_title:
            raise ValidationError("Task title must not be empty.")
        clean_priority = priority.strip().lower() or "normal"
        if clean_priority not in TASK_PRIORITIES:
            raise ValidationError(
                f"Invalid task priority '{priority}'. Allowed: {', '.join(TASK_PRIORITIES)}."
            )
        clean_agent = agent_id.strip() or "operator"
        project = await self.projects.get_project(project_id)

        validated_ops: list[dict[str, Any]] = []
        if operations:
            parsed_ops = [
                PlannedOperation.from_dict(raw_op, idx) for idx, raw_op in enumerate(operations)
            ]
            ordered_ops = _topo_sort_operations(parsed_ops)
            validated_ops = [op.to_dict() for op in ordered_ops]

        retry_cfg = RetryPolicy.from_dict(retry_policy).to_dict()
        limit_cfg = ExecutionLimits.from_dict(execution_limits).to_dict()

        task_id = f"task-{uuid.uuid4().hex[:10]}"
        plan = TaskPlan.create_template(task_id=task_id, project_id=project.id, goal=clean_title)
        now = datetime.now(timezone.utc).isoformat()
        steps_payload = [asdict(s) for s in plan.steps]
        logs_payload = [
            f"Task created for {project.name} ({project.engine}) by '{clean_agent}' [priority={clean_priority}].",
        ]
        plan_payload: dict[str, Any] = {
            "operations": validated_ops,
            "retryPolicy": retry_cfg,
            "executionLimits": limit_cfg,
            "adapterId": adapter_id,
            "approvedScopes": sorted({str(s).strip() for s in (approved_scopes or []) if str(s).strip()}),
            "repairAttempts": 0,
            "failedFingerprints": [],
            "approvalPending": None,
        }
        context_payload: dict[str, Any] = {
            "project": {
                "id": project.id,
                "name": project.name,
                "engine": project.engine,
                "rootPath": project.root_path,
            },
            "activeScene": getattr(project, "active_scene", None),
            "relevantObjects": [],
            "scripts": [],
            "assets": [],
            "engineState": {},
            "previousOperations": [],
            "recentErrors": [],
            "screenshots": [],
            "repairHistory": [],
        }
        op = "Task planned; ready for autonomous execution when engine adapter connects."

        await self.storage.execute(
            """
            INSERT INTO tasks (
                id, project_id, title, engine, priority, agent_id, progress, status,
                current_operation, checkpoint_id, steps_json, logs_json,
                plan_json, context_json, report_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                project.id,
                clean_title,
                project.engine,
                clean_priority,
                clean_agent,
                0,
                NexusStatus.PLANNED.value,
                op,
                None,
                json.dumps(steps_payload, separators=(",", ":")),
                json.dumps(logs_payload, separators=(",", ":")),
                json.dumps(plan_payload, separators=(",", ":")),
                json.dumps(context_payload, separators=(",", ":")),
                None,
                now,
                now,
            ),
        )
        await self.storage.record_audit(
            clean_agent,
            "task.create",
            "success",
            target=task_id,
            detail={"projectId": project.id, "priority": clean_priority, "operations": len(validated_ops)},
        )
        await self.events.publish(
            "task.step_updated",
            "task_manager",
            {"taskId": task_id, "projectId": project.id, "status": NexusStatus.PLANNED.value, "progress": 0},
        )
        return await self.get_task(task_id)

    async def _persist_task(self, task: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        task["updatedAt"] = now
        await self.storage.execute(
            """
            UPDATE tasks
            SET status = ?, progress = ?, current_operation = ?, checkpoint_id = ?,
                steps_json = ?, logs_json = ?, plan_json = ?, context_json = ?,
                report_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                task["status"],
                int(task.get("progress", 0)),
                task["currentOperation"],
                task.get("checkpointId"),
                json.dumps(task["steps"], separators=(",", ":")),
                json.dumps(task["logs"], separators=(",", ":")),
                json.dumps(task.get("plan") or {}, separators=(",", ":")),
                json.dumps(task.get("context") or {}, separators=(",", ":")),
                json.dumps(task["report"], separators=(",", ":")) if task.get("report") is not None else None,
                now,
                task["id"],
            ),
        )

    async def list_tasks(self) -> list[dict[str, Any]]:
        rows = await self.storage.fetch_tuples(
            """
            SELECT id, project_id, title, engine, priority, agent_id, progress, status,
                   current_operation, checkpoint_id, steps_json, logs_json,
                   plan_json, context_json, report_json, created_at, updated_at
            FROM tasks
            ORDER BY updated_at DESC
            """
        )
        loads = json.loads
        items = [
            {
                "id": r[0],
                "projectId": r[1],
                "title": r[2],
                "engine": r[3],
                "priority": r[4] or "normal",
                "agentId": r[5] or "operator",
                "progress": int(r[6] or 0),
                "status": r[7],
                "currentOperation": r[8],
                "checkpointId": r[9],
                "steps": loads(r[10]),
                "logs": loads(r[11]),
                "plan": loads(r[12]) if r[12] else {},
                "context": loads(r[13]) if r[13] else {},
                "report": loads(r[14]) if r[14] else None,
                "createdAt": r[15],
                "updatedAt": r[16],
            }
            for r in rows
        ]
        if len(items) > 1:
            items.sort(key=lambda item: PRIORITY_WEIGHT.get(item["priority"], 2), reverse=True)
        return items

    async def get_task(self, task_id: str) -> dict[str, Any]:
        rows = await self.storage.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        )
        if not rows:
            raise NotFoundError(f"Task '{task_id}' was not found.")
        return self._hydrate(rows[0])

    async def execute_task(
        self,
        task_id: str,
        *,
        adapter_id: str | None = None,
        approved_scopes: list[str] | None = None,
    ) -> dict[str, Any]:
        task = await self.get_task(task_id)
        if task["status"] in {NexusStatus.DISCONNECTED.value}:
            raise ValidationError(f"Cancelled task '{task_id}' cannot be executed.")
        if self.orchestrator is None:
            raise ValidationError("Autonomous orchestrator is not attached.")
        project = await self.projects.get_project(task["projectId"])
        scopes = {str(s).strip() for s in (approved_scopes or []) if str(s).strip()}
        return await self.orchestrator.run_task(
            task=task,
            project=project,
            adapter_id=adapter_id,
            approved_scopes=scopes,
            on_persist=self._persist_task,
        )

    async def approve_task_checkpoint(
        self,
        task_id: str,
        *,
        approved: bool = True,
        approved_scopes: list[str] | None = None,
        resume_execution: bool = True,
        adapter_id: str | None = None,
    ) -> dict[str, Any]:
        task = await self.get_task(task_id)
        plan = dict(task.get("plan") or {})
        pending = plan.get("approvalPending") or {}
        if not approved:
            task["status"] = NexusStatus.DISCONNECTED.value
            task["currentOperation"] = "Rejected at operator approval checkpoint."
            plan["approvalPending"] = None
            task["plan"] = plan
            task["logs"].append("Operator rejected approval checkpoint; task cancelled.")
            await self._persist_task(task)
            await self.storage.record_audit("operator", "task.approve", "rejected", target=task_id)
            return await self.get_task(task_id)

        scopes_to_add = set(approved_scopes or pending.get("requiredScopes") or [])
        granted = set(plan.get("approvedScopes") or [])
        granted.update(scopes_to_add)
        plan["approvedScopes"] = sorted(granted)
        plan["approvalPending"] = None
        task["plan"] = plan
        task["logs"].append(f"Operator approved scopes: {sorted(scopes_to_add)}.")
        await self._persist_task(task)
        await self.storage.record_audit(
            "operator",
            "task.approve",
            "approved",
            target=task_id,
            detail={"approvedScopes": sorted(scopes_to_add)},
        )
        if resume_execution:
            return await self.execute_task(task_id, adapter_id=adapter_id)
        return await self.get_task(task_id)

    async def control_task(
        self,
        task_id: str,
        action: str,
        *,
        adapter_id: str | None = None,
        approved_scopes: list[str] | None = None,
    ) -> dict[str, Any]:
        task = await self.get_task(task_id)
        if action == "execute":
            return await self.execute_task(
                task_id, adapter_id=adapter_id, approved_scopes=approved_scopes
            )

        if action == "rollback":
            return await self.rollback_task(task_id, target_files=None)

        if action == "pause":
            if self.orchestrator is not None:
                self.orchestrator.request_pause(task_id)
            next_status, next_op = NexusStatus.UNAVAILABLE.value, "Paused by operator."
        elif action == "resume":
            if self.orchestrator is not None:
                self.orchestrator.clear_pause(task_id)
            if task["status"] == NexusStatus.UNAVAILABLE.value and self.orchestrator is not None:
                project = await self.projects.get_project(task["projectId"])
                try:
                    self.orchestrator.resolve_adapter_for_project(
                        project=project, preferred_adapter_id=adapter_id
                    )
                    return await self.execute_task(
                        task_id, adapter_id=adapter_id, approved_scopes=approved_scopes
                    )
                except Exception:
                    pass
            next_status, next_op = NexusStatus.PLANNED.value, "Ready to resume when engine adapter connects."
        elif action == "cancel":
            if self.orchestrator is not None:
                self.orchestrator.request_cancel(task_id)
            next_status, next_op = NexusStatus.DISCONNECTED.value, "Cancelled by operator."
        else:
            raise ValidationError(
                f"Unsupported task control action '{action}'.",
                details={"action": action},
            )

        logs: list[str] = list(task["logs"])
        logs.append(f"Control action '{action}' applied -> {next_status}.")
        task["status"] = next_status
        task["currentOperation"] = next_op
        task["logs"] = logs
        await self._persist_task(task)
        await self.events.publish(
            "task.step_updated",
            "task_manager",
            {"taskId": task_id, "status": next_status, "action": action},
        )
        return await self.get_task(task_id)

    async def rollback_task(
        self,
        task_id: str,
        *,
        target_files: list[str] | None = None,
    ) -> dict[str, Any]:
        task = await self.get_task(task_id)
        checkpoint_id = task.get("checkpointId")
        if not checkpoint_id:
            raise ValidationError(
                f"Task '{task_id}' has no checkpoint recorded to rollback.",
                details={"taskId": task_id},
            )
        if self.orchestrator is None:
            raise ValidationError("Autonomous orchestrator is not attached.")
        project = await self.projects.get_project(task["projectId"])
        restored = await self.orchestrator.checkpoints.selective_rollback(
            checkpoint_id,
            project_root=Path(project.root_path),
            target_files=target_files,
        )
        mode_label = "Selective rollback" if restored.get("selective") else "Rolled back checkpoint"
        task["status"] = NexusStatus.PLANNED.value
        if not restored.get("selective"):
            task["progress"] = 0
        task["currentOperation"] = f"{mode_label} {checkpoint_id}."
        task["logs"].append(
            f"{mode_label} {checkpoint_id} "
            f"(restored={len(restored['restoredFiles'])}, removed={len(restored['removedFiles'])}, skipped={len(restored['skippedFiles'])})."
        )
        context = dict(task.get("context") or {})
        context["lastRollback"] = restored
        task["context"] = context
        await self._persist_task(task)
        await self.events.publish(
            "task.step_updated",
            "task_manager",
            {
                "taskId": task_id,
                "status": NexusStatus.PLANNED.value,
                "action": "rollback",
                "selective": bool(restored.get("selective")),
                "checkpointId": checkpoint_id,
            },
        )
        updated = await self.get_task(task_id)
        updated["lastRollback"] = restored
        return updated

    async def get_task_recovery_details(self, task_id: str) -> dict[str, Any]:
        task_rows, journal_rows, failed_rows = await self.storage.execute_many_reads(
            [
                ("SELECT * FROM tasks WHERE id = ?", (task_id,)),
                (
                    """
                    SELECT task_id, op_id, project_id, tool_id, target_resources_json, fingerprint,
                           status, error_code, error_message, reversible, file_changes_json,
                           started_at, finished_at
                    FROM operation_journal
                    WHERE task_id = ?
                    ORDER BY started_at ASC
                    """,
                    (task_id,),
                ),
                (
                    """
                    SELECT id, task_id, project_id, op_id, tool_id, arguments_json, fingerprint,
                           error_code, error_message, diagnostics_json, repair_attempted, created_at
                    FROM failed_operations
                    WHERE task_id = ?
                    ORDER BY id ASC
                    """,
                    (task_id,),
                ),
            ]
        )
        if not task_rows:
            raise NotFoundError(f"Task '{task_id}' was not found.")
        task = self._hydrate(task_rows[0])
        checkpoint_info: dict[str, Any] | None = None
        checkpoint_id = task.get("checkpointId")
        if checkpoint_id and self.orchestrator is not None:
            try:
                checkpoint_info = await self.orchestrator.checkpoints.get_checkpoint(checkpoint_id)
            except NotFoundError:
                checkpoint_info = None

        return {
            "taskId": task_id,
            "status": task["status"],
            "checkpointId": checkpoint_id,
            "checkpoint": checkpoint_info,
            "fileChangeManifest": (checkpoint_info or {}).get("fileChangeManifest"),
            "operationJournal": [
                {
                    "taskId": r["task_id"],
                    "opId": r["op_id"],
                    "projectId": r["project_id"],
                    "toolId": r["tool_id"],
                    "targetResources": json.loads(r["target_resources_json"] or "[]"),
                    "fingerprint": r["fingerprint"],
                    "status": r["status"],
                    "errorCode": r["error_code"],
                    "errorMessage": r["error_message"],
                    "reversible": bool(r["reversible"]),
                    "fileChanges": json.loads(r["file_changes_json"] or "[]"),
                    "startedAt": r["started_at"],
                    "finishedAt": r["finished_at"],
                }
                for r in journal_rows
            ],
            "failedOperations": [
                {
                    "id": r["id"],
                    "taskId": r["task_id"],
                    "projectId": r["project_id"],
                    "opId": r["op_id"],
                    "toolId": r["tool_id"],
                    "arguments": json.loads(r["arguments_json"] or "{}"),
                    "fingerprint": r["fingerprint"],
                    "errorCode": r["error_code"],
                    "errorMessage": r["error_message"],
                    "diagnostics": json.loads(r["diagnostics_json"] or "{}"),
                    "repairAttempted": bool(r["repair_attempted"]),
                    "createdAt": r["created_at"],
                }
                for r in failed_rows
            ],
        }

    async def recover_interrupted_tasks(self) -> list[dict[str, Any]]:
        """Detects tasks left in Running state across an unclean daemon restart and transitions them safely."""
        rows = await self.storage.execute(
            "SELECT * FROM tasks WHERE status = ?", (NexusStatus.RUNNING.value,)
        )
        recovered: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc).isoformat()
        for row in rows:
            task = self._hydrate(row)
            task_id = task["id"]
            await self.storage.execute(
                """
                UPDATE operation_journal
                SET status = ?, error_code = ?, error_message = ?, finished_at = ?
                WHERE task_id = ? AND status = ?
                """,
                (
                    "Interrupted",
                    "DAEMON_RESTART_INTERRUPTED",
                    "Operation interrupted when daemon stopped uncleanly before completion.",
                    now,
                    task_id,
                    NexusStatus.RUNNING.value,
                ),
            )
            for step in task["steps"]:
                if step.get("status") == NexusStatus.RUNNING.value:
                    step["status"] = NexusStatus.UNAVAILABLE.value
            task["status"] = NexusStatus.UNAVAILABLE.value
            ckpt_label = task.get("checkpointId") or "no-checkpoint"
            task["currentOperation"] = (
                f"Interrupted during daemon restart; checkpoint ({ckpt_label}) ready for resume or selective rollback."
            )
            task["logs"].append(
                f"[{now}] Daemon restart recovery detected interrupted Running task -> Unavailable (checkpoint={ckpt_label})."
            )
            await self._persist_task(task)
            await self.storage.record_audit(
                "daemon",
                "task.recover_interrupted",
                "recovered",
                target=task_id,
                detail={"checkpointId": task.get("checkpointId"), "projectId": task["projectId"]},
            )
            await self.events.publish(
                "task.step_updated",
                "task_manager",
                {
                    "taskId": task_id,
                    "status": NexusStatus.UNAVAILABLE.value,
                    "action": "recover_interrupted",
                    "checkpointId": task.get("checkpointId"),
                },
            )
            recovered.append(
                {
                    "taskId": task_id,
                    "projectId": task["projectId"],
                    "checkpointId": task.get("checkpointId"),
                    "recoveredAt": now,
                }
            )
        return recovered

    def _hydrate(self, row: dict[str, Any]) -> dict[str, Any]:
        loads = json.loads
        report_raw = row["report_json"]
        plan_raw = row["plan_json"]
        ctx_raw = row["context_json"]
        return {
            "id": row["id"],
            "projectId": row["project_id"],
            "title": row["title"],
            "engine": row["engine"],
            "priority": row["priority"] or "normal",
            "agentId": row["agent_id"] or "operator",
            "progress": int(row["progress"] or 0),
            "status": row["status"],
            "currentOperation": row["current_operation"],
            "checkpointId": row["checkpoint_id"],
            "steps": loads(row["steps_json"]),
            "logs": loads(row["logs_json"]),
            "plan": loads(plan_raw) if plan_raw else {},
            "context": loads(ctx_raw) if ctx_raw else {},
            "report": loads(report_raw) if report_raw else None,
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
