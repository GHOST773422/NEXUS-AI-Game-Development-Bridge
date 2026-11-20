"""NEXUS Stage 9 Checkpoint, File Change Manifest & Selective Rollback Manager."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
import uuid

from core.nexus_core.errors import NotFoundError
from core.nexus_core.security import PermissionManager
from core.nexus_core.storage import SQLiteStorageManager


class CheckpointManager:
    """Captures sandboxed snapshots, computes file change manifests, and performs selective rollbacks."""

    def __init__(
        self,
        *,
        checkpoints_dir: Path,
        storage: SQLiteStorageManager,
        permissions: PermissionManager,
    ) -> None:
        self.checkpoints_dir = Path(checkpoints_dir)
        self.storage = storage
        self.permissions = permissions

    def _resolve_project_file(self, project_root: Path, raw_ref: str) -> Path | None:
        clean = raw_ref.strip().replace("\\", "/")
        if not clean:
            return None
        return self.permissions.resolve_engine_resource_path(project_root, clean)

    async def create_checkpoint(
        self,
        *,
        task_id: str,
        project_id: str,
        project_root: Path,
        target_paths: list[str],
        engine_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        checkpoint_id = f"chk-{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc).isoformat()
        ckpt_dir = self.checkpoints_dir / checkpoint_id
        files_dir = ckpt_dir / "files"

        resolved_root = project_root.expanduser().resolve()
        entries: list[dict[str, Any]] = []
        seen_paths: set[str] = set()

        def _capture_files() -> None:
            files_dir.mkdir(parents=True, exist_ok=True)
            for idx, ref in enumerate(target_paths):
                resolved_target = self._resolve_project_file(resolved_root, ref)
                if resolved_target is None:
                    continue
                rel_posix = resolved_target.relative_to(resolved_root).as_posix()
                if rel_posix in seen_paths:
                    continue
                seen_paths.add(rel_posix)

                if resolved_target.is_file():
                    raw_bytes = resolved_target.read_bytes()
                    digest = hashlib.sha256(raw_bytes).hexdigest()
                    backup_rel = f"{idx:03d}_{resolved_target.name}.bak"
                    backup_path = files_dir / backup_rel
                    backup_path.write_bytes(raw_bytes)
                    entries.append(
                        {
                            "relativePath": rel_posix,
                            "resourceRef": ref,
                            "existed": True,
                            "beforeHash": digest,
                            "sha256": digest,
                            "sizeBytes": len(raw_bytes),
                            "backupFile": backup_rel,
                        }
                    )
                else:
                    entries.append(
                        {
                            "relativePath": rel_posix,
                            "resourceRef": ref,
                            "existed": False,
                            "beforeHash": None,
                            "sha256": None,
                            "sizeBytes": 0,
                            "backupFile": None,
                        }
                    )

            manifest = {
                "checkpointId": checkpoint_id,
                "taskId": task_id,
                "projectId": project_id,
                "projectRoot": str(resolved_root),
                "createdAt": now,
                "engineState": engine_state or {},
                "files": entries,
            }
            (ckpt_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8"
            )

        await asyncio.to_thread(_capture_files)

        await self.storage.execute(
            """
            INSERT INTO checkpoints (id, task_id, project_id, snapshot_path, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (checkpoint_id, task_id, project_id, str(ckpt_dir / "manifest.json"), now),
        )
        await self.storage.record_audit(
            "orchestrator",
            "checkpoint.create",
            "success",
            target=checkpoint_id,
            detail={"taskId": task_id, "projectId": project_id, "trackedFiles": len(entries)},
        )
        return {
            "checkpointId": checkpoint_id,
            "taskId": task_id,
            "projectId": project_id,
            "snapshotPath": str(ckpt_dir / "manifest.json"),
            "trackedFiles": len(entries),
            "createdAt": now,
        }

    async def finalize_file_change_manifest(
        self,
        checkpoint_id: str,
        *,
        project_root: Path,
        extra_paths: list[str] | None = None,
    ) -> dict[str, Any]:
        """Computes afterHash & change classifications for tracked + extra modified paths."""
        ckpt = await self.get_checkpoint(checkpoint_id)
        manifest = ckpt.get("manifest") or {}
        manifest_path = Path(ckpt["snapshotPath"])
        resolved_root = project_root.expanduser().resolve()

        def _compute() -> dict[str, Any]:
            by_rel: dict[str, dict[str, Any]] = {}
            for entry in manifest.get("files", []):
                rel = str(entry.get("relativePath", "")).strip()
                if rel:
                    by_rel[rel] = dict(entry)

            for raw_ref in extra_paths or []:
                resolved_target = self._resolve_project_file(resolved_root, raw_ref)
                if resolved_target is None:
                    continue
                rel = resolved_target.relative_to(resolved_root).as_posix()
                if rel not in by_rel:
                    by_rel[rel] = {
                        "relativePath": rel,
                        "resourceRef": raw_ref,
                        "existed": False,
                        "beforeHash": None,
                        "sha256": None,
                        "sizeBytes": 0,
                        "backupFile": None,
                    }

            changes: list[dict[str, Any]] = []
            for rel, entry in sorted(by_rel.items()):
                target_path = self.permissions.assert_path_within_project(
                    resolved_root, resolved_root / rel
                )
                existed_before = bool(entry.get("existed"))
                before_hash = entry.get("beforeHash") or entry.get("sha256")
                if target_path.is_file():
                    raw_bytes = target_path.read_bytes()
                    after_hash = hashlib.sha256(raw_bytes).hexdigest()
                    after_size = len(raw_bytes)
                    if not existed_before:
                        change_kind = "created"
                    elif before_hash != after_hash:
                        change_kind = "modified"
                    else:
                        change_kind = "unchanged"
                else:
                    after_hash = None
                    after_size = 0
                    change_kind = "deleted" if existed_before else "absent"

                changes.append(
                    {
                        "relativePath": rel,
                        "resourceRef": entry.get("resourceRef", rel),
                        "change": change_kind,
                        "beforeHash": before_hash,
                        "afterHash": after_hash,
                        "afterSizeBytes": after_size,
                        "reversible": bool(entry.get("backupFile")) or (not existed_before),
                    }
                )

            change_manifest = {
                "checkpointId": checkpoint_id,
                "taskId": ckpt["taskId"],
                "projectId": ckpt["projectId"],
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "totalTracked": len(changes),
                "changedCount": sum(
                    1 for c in changes if c["change"] in {"created", "modified", "deleted"}
                ),
                "files": changes,
            }
            (manifest_path.parent / "file_change_manifest.json").write_text(
                json.dumps(change_manifest, indent=2, ensure_ascii=True), encoding="utf-8"
            )
            return change_manifest

        return await asyncio.to_thread(_compute)

    async def get_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        rows = await self.storage.execute(
            "SELECT * FROM checkpoints WHERE id = ?", (checkpoint_id,)
        )
        if not rows:
            raise NotFoundError(f"Checkpoint '{checkpoint_id}' was not found.")
        row = rows[0]
        manifest_path = Path(row["snapshot_path"])
        manifest: dict[str, Any] = {}
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        change_manifest_path = manifest_path.parent / "file_change_manifest.json"
        change_manifest: dict[str, Any] | None = None
        if change_manifest_path.is_file():
            change_manifest = json.loads(change_manifest_path.read_text(encoding="utf-8"))
        return {
            "checkpointId": row["id"],
            "taskId": row["task_id"],
            "projectId": row["project_id"],
            "snapshotPath": row["snapshot_path"],
            "createdAt": row["created_at"],
            "manifest": manifest,
            "fileChangeManifest": change_manifest,
        }

    async def selective_rollback(
        self,
        checkpoint_id: str,
        *,
        project_root: Path,
        target_files: list[str] | None = None,
    ) -> dict[str, Any]:
        """Restores either all tracked files or a caller-selected subset cleanly inside project_root."""
        ckpt = await self.get_checkpoint(checkpoint_id)
        manifest = ckpt.get("manifest") or {}
        manifest_path = Path(ckpt["snapshotPath"])
        files_dir = manifest_path.parent / "files"
        resolved_root = project_root.expanduser().resolve()

        selected_rel_paths: set[str] | None = None
        if target_files:
            selected_rel_paths = set()
            for raw_ref in target_files:
                resolved = self._resolve_project_file(resolved_root, raw_ref)
                if resolved is not None:
                    selected_rel_paths.add(resolved.relative_to(resolved_root).as_posix())

        restored_files: list[str] = []
        removed_files: list[str] = []
        skipped_files: list[str] = []

        def _restore_sync() -> None:
            for entry in manifest.get("files", []):
                rel = str(entry.get("relativePath", "")).strip()
                if not rel:
                    continue
                if selected_rel_paths is not None and rel not in selected_rel_paths:
                    skipped_files.append(rel)
                    continue
                target_path = self.permissions.assert_path_within_project(
                    resolved_root, resolved_root / rel
                )
                if entry.get("existed"):
                    backup_rel = entry.get("backupFile")
                    if not backup_rel:
                        continue
                    backup_path = files_dir / str(backup_rel)
                    if backup_path.is_file():
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        target_path.write_bytes(backup_path.read_bytes())
                        restored_files.append(rel)
                else:
                    if target_path.is_file():
                        target_path.unlink()
                        removed_files.append(rel)

        await asyncio.to_thread(_restore_sync)

        await self.storage.record_audit(
            "orchestrator",
            "checkpoint.selective_rollback" if selected_rel_paths is not None else "checkpoint.restore",
            "success",
            target=checkpoint_id,
            detail={
                "selective": selected_rel_paths is not None,
                "restoredFiles": restored_files,
                "removedFiles": removed_files,
                "skippedFiles": skipped_files,
            },
        )
        return {
            "checkpointId": checkpoint_id,
            "selective": selected_rel_paths is not None,
            "restoredFiles": restored_files,
            "removedFiles": removed_files,
            "skippedFiles": skipped_files,
            "restoredAt": datetime.now(timezone.utc).isoformat(),
        }

    async def restore_checkpoint(
        self,
        checkpoint_id: str,
        *,
        project_root: Path,
    ) -> dict[str, Any]:
        return await self.selective_rollback(
            checkpoint_id, project_root=project_root, target_files=None
        )
