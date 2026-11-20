"""NEXUS Universal Engine Adapter Framework."""

from core.nexus_core.adapters.interface import (
    ProtocolEngineAdapter,
    UniversalEngineAdapter,
    build_transport_for_manifest,
)
from core.nexus_core.adapters.manager import (
    AdapterCapabilityRegistry,
    AdapterErrorRecord,
    AdapterLifecycleState,
    AdapterManager,
    AdapterRuntimeRecord,
    ReconnectionPolicy,
)
from core.nexus_core.adapters.manifest import (
    DAEMON_ADAPTER_PROTOCOL_VERSION,
    MANIFEST_SCHEMA_VERSION,
    AdapterManifest,
    AdapterTransportSpec,
    parse_adapter_manifest,
    parse_semver,
    validate_adapter_compatibility,
)
from core.nexus_core.adapters.protocol import (
    ADAPTER_PROTOCOL_VERSION,
    ADAPTER_REQUIRED_METHODS,
    JsonRpcAdapterTransport,
    StdioAdapterTransport,
    TcpLoopbackAdapterTransport,
)

__all__ = [
    "ADAPTER_PROTOCOL_VERSION",
    "ADAPTER_REQUIRED_METHODS",
    "AdapterCapabilityRegistry",
    "AdapterErrorRecord",
    "AdapterLifecycleState",
    "AdapterManager",
    "AdapterManifest",
    "AdapterRuntimeRecord",
    "AdapterTransportSpec",
    "DAEMON_ADAPTER_PROTOCOL_VERSION",
    "JsonRpcAdapterTransport",
    "MANIFEST_SCHEMA_VERSION",
    "ProtocolEngineAdapter",
    "ReconnectionPolicy",
    "StdioAdapterTransport",
    "TcpLoopbackAdapterTransport",
    "UniversalEngineAdapter",
    "build_transport_for_manifest",
    "parse_adapter_manifest",
    "parse_semver",
    "validate_adapter_compatibility",
]
