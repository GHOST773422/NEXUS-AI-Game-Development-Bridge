"""NEXUS Core Diagnostics Service."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import sys
import time
from typing import Any

from core.nexus_core.config import APP_VERSION, NexusDaemonConfig
from core.nexus_core.engine_manager import EngineManager
from core.nexus_core.project_registry import ProjectRegistry
from core.nexus_core.storage import SQLiteStorageManager


class DiagnosticsService:
    """Evaluates real daemon health, SQLite integrity, and project directory validity."""

    def __init__(
        self,
        *,
        config: NexusDaemonConfig,
        storage: SQLiteStorageManager,
        projects: ProjectRegistry,
        engines: EngineManager,
        adapters: Any | None = None,
        started_at: str | None,
        integrity_cache_ttl_sec: float = 10.0,
    ) -> None:
        self.config = config
        self.storage = storage
        self.projects = projects
        self.engines = engines
        self.adapters = adapters
        self.started_at = started_at
        self._integrity_cache_ttl_sec = integrity_cache_ttl_sec
        self._cached_integrity: tuple[int, float, str] | None = None
        self._cached_bundled_adapters: dict[str, Any] | None = None

    def _inspect_bundled_adapters(self) -> dict[str, Any]:
        if self._cached_bundled_adapters is not None:
            return self._cached_bundled_adapters
        repo_root = Path(__file__).resolve().parents[2]
        unity_manifest = repo_root / "adapters" / "unity" / "nexus-adapter.manifest.json"
        godot_plugin = repo_root / "adapters" / "godot" / "addons" / "nexus_bridge" / "plugin.cfg"
        self._cached_bundled_adapters = {
            "unityPackagePresent": unity_manifest.exists(),
            "godotPluginPresent": godot_plugin.exists(),
        }
        return self._cached_bundled_adapters

    async def _get_cached_integrity(self) -> str:
        if not self.storage.is_initialized:
            self._cached_integrity = None
            return "not_initialized"
        now_mono = time.monotonic()
        epoch = self.storage.write_epoch
        cached = self._cached_integrity
        if (
            cached is not None
            and cached[0] == epoch
            and (now_mono - cached[1]) < self._integrity_cache_ttl_sec
        ):
            return cached[2]
        result = await self.storage.integrity_check()
        self._cached_integrity = (self.storage.write_epoch, now_mono, result)
        return result

    async def collect(self) -> dict[str, Any]:
        sqlite_integrity = await self._get_cached_integrity()
        project_records = (
            await self.projects.list_projects()
            if self.storage.is_initialized
            else []
        )
        missing_dirs = [p.id for p in project_records if not p.exists_on_disk]

        log_path = self.config.log_file
        log_exists = bool(log_path and log_path.exists())
        log_bytes = log_path.stat().st_size if log_path and log_exists else 0
        connected_adapters = (
            self.adapters.list_adapters() if self.adapters is not None else None
        )

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": APP_VERSION,
            "startedAt": self.started_at,
            "pid": os.getpid(),
            "runtime": {
                "pythonVersion": sys.version.split()[0],
                "meetsTargetPython312": sys.version_info >= (3, 12),
                "os": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "isWindows": os.name == "nt",
            },
            "config": self.config.to_safe_dict(),
            "logging": {
                "logFilePath": str(log_path) if log_path is not None else None,
                "logFileExists": log_exists,
                "logFileBytes": log_bytes,
            },
            "storage": {
                "initialized": self.storage.is_initialized,
                "integrity": sqlite_integrity,
            },
            "projects": {
                "registeredCount": len(project_records),
                "missingDirectoryIds": missing_dirs,
            },
            "bundledAdapters": self._inspect_bundled_adapters(),
            "engines": [
                e.to_dict()
                for e in self.engines.list_engines(connected_adapters=connected_adapters)
            ],
        }
