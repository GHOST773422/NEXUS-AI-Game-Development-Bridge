@tool
extends RefCounted

## Version-Aware Godot 4.x Tool Catalog & Capability Discovery Definitions.


static func discover_capabilities(compat: Dictionary) -> Array:
	var caps: Array = [
		"engine.info",
		"project.discover",
		"editor.version_check",
		"scene.inspect",
		"scene.hierarchy",
		"node.create",
		"node.modify",
		"node.delete",
		"transform.manage",
		"script.create",
		"script.modify",
		"resource.manage",
		"asset.inspect",
		"signal.manage",
		"scene.save",
		"runtime.launch",
		"runtime.monitor",
		"error.report",
		"export.status",
	]
	if bool(compat.get("hasEditorDebuggerPlugin", false)):
		caps.append("debugger.inspect")
	if bool(compat.get("hasEditorViewportCapture", false)):
		caps.append("screenshot.capture")
	if bool(compat.get("hasResourceUid", false)):
		caps.append("asset.uid_inspection")
	return caps


static func build_tool_catalog(compat: Dictionary) -> Array:
	if not bool(compat.get("compatible", false)):
		return []

	var tools: Array = [
		_make_tool("godot.get_scene_state", "Scene management", "Inspect currently edited Godot scene, open scenes, playing state, and version metadata.", ["project:read"], {}),
		_make_tool("godot.get_node_hierarchy", "Scene management", "Traverse the active edited SceneTree node hierarchy recursively with types, scripts, and groups.", ["project:read"], {"maxDepth": "integer"}),
		_make_tool("godot.create_node", "Object management", "Instantiate a ClassDB Node under target parent with EditorUndoRedoManager.", ["scene:write"], {"nodeType": "string", "name": "string", "parentPath": "string"}),
		_make_tool("godot.modify_node", "Object management", "Modify properties on an existing SceneTree node with Undo/Redo support.", ["scene:write"], {"nodePath": "string", "properties": "object"}),
		_make_tool("godot.delete_node", "Object management", "Remove a non-root node from the active scene using EditorUndoRedoManager.", ["scene:write"], {"nodePath": "string"}),
		_make_tool("godot.set_transform", "Object management", "Update 2D/Control or 3D Node position, rotation_degrees, and scale via EditorUndoRedoManager.", ["scene:write"], {"nodePath": "string", "position": "object", "rotationDegrees": "object", "scale": "object"}),
		_make_tool("godot.create_script", "Script management", "Create a res://*.gd script, reload/validate GDScript compilation, and optionally attach to a node.", ["script:write"], {"assetPath": "string", "content": "string", "overwrite": "boolean", "attachNodePath": "string"}),
		_make_tool("godot.modify_script", "Script management", "Update an existing res://*.gd script via full content or search/replace and verify GDScript reload.", ["script:write"], {"assetPath": "string", "content": "string", "searchText": "string", "replaceText": "string"}),
		_make_tool("godot.manage_resource", "Asset management", "Inspect, create, update properties on, and save .tres/.res resources under res://.", ["assets:modify"], {"action": "string", "resourcePath": "string", "resourceType": "string", "properties": "object"}),
		_make_tool("godot.inspect_assets", "Asset management", "Inspect EditorFileSystem directory tree under res:// with filter, extension, and pagination.", ["project:read"], {"folder": "string", "filter": "string", "extension": "string", "limit": "integer"}),
		_make_tool("godot.manage_signals", "Component management", "List node signals/connections or connect/disconnect persistent scene signals via EditorUndoRedoManager.", ["scene:write"], {"action": "string", "sourcePath": "string", "signalName": "string", "targetPath": "string", "methodName": "string"}),
		_make_tool("godot.save_scene", "Scene management", "Save the edited Godot scene in place or to a res://*.tscn path via EditorInterface.", ["scene:write"], {"scenePath": "string"}),
		_make_tool("godot.launch_runtime", "Testing", "Start (main/current/custom) or stop running the project inside Godot Editor.", ["editor:execute"], {"action": "string", "scenePath": "string"}),
		_make_tool("godot.get_runtime_status", "Profiling", "Inspect running Godot scene status, uptime, FPS, frame count, and object/memory metrics.", ["project:read"], {}),
		_make_tool("godot.get_errors", "Debugging", "Inspect buffered adapter errors, compilation failures, and Godot log ERROR/WARNING tail.", ["project:read"], {"limit": "integer", "clear": "boolean"}),
		_make_tool("godot.get_export_status", "Build and export", "Inspect export_presets.cfg presets, platform targets, and active NEXUS export plugin status.", ["project:read"], {}),
	]

	if bool(compat.get("hasEditorDebuggerPlugin", false)):
		tools.append(_make_tool("godot.inspect_debugger", "Debugging", "Inspect active EditorDebuggerPlugin sessions, breakpoint state, and captured messages.", ["project:read"], {}))

	if bool(compat.get("hasEditorViewportCapture", false)):
		tools.append(_make_tool("godot.capture_screenshot", "Rendering", "Capture live Godot 3D/2D editor viewport texture as PNG base64.", ["editor:execute"], {"viewport": "string"}))

	return tools


static func _make_tool(
	id: String,
	category: String,
	description: String,
	permissions: Array,
	properties: Dictionary
) -> Dictionary:
	var schema_props := {}
	for k in properties.keys():
		schema_props[k] = {"type": properties[k]}
	return {
		"id": id,
		"category": category,
		"description": description,
		"requiredPermissions": permissions,
		"executionContext": "EditorMainThread",
		"errorHandling": "Structured JSON-RPC 2.0 error envelope with Godot Engine diagnostics",
		"inputSchema": {"type": "object", "properties": schema_props},
		"outputSchema": {"type": "object"},
	}
