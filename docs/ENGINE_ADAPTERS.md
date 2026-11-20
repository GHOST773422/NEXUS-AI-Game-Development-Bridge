# NEXUS Universal Engine Adapter Specification

Every engine adapter (`Unity` in C#, `Godot` in GDScript) implements the 13-method `EngineAdapterContract` defined in `sdk/ts/adapter.ts` and `sdk/python/nexus_sdk/__init__.py`:

1. `detectEngine()`
2. `identifyVersion(projectPath)`
3. `discoverProjects(searchRoots)`
4. `connectProject(projectId)`
5. `discoverCapabilities(projectId)`
6. `registerTools(projectId)`
7. `executeTool(request)`
8. `inspectProjectState(projectId)`
9. `subscribeEvents(projectId, onEvent)`
10. `captureScreenshot(projectId, viewport)`
11. `checkHealth(projectId)`
12. `reportError(error)`
13. `disconnectAndReconnect(projectId)`

Native editor idioms (`Undo.RecordObject` & `AssemblyReloadEvents` in Unity; `EditorUndoRedoManager` & `EditorInterface` in Godot) are preserved inside each adapter without cross-engine leakage.
