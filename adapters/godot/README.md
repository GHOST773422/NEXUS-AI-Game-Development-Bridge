# NEXUS Godot GDScript Adapter (`adapters/godot/`)

Native Godot `4.2+` `EditorPlugin` (`addons/nexus_bridge/`) exposing a loopback-only (`127.0.0.1:47202`) NDJSON JSON-RPC `2.0` server integrated with NEXUS's Universal Adapter Framework.

## Modules (`addons/nexus_bridge/`)
- `plugin.cfg` & `plugin.gd`: `EditorPlugin` lifecycle, `EditorDebuggerPlugin` / `EditorExportPlugin` registration, `_process(delta)` socket polling, per-project port persistence (`NEXUS_GODOT_PORT` / `EditorSettings`).
- `nexus_version.gd`: Explicit `Engine.get_version_info()` `4.2+` compatibility checks, feature flags (`hasEditorDebuggerPlugin`, `hasEditorViewportCapture`, `hasResourceUid`), deterministic `godot-<hash>` project ID.
- `nexus_tool_registry.gd`: Version-aware capability discovery and 18 typed Godot tools across 22 capabilities.
- `nexus_godot_handlers.gd`: Main-thread `EditorInterface`, `EditorUndoRedoManager`, `ClassDB`, `GDScript.reload()`, `ResourceSaver`, `EditorFileSystem`, `Viewport` PNG capture, and `export_presets.cfg` inspection.
- `nexus_state_plugins.gd`: `EditorDebuggerPlugin`, `EditorExportPlugin`, error ring buffer, and `godot.log` tail reader.
- `nexus_tcp_server.gd` & `nexus_dock.gd`: Non-blocking `TCPServer` NDJSON JSON-RPC `2.0` server and **NEXUS Bridge** editor dock UI.

## Test Project (`adapters/godot/test_project/`)
Pre-configured Godot 4.x project (`Main` 3D scene, `TestActor` script/signal, Windows export preset, and `tests/nexus_godot_verification.gd`). Run `npm run sync:godot-addon` after editing addon files to keep `test_project/addons/nexus_bridge/` in sync. See `docs/GODOT_ADAPTER_GUIDE.md`.
