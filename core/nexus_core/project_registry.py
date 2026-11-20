"""NEXUS Persistent SQLite Project Registry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any
import uuid

from core.nexus_core.errors import ConflictError, NotFoundError, ValidationError
from core.nexus_core.event_manager import EventManager
from core.nexus_core.security import PermissionManager
from core.nexus_core.storage import SQLiteStorageManager
from sdk.python.nexus_sdk import EngineKind, NexusStatus


@dataclass(slots=True)
class ProjectRecord:
    id: str
    name: str
    engine: str
    root_path: str
    engine_version: str
    status: str
    notes: str
    exists_on_disk: bool
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "engine": self.engine,
            "root_path": self.root_path,
            "engine_version": self.engine_version,
            "status": self.status,
            "notes": self.notes,
            "exists_on_disk": self.exists_on_disk,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ProjectRegistry:
    """Manages persistent multi-engine project registrations in SQLite."""

    def __init__(
        self,
        storage: SQLiteStorageManager,
        permissions: PermissionManager,
        events: EventManager,
    ) -> None:
        self.storage = storage
        self.permissions = permissions
        self.events = events

    def _row_to_record(self, row: dict[str, Any]) -> ProjectRecord:
        raw_root = str(row["root_path"])
        return ProjectRecord(
            id=str(row["id"]),
            name=str(row["name"]),
            engine=str(row["engine"]),
            root_path=raw_root,
            engine_version=str(row.get("engine_version") or "Unverified"),
            status=str(row.get("status") or NexusStatus.DISCONNECTED.value),
            notes=str(row.get("notes") or ""),
            exists_on_disk=os.path.isdir(raw_root),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    async def register_project(
        self,
        *,
        name: str,
        engine: str,
        root_path: str,
        engine_version: str = "Unverified",
        notes: str = "",
        require_existing_dir: bool = False,
    ) -> ProjectRecord:
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError("Project name must not be empty.")

        try:
            engine_enum = EngineKind(engine)
        except ValueError as exc:
            raise ValidationError(
                f"Unsupported engine '{engine}'. Expected Unity or Godot.",
                details={"engine": engine},
            ) from exc

        resolved_root = self.permissions.validate_project_registration_path(
            Path(root_path)
        )
        if require_existing_dir and not resolved_root.is_dir():
            raise ValidationError(
                "Declared project directory does not exist on disk.",
                details={"rootPath": str(resolved_root)},
            )

        existing = await self.storage.execute(
            "SELECT id FROM projects WHERE root_path = ?",
            (str(resolved_root),),
        )
        if existing:
            raise ConflictError(
                "A project is already registered for that directory path.",
                details={"rootPath": str(resolved_root)},
            )

        now = datetime.now(timezone.utc).isoformat()
        proj_id = f"proj-{uuid.uuid4().hex[:10]}"
        await self.storage.execute(
            """
            INSERT INTO projects (
                id, name, engine, root_path, engine_version, status, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proj_id,
                clean_name,
                engine_enum.value,
                str(resolved_root),
                engine_version.strip() or "Unverified",
                NexusStatus.DISCONNECTED.value,
                notes.strip(),
                now,
                now,
            ),
        )
        await self.storage.record_audit(
            "daemon",
            "project.register",
            "success",
            target=proj_id,
            detail={"engine": engine_enum.value, "rootPath": str(resolved_root)},
        )
        record = await self.get_project(proj_id)
        await self.events.publish(
            "bridge.status",
            "project_registry",
            {"action": "registered", "projectId": record.id, "engine": record.engine},
        )
        return record

    async def list_projects(self) -> list[ProjectRecord]:
        rows = await self.storage.execute(
            "SELECT * FROM projects ORDER BY updated_at DESC"
        )
        return [self._row_to_record(r) for r in rows]

    async def get_project(self, project_id: str) -> ProjectRecord:
        rows = await self.storage.execute(
            "SELECT * FROM projects WHERE id = ?",
            (project_id,),
        )
        if not rows:
            raise NotFoundError(
                f"Project '{project_id}' was not found.",
                details={"projectId": project_id},
            )
        return self._row_to_record(rows[0])

    async def update_engine_association(
        self, project_id: str, engine: str
    ) -> ProjectRecord:
        try:
            engine_enum = EngineKind(engine)
        except ValueError as exc:
            raise ValidationError(f"Unsupported engine '{engine}'.") from exc

        await self.get_project(project_id)
        now = datetime.now(timezone.utc).isoformat()
        await self.storage.execute(
            "UPDATE projects SET engine = ?, updated_at = ? WHERE id = ?",
            (engine_enum.value, now, project_id),
        )
        await self.storage.record_audit(
            "daemon",
            "project.associate_engine",
            "success",
            target=project_id,
            detail={"engine": engine_enum.value},
        )
        return await self.get_project(project_id)

    async def remove_project(self, project_id: str) -> None:
        await self.get_project(project_id)
        await self.storage.execute(
            "DELETE FROM projects WHERE id = ?",
            (project_id,),
        )
        await self.storage.record_audit(
            "daemon",
            "project.remove",
            "success",
            target=project_id,
        )
