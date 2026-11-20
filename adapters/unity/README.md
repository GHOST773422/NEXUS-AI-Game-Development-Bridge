# NEXUS Unity C# Editor Adapter (`com.nexus.bridge`)

Native Unity Package Manager (`UPM`) C# extension connecting **Unity Editor** (`2022.3 LTS` / `6000.0 LTS` on Windows 10/11) to the local **NEXUS Daemon** over loopback TCP NDJSON JSON-RPC `2.0`.

## Installation in a Real Unity Project

1. Open **Window -> Package Manager -> `+` -> Add package from disk...** and select `adapters/unity/package.json`.
2. Unity compiles `Nexus.Bridge.Editor.asmdef` automatically and `[InitializeOnLoad]` starts `NexusUnityBridgeEntrypoint` on `127.0.0.1:47201`.
3. Open **NEXUS -> Unity Bridge Status** in the Unity menu bar to inspect the project ID, connected clients, and active port.

## Multi-Project Support

To attach multiple open Unity Editor projects concurrently:
- Set `NEXUS_UNITY_PORT` before launching Unity, **or** set a per-project port in **NEXUS -> Unity Bridge Status** (stored in `EditorPrefs` keyed by project root hash).
- Register a corresponding `nexus-adapter.manifest.json` in `AdapterManager` (`POST /api/v1/adapters/install`) with matching `127.0.0.1:<port>` and unique `adapterId` (e.g., `nexus.unity.csharp_editor.project_b`).

## Implemented Capabilities (21 Requirements / 17 Verified Editor Tools)

1. `[InitializeOnLoad]` initialization & `AssemblyReloadEvents` domain reload recovery
2. Unity version, render pipeline & scripting backend detection (`getEngineInfo`)
3. Deterministic project identification (`ComputeProjectId`, `discoverProjects`)
4. Loopback TCP session management & heartbeat (`connect`, `disconnect`, `healthCheck`)
5. Editor state inspection (`unity.get_editor_state`, `getProjectState`)
6. Recursive scene hierarchy inspection (`unity.get_scene_hierarchy`)
7. Object & `SerializedObject` inspection (`unity.inspect_object`)
8. Object creation with `Undo.RegisterCreatedObjectUndo` (`unity.create_object`)
9. Object deletion with `Undo.DestroyObjectImmediate` (`unity.delete_object`)
10. Object transformation with `Undo.RecordObject` (`unity.transform_object`)
11. Component add/remove/list/set property (`unity.manage_component`)
12. C# script creation sandboxed under `Assets/` (`unity.create_script`)
13. C# script modification & force reimport (`unity.modify_script`)
14. AssetDatabase search & pagination (`unity.inspect_assets`)
15. Asset importing & load verification (`unity.import_asset`)
16. Scene saving via `EditorSceneManager` (`unity.save_scene`)
17. Live C# compilation diagnostics (`CompilationPipeline` events + `unity.get_compilation_status`)
18. Threaded Unity console log capture (`logMessageReceivedThreaded` + `unity.get_console_logs`)
19. Play Mode control (`enter`/`exit`/`pause`/`resume`/`step`, `unity.control_play_mode`)
20. Camera / SceneView RenderTexture PNG screenshot capture (`captureScreenshot`, `unity.capture_screenshot`)
21. BuildPipeline & BuildReport reporting (`unity.get_build_status`)

## Real Unity Project Verification

Run the EditMode test suite inside Unity **Window -> General -> Test Runner -> EditMode** (`Nexus.Bridge.Editor.Tests` -> `NexusUnityIntegrationTests`) to verify live scene mutations, component modifications, script generation/compilation, and safety guards inside a real Unity Editor process.
