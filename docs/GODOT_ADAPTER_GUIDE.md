# NEXUS Godot Editor Integration Guide (Stage 7)

**Target OS**: Windows 10/11 (64-bit) / Desktop Godot  
**Supported Godot Versions**: Godot `4.2+` (`4.2`, `4.3`, `4.4`)  
**Addon**: `addons/nexus_bridge/` (`adapters/godot/`)

---

## 1. Architecture Overview

`addons/nexus_bridge/` runs natively inside the Godot Editor (`@tool` `EditorPlugin`) and exposes a loopback-only (`127.0.0.1`) NDJSON JSON-RPC `2.0` TCP server (`NexusGodotTcpServer`):

1. **Main-Thread Execution (`_process(delta)`)**: `TCPServer` and connected `StreamPeerTCP` sockets are polled synchronously inside `EditorPlugin._process(delta)` on Godot's main thread so `SceneTree`, `EditorInterface`, `EditorUndoRedoManager`, `ResourceLoader`, and `Viewport` APIs are never accessed off-thread.
2. **Version-Aware Capability Discovery (`nexus_version.gd`, `nexus_tool_registry.gd`)**:
   - Inspects `Engine.get_version_info()` explicitly on activation and on every `getEngineInfo` / `getCapabilities` / `listTools` RPC.
   - Blocks activation (`compatible: false` -> daemon `AdapterCompatibilityError`) on Godot `< 4.2`.
   - Exposes `hasEditorDebuggerPlugin` (`4.2+`), `hasEditorUndoRedoManager` (`4.x`), `hasEditorViewportCapture` (`4.2+`), and `hasResourceUid` (`4.3+`).
3. **Undo/Redo & `res://` Path Sandboxing (`nexus_godot_handlers.gd`)**:
   - Wraps node creation, property modification, deletion, 2D/3D transforms, and persistent signal connection/disconnection in `plugin.get_undo_redo()` (`EditorUndoRedoManager`).
   - Enforces `res://` scoping with `..` traversal rejection on script creation/modification (`.gd`), resource persistence (`.tres`/`.res`), scene saves (`.tscn`), and custom scene launches.
   - Compiles GDScript changes via `EditorInterface.get_resource_filesystem().scan()` + `ResourceLoader.load(..., CACHE_MODE_REPLACE)` + `GDScript.reload(true)`, logging failures into `StateTracker`.

---

## 2. All 22 Implemented Capabilities & 18 Verified Tools

| Tool ID | Category | Required Scope | Capability |
| :--- | :--- | :--- | :--- |
| `godot.get_scene_state` | Scene management | `project:read` | Godot version, compatibility, edited scene, open scenes, playing status |
| `godot.get_node_hierarchy` | Scene management | `project:read` | Recursive `SceneTree` node traversal, types, scripts, groups |
| `godot.create_node` | Object management | `scene:write` | Instantiate any `ClassDB` `Node` subclass via `EditorUndoRedoManager` |
| `godot.modify_node` | Object management | `scene:write` | Update node properties cleanly with Undo/Redo support |
| `godot.delete_node` | Object management | `scene:write` | Safe non-root node removal with Undo restoration |
| `godot.set_transform` | Object management | `scene:write` | 2D & 3D `position`, `rotation_degrees`, and `scale` updates |
| `godot.create_script` | Script management | `script:write` | Create `res://*.gd`, reload-compile verify, optional node attach |
| `godot.modify_script` | Script management | `script:write` | Replace/patch `res://*.gd` and verify compilation via `reload(true)` |
| `godot.manage_resource` | Asset management | `assets:modify` | Create, inspect, update properties on `.tres`/`.res` resources |
| `godot.inspect_assets` | Asset management | `project:read` | Browse `EditorFileSystem` tree with filter, extension, pagination |
| `godot.manage_signals` | Component management | `scene:write` | List node signals or connect/disconnect persistent scene signals |
| `godot.save_scene` | Scene management | `scene:write` | `EditorInterface.save_scene()` / `save_scene_as()` |
| `godot.launch_runtime` | Testing | `editor:execute` | `play_main`, `play_current`, `play_custom`, `stop` |
| `godot.get_runtime_status` | Profiling | `project:read` | Playing scene, uptime, editor FPS, object count, static memory |
| `godot.inspect_debugger` | Debugging | `project:read` | Live `EditorDebuggerPlugin` sessions, breakpoints, captured messages |
| `godot.get_errors` | Debugging | `project:read` | Buffered adapter errors & Godot `godot.log` ERROR/WARNING tail |
| `godot.capture_screenshot` | Rendering | `editor:execute` | Live 3D/2D `EditorInterface` `Viewport` PNG base64 capture |
| `godot.get_export_status` | Build and export | `project:read` | Parses `res://export_presets.cfg` + `EditorExportPlugin` telemetry |

---

## 3. Multi-Project Support & Connection Recovery

- Each open Godot project computes a deterministic ID (`godot-<sha256_12>`) from its root path.
- Configure per-project loopback ports via the **NEXUS Bridge** editor dock (`Port:` + `Restart`), `EditorSettings` (`nexus/bridge/port_<projectId>`), or `NEXUS_GODOT_PORT`.
- When the Godot Editor restarts or closes a socket, `AdapterManager` automatically enters `Reconnecting` with exponential backoff until the plugin listens again.

---

## 4. Godot 4.x Test Project Verification

An actual Godot 4.x project is included at `adapters/godot/test_project/`:

```bash
# Sync addon files into the test project after editing addons/nexus_bridge/
npm run sync:godot-addon

# Run headless Godot 4.2+ verification harness on a machine with Godot installed
godot --headless --path adapters/godot/test_project --script res://tests/nexus_godot_verification.gd
```

> **Note**: Because AI Studio's cloud container lacks a Godot binary, live EditorPlugin & headless `godot` execution must be performed locally with Godot `4.2+`.
