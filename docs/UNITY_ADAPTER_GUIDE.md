# NEXUS Unity Editor Integration Guide (Stage 6)

**Target OS**: Windows 10/11 (64-bit)  
**Supported Unity Versions**: Unity `2022.3 LTS`, Unity `6000.0 LTS`  
**Package**: `com.nexus.bridge` (`adapters/unity/`)

---

## 1. Architecture Overview

`com.nexus.bridge` runs inside the Unity Editor (`Editor` asmdef only, excluded from runtime builds) and exposes a loopback-only (`127.0.0.1`) NDJSON JSON-RPC `2.0` TCP server (`NexusUnityTcpServer`):

1. **Main Thread Marshaling (`NexusMainThreadDispatcher`)**: Background `TcpListener` sockets enqueue Unity Editor operations onto a thread-safe `ConcurrentQueue`, drained by `EditorApplication.update`. Background threads never touch Unity Engine/Editor APIs directly.
2. **Lifecycle & Domain Reload Safety (`NexusUnityBridgeEntrypoint`)**: Uses `[InitializeOnLoad]`, `AssemblyReloadEvents.beforeAssemblyReload`, `AssemblyReloadEvents.afterAssemblyReload`, and `EditorApplication.quitting` to cleanly stop and restart the socket across C# recompilations.
3. **Compilation, Play Mode & Path Sandboxing Guards (`NexusUnityHandlers`)**:
   - Blocks scene/object/component/script/asset mutations when `EditorApplication.isCompiling` or `EditorApplication.isUpdating` is true.
   - Blocks script writes and scene saves while `EditorApplication.isPlaying` is true.
   - Blocks entering Play Mode while compilation/import is active.
   - Restricts script (`*.cs`) and asset paths strictly to `Assets/`, rejecting `..` traversal or external paths.
   - Wraps scene/object/component edits in `Undo` calls (`Undo.RegisterCreatedObjectUndo`, `Undo.RecordObject`, `Undo.DestroyObjectImmediate`, `Undo.AddComponent`).

---

## 2. All 21 Implemented Capabilities & 17 Registered Tools

| Tool ID | Category | Required Scope | Capability |
| :--- | :--- | :--- | :--- |
| `unity.get_editor_state` | Project management | `project:read` | Compilation, Play Mode, active scene, build target, readiness |
| `unity.get_scene_hierarchy` | Scene management | `project:read` | Recursive loaded scene hierarchy, instanceIds, tags, layers |
| `unity.inspect_object` | Object management | `project:read` | Transform + components + `SerializedObject` properties |
| `unity.create_object` | Object management | `scene:write` | Empty `GameObject` or `PrimitiveType` creation with `Undo` |
| `unity.delete_object` | Object management | `scene:write` | Safe `Undo.DestroyObjectImmediate` removal |
| `unity.transform_object` | Object management | `scene:write` | World/local position, Euler rotation, local scale with `Undo` |
| `unity.manage_component` | Component management | `scene:write` | `list`, `add`, `remove`, `set_property` via `SerializedObject` |
| `unity.create_script` | Script management | `script:write` | `Assets/*.cs` creation + `AssetDatabase.ImportAsset` |
| `unity.modify_script` | Script management | `script:write` | Exact replacement or full write + `ForceUpdate` re-import |
| `unity.inspect_assets` | Asset management | `project:read` | `AssetDatabase.FindAssets` with pagination, GUIDs & types |
| `unity.import_asset` | Asset management | `assets:modify` | Force re-import + `LoadMainAssetAtPath` check |
| `unity.save_scene` | Scene management | `scene:write` | `EditorSceneManager.SaveScene` / `SaveOpenScenes` |
| `unity.get_compilation_status` | Debugging | `project:read` | `CompilationPipeline` assemblies, errors, warnings |
| `unity.get_console_logs` | Debugging | `project:read` | `Application.logMessageReceivedThreaded` bounded ring buffer |
| `unity.control_play_mode` | Testing | `editor:execute` | `enter`, `exit`, `pause`, `resume`, `step` |
| `unity.capture_screenshot` | Rendering | `editor:execute` | Camera `RenderTexture` -> PNG bytes on main thread |
| `unity.get_build_status` | Build and export | `project:read` | `BuildPipeline`, active target, enabled scenes, last `BuildReport` |

---

## 3. Multi-Project Support

Each running Unity Editor calculates a deterministic `projectId` (`unity-<sha256_12>`) from its project root directory. To run multiple Unity Editor projects simultaneously with NEXUS:

1. Assign each Unity project a distinct loopback port (`1024–65535`) via **NEXUS -> Unity Bridge Status** or `NEXUS_UNITY_PORT`.
2. Install one manifest per Unity instance in the daemon (`POST /api/v1/adapters/install`) with unique `adapterId` and matching `127.0.0.1:<port>`.

---

## 4. Real Unity Editor Verification

Because Unity Editor on Windows does not exist inside AI Studio's web container, verify inside a real Unity project on Windows 10/11:
1. Install `adapters/unity/package.json` via Unity Package Manager (`Add package from disk...`).
2. Run **Window -> General -> Test Runner -> EditMode -> NexusUnityIntegrationTests**.
3. Connect the NEXUS Python daemon (`POST /api/v1/adapters/install` + `/connect`) against `127.0.0.1:47201` to drive live scene, script, compilation, screenshot, and MCP workflows.
