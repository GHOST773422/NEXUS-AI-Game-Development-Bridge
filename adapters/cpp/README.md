# NEXUS Native C++ Adapter Target (Future Engine Support)

`adapters/cpp/nexus-adapter.manifest.json` defines the language-neutral extension contract for native **C++** engine plugins (such as Unreal Engine Editor modules or custom C++ renderers).

## Integration Requirements

1. Implement a loopback TCP listener on `127.0.0.1:47203` (or spawn via `stdio`) reading UTF-8 NDJSON JSON-RPC `2.0` frames.
2. Implement all 11 canonical `UniversalEngineAdapter` RPC methods defined in `docs/ADAPTER_PROTOCOL.md`.
3. Never assume Python is embedded inside the C++ host engine; `AdapterManager` communicates exclusively across the local JSON-RPC wire boundary.
