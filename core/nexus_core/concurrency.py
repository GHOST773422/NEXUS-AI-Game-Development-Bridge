"""NEXUS Multi-Agent Concurrency Coordinator, Project Locks & Resource Conflict Detection."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import threading
from typing import Any
import uuid

from core.nexus_core.errors import ConflictError


@dataclass(slots=True)
class ProjectLockEntry:
    project_id: str
    task_id: str
    agent_id: str
    acquired_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "projectId": self.project_id,
            "taskId": self.task_id,
            "agentId": self.agent_id,
            "acquiredAt": self.acquired_at,
        }


@dataclass(slots=True)
class ResourceClaimEntry:
    project_id: str
    resource_key: str
    task_id: str
    agent_id: str
    claimed_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "projectId": self.project_id,
            "resourceKey": self.resource_key,
            "taskId": self.task_id,
            "agentId": self.agent_id,
            "claimedAt": self.claimed_at,
        }


@dataclass(slots=True)
class ActiveOperationEntry:
    op_id: str
    task_id: str
    project_id: str
    agent_id: str
    tool_id: str
    resources: list[str]
    status: str
    started_at: str
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "opId": self.op_id,
            "taskId": self.task_id,
            "projectId": self.project_id,
            "agentId": self.agent_id,
            "toolId": self.tool_id,
            "resources": list(self.resources),
            "status": self.status,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
        }


def normalize_resource_key(raw: str) -> str:
    return raw.strip().replace("\\", "/").rstrip("/").lower()


class MultiAgentCoordinator:
    """Prevents conflicting concurrent AI writes via project locks, resource claims & op tracking."""

    def __init__(self, *, max_recent_ops: int = 100) -> None:
        self._lock = threading.RLock()
        self._project_locks: dict[str, ProjectLockEntry] = {}
        self._resource_claims: dict[tuple[str, str], ResourceClaimEntry] = {}
        self._active_operations: dict[str, ActiveOperationEntry] = {}
        self._recent_operations: list[ActiveOperationEntry] = []
        self._max_recent_ops = max_recent_ops

    def acquire_project_lock(self, project_id: str, task_id: str, agent_id: str) -> ProjectLockEntry:
        clean_agent = agent_id.strip() or "operator"
        with self._lock:
            existing = self._project_locks.get(project_id)
            if existing is not None and existing.task_id != task_id:
                raise ConflictError(
                    f"Project '{project_id}' is currently locked by task '{existing.task_id}' (agent '{existing.agent_id}').",
                    details={
                        "conflictType": "project_lock",
                        "projectId": project_id,
                        "holderTaskId": existing.task_id,
                        "holderAgentId": existing.agent_id,
                        "requestingTaskId": task_id,
                        "requestingAgentId": clean_agent,
                    },
                )
            if existing is not None:
                return existing
            entry = ProjectLockEntry(
                project_id=project_id,
                task_id=task_id,
                agent_id=clean_agent,
                acquired_at=datetime.now(timezone.utc).isoformat(),
            )
            self._project_locks[project_id] = entry
            return entry

    def release_project_lock(self, project_id: str, task_id: str) -> bool:
        with self._lock:
            existing = self._project_locks.get(project_id)
            if existing is None or existing.task_id != task_id:
                return False
            del self._project_locks[project_id]
            self.release_task_resources(task_id)
            return True

    def claim_resources(
        self,
        project_id: str,
        task_id: str,
        agent_id: str,
        resources: list[str],
    ) -> list[ResourceClaimEntry]:
        clean_agent = agent_id.strip() or "operator"
        normalized = [normalize_resource_key(r) for r in resources if r and r.strip()]
        if not normalized:
            return []
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            # Verify all claims first before committing any
            for key in normalized:
                existing = self._resource_claims.get((project_id, key))
                if existing is not None and existing.task_id != task_id:
                    raise ConflictError(
                        f"Resource '{key}' in project '{project_id}' is locked by task '{existing.task_id}' (agent '{existing.agent_id}').",
                        details={
                            "conflictType": "resource_claim",
                            "projectId": project_id,
                            "resourceKey": key,
                            "holderTaskId": existing.task_id,
                            "holderAgentId": existing.agent_id,
                            "requestingTaskId": task_id,
                            "requestingAgentId": clean_agent,
                        },
                    )
            claimed: list[ResourceClaimEntry] = []
            for key in normalized:
                existing = self._resource_claims.get((project_id, key))
                if existing is None:
                    entry = ResourceClaimEntry(
                        project_id=project_id,
                        resource_key=key,
                        task_id=task_id,
                        agent_id=clean_agent,
                        claimed_at=now,
                    )
                    self._resource_claims[(project_id, key)] = entry
                    claimed.append(entry)
                else:
                    claimed.append(existing)
            return claimed

    def release_task_resources(self, task_id: str) -> int:
        with self._lock:
            keys = [k for k, v in self._resource_claims.items() if v.task_id == task_id]
            for k in keys:
                del self._resource_claims[k]
            return len(keys)

    def begin_operation(
        self,
        *,
        task_id: str,
        project_id: str,
        agent_id: str,
        tool_id: str,
        resources: list[str] | None = None,
    ) -> ActiveOperationEntry:
        op_id = f"op-{uuid.uuid4().hex[:10]}"
        entry = ActiveOperationEntry(
            op_id=op_id,
            task_id=task_id,
            project_id=project_id,
            agent_id=agent_id.strip() or "operator",
            tool_id=tool_id,
            resources=[normalize_resource_key(r) for r in (resources or []) if r],
            status="Running",
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._active_operations[op_id] = entry
        return entry

    def finish_operation(self, op_id: str, *, status: str) -> None:
        with self._lock:
            entry = self._active_operations.pop(op_id, None)
            if entry is None:
                return
            entry.status = status
            entry.finished_at = datetime.now(timezone.utc).isoformat()
            self._recent_operations.insert(0, entry)
            if len(self._recent_operations) > self._max_recent_ops:
                self._recent_operations = self._recent_operations[: self._max_recent_ops]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "projectLocks": [v.to_dict() for v in self._project_locks.values()],
                "resourceClaims": [v.to_dict() for v in self._resource_claims.values()],
                "activeOperations": [v.to_dict() for v in self._active_operations.values()],
                "recentOperations": [v.to_dict() for v in self._recent_operations[:25]],
            }
