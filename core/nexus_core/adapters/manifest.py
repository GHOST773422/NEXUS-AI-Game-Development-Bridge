"""NEXUS Language-Neutral Adapter & Plugin Manifest Specification + Validator."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
from pathlib import Path
import re
from typing import Any

from core.nexus_core.errors import AdapterCompatibilityError, ValidationError
from sdk.python.nexus_sdk import PermissionScope

MANIFEST_SCHEMA_VERSION = "1.0"
DAEMON_ADAPTER_PROTOCOL_VERSION = "1.0.0"

SUPPORTED_RUNTIME_LANGUAGES = frozenset(
    {"C#", "GDScript", "C++", "Python", "NodeTS", "Rust", "Other"}
)
SUPPORTED_ENGINE_KINDS = frozenset(
    {"Unity", "Godot", "Unreal", "Custom", "TestHarness"}
)
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_ADAPTER_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{2,80}$")


def parse_semver(raw: str) -> tuple[int, int, int]:
    match = _SEMVER_RE.match(raw.strip())
    if not match:
        raise AdapterCompatibilityError(
            f"Invalid semantic version '{raw}'; expected MAJOR.MINOR.PATCH.",
            details={"version": raw},
        )
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


@dataclass(slots=True)
class AdapterTransportSpec:
    kind: str  # "stdio" | "tcp-loopback"
    command: list[str] = field(default_factory=list)
    host: str = "127.0.0.1"
    port: int = 0
    working_dir: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AdapterManifest:
    manifest_version: str
    adapter_id: str
    display_name: str
    version: str
    runtime_language: str
    engine_kind: str
    is_test_adapter: bool
    protocol_version: str
    min_daemon_protocol_version: str
    max_daemon_protocol_version: str
    transport: AdapterTransportSpec
    entrypoint: str
    capabilities: list[str] = field(default_factory=list)
    requested_permissions: list[str] = field(default_factory=list)
    supported_engine_versions: list[str] = field(default_factory=list)
    checksum_sha256: str | None = None
    author: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifestVersion": self.manifest_version,
            "adapterId": self.adapter_id,
            "displayName": self.display_name,
            "version": self.version,
            "runtimeLanguage": self.runtime_language,
            "engineKind": self.engine_kind,
            "isTestAdapter": self.is_test_adapter,
            "protocolVersion": self.protocol_version,
            "minDaemonProtocolVersion": self.min_daemon_protocol_version,
            "maxDaemonProtocolVersion": self.max_daemon_protocol_version,
            "transport": self.transport.to_dict(),
            "entrypoint": self.entrypoint,
            "capabilities": list(self.capabilities),
            "requestedPermissions": list(self.requested_permissions),
            "supportedEngineVersions": list(self.supported_engine_versions),
            "checksumSha256": self.checksum_sha256,
            "author": self.author,
            "description": self.description,
        }


def parse_adapter_manifest(raw: dict[str, Any]) -> AdapterManifest:
    if not isinstance(raw, dict):
        raise ValidationError("Adapter manifest must be a JSON object.")

    adapter_id = str(raw.get("adapterId", "")).strip()
    if not _ADAPTER_ID_RE.match(adapter_id):
        raise ValidationError(
            "adapterId must be 3-80 alphanumeric, dot, underscore, or hyphen characters.",
            details={"adapterId": adapter_id},
        )

    transport_raw = raw.get("transport")
    if not isinstance(transport_raw, dict):
        raise ValidationError("Manifest 'transport' object is required.")

    t_kind = str(transport_raw.get("kind", "")).strip()
    if t_kind not in {"stdio", "tcp-loopback"}:
        raise ValidationError(
            "Manifest transport.kind must be 'stdio' or 'tcp-loopback'.",
            details={"kind": t_kind},
        )

    raw_cmd = transport_raw.get("command", [])
    command = [str(c) for c in raw_cmd] if isinstance(raw_cmd, list) else []
    transport = AdapterTransportSpec(
        kind=t_kind,
        command=command,
        host=str(transport_raw.get("host", "127.0.0.1")).strip(),
        port=int(transport_raw.get("port", 0) or 0),
        working_dir=(
            str(transport_raw["workingDir"])
            if transport_raw.get("workingDir")
            else None
        ),
    )

    is_test = bool(raw.get("isTestAdapter", False))
    engine_kind = str(raw.get("engineKind", "")).strip()
    if engine_kind == "TestHarness" and not is_test:
        raise AdapterCompatibilityError(
            "TestHarness adapters must explicitly set isTestAdapter=true."
        )

    return AdapterManifest(
        manifest_version=str(raw.get("manifestVersion", "")).strip(),
        adapter_id=adapter_id,
        display_name=str(raw.get("displayName", "")).strip(),
        version=str(raw.get("version", "")).strip(),
        runtime_language=str(raw.get("runtimeLanguage", "")).strip(),
        engine_kind=engine_kind,
        is_test_adapter=is_test,
        protocol_version=str(raw.get("protocolVersion", "")).strip(),
        min_daemon_protocol_version=str(raw.get("minDaemonProtocolVersion", "1.0.0")).strip(),
        max_daemon_protocol_version=str(raw.get("maxDaemonProtocolVersion", "1.99.99")).strip(),
        transport=transport,
        entrypoint=str(raw.get("entrypoint", "")).strip(),
        capabilities=[str(c) for c in (raw.get("capabilities") or [])],
        requested_permissions=[str(p) for p in (raw.get("requestedPermissions") or [])],
        supported_engine_versions=[str(v) for v in (raw.get("supportedEngineVersions") or [])],
        checksum_sha256=(
            str(raw["checksumSha256"]).strip() if raw.get("checksumSha256") else None
        ),
        author=str(raw.get("author", "")),
        description=str(raw.get("description", "")),
    )


def validate_adapter_compatibility(
    manifest: AdapterManifest,
    *,
    daemon_protocol_version: str = DAEMON_ADAPTER_PROTOCOL_VERSION,
    base_dir: Path | None = None,
) -> None:
    """Validates schema, SemVer ranges, loopback transport rules, permissions, and checksum."""
    if manifest.manifest_version != MANIFEST_SCHEMA_VERSION:
        raise AdapterCompatibilityError(
            f"Unsupported manifestVersion '{manifest.manifest_version}'; expected '{MANIFEST_SCHEMA_VERSION}'.",
            details={"manifestVersion": manifest.manifest_version},
        )
    if not manifest.display_name:
        raise AdapterCompatibilityError("Adapter displayName cannot be empty.")
    if not manifest.entrypoint:
        raise AdapterCompatibilityError("Adapter entrypoint cannot be empty.")

    parse_semver(manifest.version)
    adapter_proto = parse_semver(manifest.protocol_version)
    min_proto = parse_semver(manifest.min_daemon_protocol_version)
    max_proto = parse_semver(manifest.max_daemon_protocol_version)
    daemon_proto = parse_semver(daemon_protocol_version)

    if adapter_proto[0] != daemon_proto[0]:
        raise AdapterCompatibilityError(
            f"Adapter protocol major version {adapter_proto[0]} is incompatible with daemon protocol {daemon_protocol_version}.",
            details={
                "adapterProtocol": manifest.protocol_version,
                "daemonProtocol": daemon_protocol_version,
            },
        )
    if not (min_proto <= daemon_proto <= max_proto):
        raise AdapterCompatibilityError(
            f"Daemon protocol {daemon_protocol_version} is outside adapter supported range [{manifest.min_daemon_protocol_version}, {manifest.max_daemon_protocol_version}].",
            details={
                "min": manifest.min_daemon_protocol_version,
                "max": manifest.max_daemon_protocol_version,
                "daemonProtocol": daemon_protocol_version,
            },
        )

    if manifest.runtime_language not in SUPPORTED_RUNTIME_LANGUAGES:
        raise AdapterCompatibilityError(
            f"Unsupported runtimeLanguage '{manifest.runtime_language}'.",
            details={"runtimeLanguage": manifest.runtime_language},
        )
    if manifest.engine_kind not in SUPPORTED_ENGINE_KINDS:
        raise AdapterCompatibilityError(
            f"Unsupported engineKind '{manifest.engine_kind}'.",
            details={"engineKind": manifest.engine_kind},
        )
    if manifest.is_test_adapter and manifest.engine_kind in {"Unity", "Godot", "Unreal"}:
        raise AdapterCompatibilityError(
            "A test adapter cannot claim engineKind Unity/Godot/Unreal; use 'TestHarness' or 'Custom'."
        )

    if manifest.transport.kind == "tcp-loopback":
        if manifest.transport.host not in LOOPBACK_HOSTS:
            raise AdapterCompatibilityError(
                f"Adapter TCP transport host '{manifest.transport.host}' must be loopback.",
                details={"host": manifest.transport.host},
            )
        if manifest.transport.port <= 0 or manifest.transport.port > 65535:
            raise AdapterCompatibilityError(
                "Adapter tcp-loopback transport requires a valid port (1..65535).",
                details={"port": manifest.transport.port},
            )
    elif manifest.transport.kind == "stdio":
        if not manifest.transport.command:
            raise AdapterCompatibilityError("Adapter stdio transport requires a non-empty command list.")

    valid_scopes = {scope.value for scope in PermissionScope}
    for perm in manifest.requested_permissions:
        if perm not in valid_scopes:
            raise AdapterCompatibilityError(
                f"Unknown requestedPermission scope '{perm}'.",
                details={"permission": perm},
            )

    clean_entrypoint = manifest.entrypoint.replace("\\", "/")
    if clean_entrypoint.startswith("/") or ".." in clean_entrypoint.split("/"):
        raise AdapterCompatibilityError(
            f"Adapter entrypoint '{manifest.entrypoint}' cannot contain absolute paths or traversal segments.",
            details={"entrypoint": manifest.entrypoint},
        )

    if base_dir is not None:
        resolved_base = base_dir.expanduser().resolve()
        target = (resolved_base / manifest.entrypoint).resolve()
        if resolved_base not in target.parents and target != resolved_base:
            raise AdapterCompatibilityError(
                f"Adapter entrypoint '{manifest.entrypoint}' escapes adapter directory.",
                details={"entrypoint": manifest.entrypoint},
            )
        if manifest.checksum_sha256:
            if not target.is_file():
                raise AdapterCompatibilityError(
                    f"Adapter entrypoint '{manifest.entrypoint}' missing for SHA-256 verification.",
                    details={"entrypoint": manifest.entrypoint},
                )
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            if digest.lower() != manifest.checksum_sha256.lower():
                raise AdapterCompatibilityError(
                    f"Checksum mismatch for adapter entrypoint '{manifest.entrypoint}'.",
                    details={"expected": manifest.checksum_sha256, "actual": digest},
                )
