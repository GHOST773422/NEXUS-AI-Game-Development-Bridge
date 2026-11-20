"""NEXUS Engine Manager (Honest Discovery Without Fake Connected Editors)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import time
from typing import Any

from sdk.python.nexus_sdk import EngineAdapter, EngineKind, NexusStatus


@dataclass(slots=True)
class EngineDescriptor:
    id: str
    engine: str
    display_name: str
    detection_status: str
    connection_status: str
    executable_path: str | None
    version: str
    adapter_version: str
    verified_capability_count: int
    contract_method_count: int = 13

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "engine": self.engine,
            "display_name": self.display_name,
            "detection_status": self.detection_status,
            "connection_status": self.connection_status,
            "executable_path": self.executable_path,
            "version": self.version,
            "adapter_version": self.adapter_version,
            "verified_capability_count": self.verified_capability_count,
            "contract_method_count": self.contract_method_count,
        }


class EngineManager:
    """Tracks registered EngineAdapters and performs honest local binary checks."""

    def __init__(self, probe_cache_ttl_sec: float = 15.0) -> None:
        self._adapters: dict[EngineKind, EngineAdapter] = {}
        self._configured_paths: dict[EngineKind, Path] = {}
        self._probe_cache_ttl_sec = probe_cache_ttl_sec
        self._probe_cache: dict[EngineKind, tuple[float, str | None, bool]] = {}

    def register_adapter(self, adapter: EngineAdapter) -> None:
        self._adapters[adapter.engine_kind] = adapter

    def set_engine_executable_path(self, engine: EngineKind, path: Path | None) -> None:
        self._probe_cache.pop(engine, None)
        if path is None:
            self._configured_paths.pop(engine, None)
            return
        self._configured_paths[engine] = path

    def _probe_binary(
        self, engine: EngineKind, candidates: tuple[str, ...]
    ) -> tuple[str | None, bool, bool]:
        """Returns (resolved_path, exists_on_disk, configured_override)."""
        configured = self._configured_paths.get(engine)
        if configured is not None:
            return str(configured), configured.exists(), True
        now = time.monotonic()
        cached = self._probe_cache.get(engine)
        if cached is not None and (now - cached[0]) < self._probe_cache_ttl_sec:
            return cached[1], cached[2], False
        for cmd in candidates:
            found = shutil.which(cmd)
            if found:
                self._probe_cache[engine] = (now, found, True)
                return found, True, False
        self._probe_cache[engine] = (now, None, False)
        return None, False, False

    def list_engines(
        self, connected_adapters: list[dict[str, Any]] | None = None
    ) -> list[EngineDescriptor]:
        unity_bin, unity_found, unity_override = self._probe_binary(
            EngineKind.UNITY, ("Unity.exe", "Unity", "unity-editor")
        )
        godot_bin, godot_found, godot_override = self._probe_binary(
            EngineKind.GODOT, ("Godot_v4.exe", "Godot.exe", "godot4", "godot")
        )

        real_unity = [
            a
            for a in (connected_adapters or [])
            if not a.get("isTestAdapter")
            and a.get("engineKind") == EngineKind.UNITY.value
            and a.get("lifecycleState") == NexusStatus.CONNECTED.value
        ]
        real_godot = [
            a
            for a in (connected_adapters or [])
            if not a.get("isTestAdapter")
            and a.get("engineKind") == EngineKind.GODOT.value
            and a.get("lifecycleState") == NexusStatus.CONNECTED.value
        ]

        unity_connected = len(real_unity) > 0
        godot_connected = len(real_godot) > 0
        unity_info = real_unity[0].get("engineInfo", {}) if unity_connected else {}
        godot_info = real_godot[0].get("engineInfo", {}) if godot_connected else {}

        return [
            EngineDescriptor(
                id="engine-unity",
                engine=EngineKind.UNITY.value,
                display_name="Unity Editor",
                detection_status=(
                    NexusStatus.AVAILABLE.value
                    if (unity_found or unity_connected)
                    else NexusStatus.UNAVAILABLE.value
                ),
                connection_status=(
                    NexusStatus.CONNECTED.value
                    if unity_connected
                    else NexusStatus.DISCONNECTED.value
                ),
                executable_path=unity_bin,
                version=(
                    str(unity_info.get("engineVersion", "Connected"))
                    if unity_connected
                    else (
                        "Configured path not found"
                        if (unity_override and not unity_found)
                        else (
                            "Not detected"
                            if not unity_found
                            else "Binary found (plugin disconnected)"
                        )
                    )
                ),
                adapter_version="1.0.0 (com.nexus.bridge)",
                verified_capability_count=sum(
                    int(a.get("registeredToolCount", 0)) for a in real_unity
                ),
            ),
            EngineDescriptor(
                id="engine-godot",
                engine=EngineKind.GODOT.value,
                display_name="Godot Engine 4.x",
                detection_status=(
                    NexusStatus.AVAILABLE.value
                    if (godot_found or godot_connected)
                    else NexusStatus.UNAVAILABLE.value
                ),
                connection_status=(
                    NexusStatus.CONNECTED.value
                    if godot_connected
                    else NexusStatus.DISCONNECTED.value
                ),
                executable_path=godot_bin,
                version=(
                    str(godot_info.get("engineVersion", "Connected"))
                    if godot_connected
                    else (
                        "Configured path not found"
                        if (godot_override and not godot_found)
                        else (
                            "Not detected"
                            if not godot_found
                            else "Binary found (plugin disconnected)"
                        )
                    )
                ),
                adapter_version="0.1.0 (nexus_bridge)",
                verified_capability_count=sum(
                    int(a.get("registeredToolCount", 0)) for a in real_godot
                ),
            ),
        ]

    @property
    def connected_adapter_count(self) -> int:
        return len(self._adapters)
