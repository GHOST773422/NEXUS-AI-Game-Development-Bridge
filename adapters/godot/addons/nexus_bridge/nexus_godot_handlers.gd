@tool
extends RefCounted

## Executes all verified Godot 4.2+ EditorPlugin tool operations strictly on the Main Thread.

const VersionHelper := preload("res://addons/nexus_bridge/nexus_version.gd")

var plugin: EditorPlugin
var state_tracker: RefCounted


func _init(editor_plugin: EditorPlugin, tracker: RefCounted) -> void:
	plugin = editor_plugin
	state_tracker = tracker


func get_engine_info(listener_port: int) -> Dictionary:
	var compat := VersionHelper.check_compatibility()
	var ver: Dictionary = compat["version"]
	var root_path := VersionHelper.get_project_root_path()
	var project_name := str(ProjectSettings.get_setting("application/config/name", root_path.get_file()))
	var edited_root := EditorInterface.get_edited_scene_root()
	return {
		"adapterId": "nexus.godot.gdscript_editor",
		"displayName": "Godot GDScript EditorPlugin Adapter",
		"engineKind": "Godot",
		"engineVersion": str(ver["string"]),
		"versionInfo": ver,
		"compatible": compat["compatible"],
		"compatibilityReasons": compat["reasons"],
		"runtimeLanguage": "GDScript",
		"protocolVersion": "1.0.0",
		"isTestAdapter": false,
		"projectId": VersionHelper.compute_project_id(root_path),
		"projectName": project_name,
		"projectPath": root_path,
		"activeScene": edited_root.scene_file_path if edited_root != null else "",
		"platform": OS.get_name(),
		"listenerPort": listener_port,
	}


func discover_projects(listener_port: int) -> Dictionary:
	var root_path := VersionHelper.get_project_root_path()
	var ver := VersionHelper.detect_version_info()
	var project_name := str(ProjectSettings.get_setting("application/config/name", root_path.get_file()))
	var edited_root := EditorInterface.get_edited_scene_root()
	return {
		"isTestAdapter": false,
		"projects": [
			{
				"id": VersionHelper.compute_project_id(root_path),
				"name": project_name,
				"engine": "Godot",
				"rootPath": root_path,
				"engineVersion": str(ver["string"]),
				"activeScene": edited_root.scene_file_path if edited_root != null else "",
				"listenerPort": listener_port,
				"isActiveEditorSession": true,
			}
		],
	}


func get_scene_state() -> Dictionary:
	var edited_root := EditorInterface.get_edited_scene_root()
	var compat := VersionHelper.check_compatibility()
	return {
		"projectId": VersionHelper.compute_project_id(),
		"projectName": str(ProjectSettings.get_setting("application/config/name", "GodotProject")),
		"godotVersion": compat["version"]["string"],
		"compatible": compat["compatible"],
		"hasEditedScene": edited_root != null,
		"activeScenePath": edited_root.scene_file_path if edited_root != null else "",
		"activeSceneRootName": edited_root.name if edited_root != null else "",
		"activeSceneRootType": edited_root.get_class() if edited_root != null else "",
		"openScenes": Array(EditorInterface.get_open_scenes()),
		"isPlayingScene": EditorInterface.is_playing_scene(),
		"playingScenePath": EditorInterface.get_playing_scene(),
		"isScanningFilesystem": EditorInterface.get_resource_filesystem().is_scanning(),
		"timestamp": Time.get_datetime_string_from_system(true, true),
	}


func dispatch_tool(tool_id: String, project_id: String, request_id: String, arguments: Dictionary) -> Dictionary:
	var output: Dictionary
	match tool_id:
		"godot.get_scene_state":
			output = get_scene_state()
		"godot.get_node_hierarchy":
			output = get_node_hierarchy(arguments)
		"godot.create_node":
			output = create_node(arguments)
		"godot.modify_node":
			output = modify_node(arguments)
		"godot.delete_node":
			output = delete_node(arguments)
		"godot.set_transform":
			output = set_transform(arguments)
		"godot.create_script":
			output = create_script(arguments)
		"godot.modify_script":
			output = modify_script(arguments)
		"godot.manage_resource":
			output = manage_resource(arguments)
		"godot.inspect_assets":
			output = inspect_assets(arguments)
		"godot.manage_signals":
			output = manage_signals(arguments)
		"godot.save_scene":
			output = save_scene(arguments)
		"godot.launch_runtime":
			output = launch_runtime(arguments)
		"godot.get_runtime_status":
			output = get_runtime_status()
		"godot.inspect_debugger":
			output = state_tracker.get_debugger_snapshot()
		"godot.get_errors":
			var lim := int(arguments.get("limit", 50))
			var clr := bool(arguments.get("clear", false))
			output = state_tracker.get_recent_errors(lim, clr)
		"godot.capture_screenshot":
			output = capture_screenshot(arguments)
		"godot.get_export_status":
			output = get_export_status()
		_:
			return _rpc_error(-32601, "NEXUS_UNKNOWN_GODOT_TOOL", "Unknown Godot tool '%s'." % tool_id)

	if output.has("_rpcError"):
		return output

	return {
		"requestId": request_id,
		"toolId": tool_id,
		"projectId": project_id,
		"status": "Available",
		"verified": true,
		"isTestAdapter": false,
		"output": output,
	}


func get_node_hierarchy(args: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _rpc_error(-32004, "NEXUS_NO_EDITED_SCENE", "No scene is currently open in Godot Editor.")
	var max_depth := int(args.get("maxDepth", 12))
	return {
		"scenePath": root.scene_file_path,
		"root": _serialize_node_tree(root, root, 0, max_depth),
	}


func create_node(args: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _rpc_error(-32004, "NEXUS_NO_EDITED_SCENE", "Open a scene before creating nodes.")
	var node_type := str(args.get("nodeType", "Node")).strip_edges()
	var node_name := str(args.get("name", node_type)).strip_edges()
	var parent_path := str(args.get("parentPath", ".")).strip_edges()

	if not ClassDB.class_exists(node_type) or not ClassDB.can_instantiate(node_type):
		return _rpc_error(-32602, "NEXUS_INVALID_NODE_TYPE", "ClassDB cannot instantiate nodeType '%s'." % node_type)

	var parent := _resolve_scene_node(root, parent_path)
	if parent == null:
		return _rpc_error(-32602, "NEXUS_PARENT_NOT_FOUND", "Parent node '%s' not found." % parent_path)

	var instance: Object = ClassDB.instantiate(node_type)
	if not (instance is Node):
		return _rpc_error(-32602, "NEXUS_NOT_A_NODE", "'%s' is not a SceneTree Node subclass." % node_type)
	var new_node := instance as Node
	new_node.name = node_name if not node_name.is_empty() else node_type

	var undo_redo := plugin.get_undo_redo()
	undo_redo.create_action("NEXUS Create %s" % new_node.name)
	undo_redo.add_do_method(parent, "add_child", new_node, true)
	undo_redo.add_do_property(new_node, "owner", root)
	undo_redo.add_do_reference(new_node)
	undo_redo.add_undo_method(parent, "remove_child", new_node)
	undo_redo.commit_action()

	return {
		"created": true,
		"node": _serialize_node_summary(new_node, root),
	}


func modify_node(args: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _rpc_error(-32004, "NEXUS_NO_EDITED_SCENE", "Open a scene before modifying nodes.")
	var node_path := str(args.get("nodePath", "")).strip_edges()
	var target := _resolve_scene_node(root, node_path)
	if target == null:
		return _rpc_error(-32602, "NEXUS_NODE_NOT_FOUND", "Node '%s' not found." % node_path)

	var props = args.get("properties", {})
	if not (props is Dictionary) or props.is_empty():
		return _rpc_error(-32602, "NEXUS_MISSING_PROPERTIES", "Provide non-empty 'properties' object.")

	var pending_changes: Array = []
	for key in props.keys():
		var prop_name := str(key)
		if not _object_has_property(target, prop_name):
			return _rpc_error(-32602, "NEXUS_UNKNOWN_PROPERTY", "Property '%s' not found on %s." % [prop_name, target.get_class()])
		var old_val: Variant = target.get(prop_name)
		var new_val: Variant = _coerce_variant(props[key], typeof(old_val))
		pending_changes.append({"name": prop_name, "old": old_val, "new": new_val})

	var undo_redo := plugin.get_undo_redo()
	undo_redo.create_action("NEXUS Modify %s" % target.name)
	var updated_keys: Array = []
	for change in pending_changes:
		undo_redo.add_do_property(target, change["name"], change["new"])
		undo_redo.add_undo_property(target, change["name"], change["old"])
		updated_keys.append(change["name"])
	undo_redo.commit_action()

	return {
		"modified": true,
		"nodePath": str(root.get_path_to(target)),
		"updatedProperties": updated_keys,
	}


func delete_node(args: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _rpc_error(-32004, "NEXUS_NO_EDITED_SCENE", "Open a scene before deleting nodes.")
	var node_path := str(args.get("nodePath", "")).strip_edges()
	var target := _resolve_scene_node(root, node_path)
	if target == null:
		return _rpc_error(-32602, "NEXUS_NODE_NOT_FOUND", "Node '%s' not found." % node_path)
	if target == root or target.get_parent() == null:
		return _rpc_error(-32602, "NEXUS_CANNOT_DELETE_ROOT", "Cannot delete the edited scene root node.")

	var parent := target.get_parent()
	var rel_path := str(root.get_path_to(target))
	var undo_redo := plugin.get_undo_redo()
	undo_redo.create_action("NEXUS Delete %s" % target.name)
	undo_redo.add_do_method(parent, "remove_child", target)
	undo_redo.add_undo_method(parent, "add_child", target)
	undo_redo.add_undo_property(target, "owner", root)
	undo_redo.add_undo_reference(target)
	undo_redo.commit_action()

	return {
		"deleted": true,
		"nodePath": rel_path,
	}


func set_transform(args: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _rpc_error(-32004, "NEXUS_NO_EDITED_SCENE", "Open a scene before transforming nodes.")
	var node_path := str(args.get("nodePath", "")).strip_edges()
	var target := _resolve_scene_node(root, node_path)
	if target == null:
		return _rpc_error(-32602, "NEXUS_NODE_NOT_FOUND", "Node '%s' not found." % node_path)

	var undo_redo := plugin.get_undo_redo()
	undo_redo.create_action("NEXUS Transform %s" % target.name)

	if target is Node3D:
		var n3 := target as Node3D
		if args.has("position") and args["position"] is Dictionary:
			var p := _dict_to_vec3(args["position"], n3.position)
			undo_redo.add_do_property(n3, "position", p)
			undo_redo.add_undo_property(n3, "position", n3.position)
		if args.has("rotationDegrees") and args["rotationDegrees"] is Dictionary:
			var r := _dict_to_vec3(args["rotationDegrees"], n3.rotation_degrees)
			undo_redo.add_do_property(n3, "rotation_degrees", r)
			undo_redo.add_undo_property(n3, "rotation_degrees", n3.rotation_degrees)
		if args.has("scale") and args["scale"] is Dictionary:
			var s := _dict_to_vec3(args["scale"], n3.scale)
			undo_redo.add_do_property(n3, "scale", s)
			undo_redo.add_undo_property(n3, "scale", n3.scale)
		undo_redo.commit_action()
		return {
			"transformed": true,
			"dimension": "3D",
			"nodePath": str(root.get_path_to(n3)),
			"position": _vec3_to_dict(n3.position),
			"rotationDegrees": _vec3_to_dict(n3.rotation_degrees),
			"scale": _vec3_to_dict(n3.scale),
		}

	if target is Node2D:
		var n2 := target as Node2D
		if args.has("position") and args["position"] is Dictionary:
			var p2 := _dict_to_vec2(args["position"], n2.position)
			undo_redo.add_do_property(n2, "position", p2)
			undo_redo.add_undo_property(n2, "position", n2.position)
		if args.has("rotationDegrees"):
			var raw_r2: Variant = args["rotationDegrees"]
			var r2: float = float(raw_r2.get("z", n2.rotation_degrees)) if raw_r2 is Dictionary else float(raw_r2)
			undo_redo.add_do_property(n2, "rotation_degrees", r2)
			undo_redo.add_undo_property(n2, "rotation_degrees", n2.rotation_degrees)
		if args.has("scale") and args["scale"] is Dictionary:
			var s2 := _dict_to_vec2(args["scale"], n2.scale)
			undo_redo.add_do_property(n2, "scale", s2)
			undo_redo.add_undo_property(n2, "scale", n2.scale)
		undo_redo.commit_action()
		return {
			"transformed": true,
			"dimension": "2D",
			"nodePath": str(root.get_path_to(n2)),
			"position": _vec2_to_dict(n2.position),
			"rotationDegrees": n2.rotation_degrees,
			"scale": _vec2_to_dict(n2.scale),
		}

	return _rpc_error(-32602, "NEXUS_NODE_NO_TRANSFORM", "Node '%s' (%s) does not support 2D/3D transforms." % [target.name, target.get_class()])


func create_script(args: Dictionary) -> Dictionary:
	var path_err := _validate_res_path(str(args.get("assetPath", "")), ".gd")
	if not path_err.is_empty():
		return _rpc_error(-32602, "NEXUS_SANDBOX_VIOLATION", path_err)
	var asset_path := str(args.get("assetPath", "")).strip_edges()
	var content := str(args.get("content", ""))
	var overwrite := bool(args.get("overwrite", false))
	if content.strip_edges().is_empty():
		return _rpc_error(-32602, "NEXUS_EMPTY_SCRIPT", "GDScript content cannot be empty.")

	if FileAccess.file_exists(asset_path) and not overwrite:
		return _rpc_error(-32004, "NEXUS_SCRIPT_EXISTS", "Script '%s' already exists (pass overwrite=true to replace)." % asset_path)

	var dir_err := _ensure_res_dir_exists(asset_path.get_base_dir())
	if dir_err != OK:
		return _rpc_error(-32005, "NEXUS_DIR_CREATE_FAILED", "Failed creating directory for '%s' (Error %d)." % [asset_path, dir_err])

	var file := FileAccess.open(asset_path, FileAccess.WRITE)
	if file == null:
		return _rpc_error(-32005, "NEXUS_FILE_WRITE_FAILED", "Cannot open '%s' for writing." % asset_path)
	file.store_string(content)
	file.flush()
	file.close()

	EditorInterface.get_resource_filesystem().scan()
	var loaded := ResourceLoader.load(asset_path, "GDScript", ResourceLoader.CACHE_MODE_REPLACE)
	var compile_ok := loaded is GDScript
	var reload_err := ERR_CANT_RESOLVE
	if compile_ok:
		reload_err = (loaded as GDScript).reload(true)
	if reload_err != OK:
		state_tracker.record_error("NEXUS_GDSCRIPT_COMPILE_ERROR", "Script '%s' reload returned error %d." % [asset_path, reload_err], {"assetPath": asset_path})

	var attach_path := str(args.get("attachNodePath", "")).strip_edges()
	var attached := false
	if not attach_path.is_empty() and compile_ok:
		var root := EditorInterface.get_edited_scene_root()
		var target := _resolve_scene_node(root, attach_path) if root != null else null
		if target != null:
			target.set_script(loaded)
			attached = true

	return {
		"created": true,
		"assetPath": asset_path,
		"compiled": compile_ok and reload_err == OK,
		"reloadErrorCode": reload_err,
		"attached": attached,
	}


func modify_script(args: Dictionary) -> Dictionary:
	var path_err := _validate_res_path(str(args.get("assetPath", "")), ".gd")
	if not path_err.is_empty():
		return _rpc_error(-32602, "NEXUS_SANDBOX_VIOLATION", path_err)
	var asset_path := str(args.get("assetPath", "")).strip_edges()
	if not FileAccess.file_exists(asset_path):
		return _rpc_error(-32602, "NEXUS_SCRIPT_NOT_FOUND", "Script '%s' does not exist." % asset_path)

	var new_content: String
	if args.has("content") and args["content"] != null:
		new_content = str(args["content"])
	else:
		var search_text := str(args.get("searchText", ""))
		var replace_text := str(args.get("replaceText", ""))
		if search_text.is_empty():
			return _rpc_error(-32602, "NEXUS_MISSING_EDIT", "Provide 'content' or non-empty 'searchText' + 'replaceText'.")
		var existing := FileAccess.get_file_as_string(asset_path)
		if not existing.contains(search_text):
			return _rpc_error(-32602, "NEXUS_SEARCH_TEXT_NOT_FOUND", "'%s' not found inside '%s'." % [search_text, asset_path])
		new_content = existing.replace(search_text, replace_text)

	var file := FileAccess.open(asset_path, FileAccess.WRITE)
	if file == null:
		return _rpc_error(-32005, "NEXUS_FILE_WRITE_FAILED", "Cannot open '%s' for writing." % asset_path)
	file.store_string(new_content)
	file.flush()
	file.close()

	EditorInterface.get_resource_filesystem().scan()
	var loaded := ResourceLoader.load(asset_path, "GDScript", ResourceLoader.CACHE_MODE_REPLACE)
	var reload_err := (loaded as GDScript).reload(true) if loaded is GDScript else ERR_PARSE_ERROR
	if reload_err != OK:
		state_tracker.record_error("NEXUS_GDSCRIPT_COMPILE_ERROR", "Modified script '%s' failed reload (%d)." % [asset_path, reload_err], {"assetPath": asset_path})

	return {
		"modified": true,
		"assetPath": asset_path,
		"compiled": reload_err == OK,
		"reloadErrorCode": reload_err,
	}


func manage_resource(args: Dictionary) -> Dictionary:
	var action := str(args.get("action", "inspect")).strip_edges().to_lower()
	var res_path := str(args.get("resourcePath", "")).strip_edges()
	var path_err := _validate_res_path(res_path, "")
	if not path_err.is_empty():
		return _rpc_error(-32602, "NEXUS_SANDBOX_VIOLATION", path_err)

	if action == "create":
		var res_type := str(args.get("resourceType", "Resource")).strip_edges()
		if not ClassDB.class_exists(res_type) or not ClassDB.can_instantiate(res_type):
			return _rpc_error(-32602, "NEXUS_INVALID_RESOURCE_TYPE", "Cannot instantiate resourceType '%s'." % res_type)
		var inst: Object = ClassDB.instantiate(res_type)
		if not (inst is Resource):
			return _rpc_error(-32602, "NEXUS_NOT_A_RESOURCE", "'%s' is not a Resource subclass." % res_type)
		var res := inst as Resource
		var dir_err := _ensure_res_dir_exists(res_path.get_base_dir())
		if dir_err != OK:
			return _rpc_error(-32005, "NEXUS_DIR_CREATE_FAILED", "Failed creating directory for resource.")
		if args.has("properties") and args["properties"] is Dictionary:
			_apply_dict_properties(res, args["properties"])
		var save_err := ResourceSaver.save(res, res_path)
		EditorInterface.get_resource_filesystem().scan()
		return {"created": save_err == OK, "errorCode": save_err, "resourcePath": res_path, "resourceType": res.get_class()}

	if not ResourceLoader.exists(res_path):
		return _rpc_error(-32602, "NEXUS_RESOURCE_NOT_FOUND", "Resource '%s' does not exist." % res_path)
	var loaded := ResourceLoader.load(res_path, "", ResourceLoader.CACHE_MODE_REPLACE)
	if loaded == null:
		return _rpc_error(-32005, "NEXUS_RESOURCE_LOAD_FAILED", "Failed loading '%s'." % res_path)

	if action == "set_property":
		if not (args.get("properties") is Dictionary):
			return _rpc_error(-32602, "NEXUS_MISSING_PROPERTIES", "Provide 'properties' dictionary.")
		_apply_dict_properties(loaded, args["properties"])
		var err := ResourceSaver.save(loaded, res_path)
		return {"updated": err == OK, "errorCode": err, "resourcePath": res_path}

	var prop_preview := {}
	for p in loaded.get_property_list():
		var pname := str(p["name"])
		if int(p["usage"]) & PROPERTY_USAGE_EDITOR:
			prop_preview[pname] = _variant_to_json_safe(loaded.get(pname))
	return {
		"resourcePath": res_path,
		"resourceType": loaded.get_class(),
		"properties": prop_preview,
	}


func inspect_assets(args: Dictionary) -> Dictionary:
	var folder := str(args.get("folder", "res://")).strip_edges()
	var filter := str(args.get("filter", "")).strip_edges().to_lower()
	var ext_filter := str(args.get("extension", "")).strip_edges().to_lower()
	var limit := clampi(int(args.get("limit", 100)), 1, 500)

	var fs := EditorInterface.get_resource_filesystem()
	var dir := fs.get_filesystem_path(folder)
	if dir == null:
		dir = fs.get_filesystem()
	var collected: Array = []
	if dir != null:
		_collect_fs_assets(dir, filter, ext_filter, limit, collected)
	return {
		"folder": folder,
		"count": collected.size(),
		"assets": collected,
	}


func manage_signals(args: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _rpc_error(-32004, "NEXUS_NO_EDITED_SCENE", "Open a scene before managing signals.")
	var action := str(args.get("action", "list")).strip_edges().to_lower()
	var source_path := str(args.get("sourcePath", ".")).strip_edges()
	var source := _resolve_scene_node(root, source_path)
	if source == null:
		return _rpc_error(-32602, "NEXUS_SOURCE_NODE_NOT_FOUND", "Source node '%s' not found." % source_path)

	if action == "list":
		var signals_out: Array = []
		for sig in source.get_signal_list():
			var sname := str(sig["name"])
			var conns: Array = []
			for c in source.get_signal_connection_list(sname):
				var callable_obj: Callable = c["callable"]
				var target_obj := callable_obj.get_object()
				conns.append({
					"targetName": target_obj.name if target_obj is Node else str(target_obj),
					"method": str(callable_obj.get_method()),
					"flags": int(c["flags"]),
				})
			signals_out.append({"name": sname, "connections": conns})
		return {"nodePath": str(root.get_path_to(source)), "signals": signals_out}

	var sig_name := str(args.get("signalName", "")).strip_edges()
	var target_path := str(args.get("targetPath", ".")).strip_edges()
	var method_name := str(args.get("methodName", "")).strip_edges()
	var target := _resolve_scene_node(root, target_path)
	if target == null:
		return _rpc_error(-32602, "NEXUS_TARGET_NODE_NOT_FOUND", "Target node '%s' not found." % target_path)
	if not source.has_signal(sig_name):
		return _rpc_error(-32602, "NEXUS_SIGNAL_NOT_FOUND", "Signal '%s' not found on '%s'." % [sig_name, source.name])

	var callable := Callable(target, StringName(method_name))
	var undo_redo := plugin.get_undo_redo()
	if action == "connect":
		if source.is_connected(sig_name, callable):
			return {"connected": true, "alreadyConnected": true}
		undo_redo.create_action("NEXUS Connect Signal %s" % sig_name)
		undo_redo.add_do_method(source, "connect", sig_name, callable, Object.CONNECT_PERSIST)
		undo_redo.add_undo_method(source, "disconnect", sig_name, callable)
		undo_redo.commit_action()
		return {"connected": true, "signal": sig_name, "method": method_name}

	if action == "disconnect":
		if not source.is_connected(sig_name, callable):
			return {"disconnected": false, "reason": "Signal was not connected."}
		undo_redo.create_action("NEXUS Disconnect Signal %s" % sig_name)
		undo_redo.add_do_method(source, "disconnect", sig_name, callable)
		undo_redo.add_undo_method(source, "connect", sig_name, callable, Object.CONNECT_PERSIST)
		undo_redo.commit_action()
		return {"disconnected": true, "signal": sig_name, "method": method_name}

	return _rpc_error(-32602, "NEXUS_INVALID_ACTION", "Unsupported manage_signals action '%s'." % action)


func save_scene(args: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _rpc_error(-32004, "NEXUS_NO_EDITED_SCENE", "No scene is currently open to save.")
	var custom_path := str(args.get("scenePath", "")).strip_edges()
	if not custom_path.is_empty():
		var path_err := _validate_res_path(custom_path, ".tscn")
		if not path_err.is_empty():
			return _rpc_error(-32602, "NEXUS_SANDBOX_VIOLATION", path_err)
		EditorInterface.save_scene_as(custom_path)
		var saved_to_path := root.scene_file_path == custom_path and FileAccess.file_exists(custom_path)
		return {
			"saved": saved_to_path,
			"errorCode": OK if saved_to_path else ERR_CANT_CREATE,
			"scenePath": root.scene_file_path,
		}

	if root.scene_file_path.is_empty():
		return _rpc_error(-32602, "NEXUS_UNTITLED_SCENE", "Active scene has no path; provide 'scenePath' ending with .tscn.")
	var err: Error = EditorInterface.save_scene()

	return {
		"saved": err == OK,
		"errorCode": err,
		"scenePath": root.scene_file_path,
	}


func launch_runtime(args: Dictionary) -> Dictionary:
	var action := str(args.get("action", "play_main")).strip_edges().to_lower()
	match action:
		"play_main":
			EditorInterface.play_main_scene()
			state_tracker.runtime_started_msec = Time.get_ticks_msec()
		"play_current":
			if EditorInterface.get_edited_scene_root() == null:
				return _rpc_error(-32004, "NEXUS_NO_EDITED_SCENE", "No edited scene open for play_current.")
			EditorInterface.play_current_scene()
			state_tracker.runtime_started_msec = Time.get_ticks_msec()
		"play_custom":
			var scene_path := str(args.get("scenePath", "")).strip_edges()
			var path_err := _validate_res_path(scene_path, ".tscn")
			if not path_err.is_empty():
				return _rpc_error(-32602, "NEXUS_SANDBOX_VIOLATION", path_err)
			if not ResourceLoader.exists(scene_path):
				return _rpc_error(-32602, "NEXUS_SCENE_NOT_FOUND", "Scene '%s' does not exist." % scene_path)
			EditorInterface.play_custom_scene(scene_path)
			state_tracker.runtime_started_msec = Time.get_ticks_msec()
		"stop":
			EditorInterface.stop_playing_scene()
		_:
			return _rpc_error(-32602, "NEXUS_INVALID_ACTION", "Unsupported launch_runtime action '%s'." % action)

	return get_runtime_status()


func get_runtime_status() -> Dictionary:
	var playing := EditorInterface.is_playing_scene()
	var uptime_ms: int = 0
	if playing and state_tracker.runtime_started_msec > 0:
		uptime_ms = int(Time.get_ticks_msec() - int(state_tracker.runtime_started_msec))
	return {
		"isPlaying": playing,
		"playingScene": EditorInterface.get_playing_scene(),
		"uptimeMs": uptime_ms,
		"editorFps": Performance.get_monitor(Performance.TIME_FPS),
		"objectCount": int(Performance.get_monitor(Performance.OBJECT_COUNT)),
		"staticMemoryBytes": int(OS.get_static_memory_usage()),
	}


func capture_screenshot(args: Dictionary) -> Dictionary:
	var mode := str(args.get("viewport", "SceneView")).strip_edges()
	var vp: Viewport = null
	if mode == "2D":
		vp = EditorInterface.get_editor_viewport_2d()
	else:
		vp = EditorInterface.get_editor_viewport_3d(0)
	if vp == null:
		vp = plugin.get_viewport()
	if vp == null or vp.get_texture() == null:
		return _rpc_error(-32006, "NEXUS_NO_VIEWPORT_AVAILABLE", "No active rendering Viewport texture is available (headless mode unsupported).")

	var img := vp.get_texture().get_image()
	if img == null or img.is_empty():
		return _rpc_error(-32006, "NEXUS_EMPTY_VIEWPORT_IMAGE", "Godot viewport returned an empty screenshot image.")

	var png_bytes := img.save_png_to_buffer()
	return {
		"projectId": VersionHelper.compute_project_id(),
		"viewport": mode,
		"mimeType": "image/png",
		"width": img.get_width(),
		"height": img.get_height(),
		"byteLength": png_bytes.size(),
		"dataBase64": Marshalls.raw_to_base64(png_bytes),
		"isTestAdapter": false,
		"capturedAt": Time.get_datetime_string_from_system(true, true),
	}


func get_export_status() -> Dictionary:
	var presets: Array = []
	var cfg := ConfigFile.new()
	if cfg.load("res://export_presets.cfg") == OK:
		for sec in cfg.get_sections():
			if sec.begins_with("preset.") and not sec.ends_with(".options"):
				presets.append({
					"section": sec,
					"name": str(cfg.get_value(sec, "name", sec)),
					"platform": str(cfg.get_value(sec, "platform", "")),
					"runnable": bool(cfg.get_value(sec, "runnable", false)),
					"exportPath": str(cfg.get_value(sec, "export_path", "")),
				})
	return {
		"hasExportPresetsFile": FileAccess.file_exists("res://export_presets.cfg"),
		"presetCount": presets.size(),
		"presets": presets,
		"lastExport": state_tracker.last_export,
	}


func _resolve_scene_node(root: Node, raw_path: String) -> Node:
	if root == null:
		return null
	var p := raw_path.strip_edges()
	if p.is_empty() or p == "." or p == root.name or p == ("/%s" % root.name):
		return root
	return root.get_node_or_null(NodePath(p))


func _serialize_node_tree(node: Node, root: Node, depth: int, max_depth: int) -> Dictionary:
	var out := _serialize_node_summary(node, root)
	var children_out: Array = []
	if depth < max_depth:
		for child in node.get_children():
			children_out.append(_serialize_node_tree(child, root, depth + 1, max_depth))
	out["children"] = children_out
	return out


func _serialize_node_summary(node: Node, root: Node) -> Dictionary:
	var script_obj: Variant = node.get_script()
	return {
		"name": str(node.name),
		"path": str(root.get_path_to(node)),
		"type": node.get_class(),
		"scriptPath": script_obj.resource_path if script_obj is Resource else "",
		"groups": Array(node.get_groups()),
		"childCount": node.get_child_count(),
	}


func _collect_fs_assets(dir: EditorFileSystemDirectory, filter: String, ext_filter: String, limit: int, out: Array) -> void:
	if out.size() >= limit:
		return
	for i in range(dir.get_file_count()):
		if out.size() >= limit:
			return
		var file_path := dir.get_file_path(i)
		var ftype := str(dir.get_file_type(i))
		if not filter.is_empty() and not file_path.to_lower().contains(filter):
			continue
		if not ext_filter.is_empty() and not file_path.get_extension().to_lower() == ext_filter.trim_prefix("."):
			continue
		out.append({
			"path": file_path,
			"type": ftype,
			"importValid": dir.get_file_import_is_valid(i),
		})
	for s in range(dir.get_subdir_count()):
		_collect_fs_assets(dir.get_subdir(s), filter, ext_filter, limit, out)


func _validate_res_path(raw: String, required_ext: String) -> String:
	var p := raw.strip_edges().replace("\\", "/")
	if not p.begins_with("res://"):
		return "Godot resource/script path must start with 'res://'."
	if p.contains(".."):
		return "Path traversal ('..') is forbidden."
	if not required_ext.is_empty() and not p.to_lower().ends_with(required_ext.to_lower()):
		return "Path must use '%s' extension." % required_ext
	return ""


func _ensure_res_dir_exists(res_dir: String) -> Error:
	if res_dir == "res://" or res_dir == "res:":
		return OK
	return DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(res_dir))


func _object_has_property(obj: Object, prop_name: String) -> bool:
	for p in obj.get_property_list():
		if str(p["name"]) == prop_name:
			return true
	return false


func _apply_dict_properties(target: Object, props: Dictionary) -> void:
	for key in props.keys():
		var pname := str(key)
		if _object_has_property(target, pname):
			target.set(pname, _coerce_variant(props[key], typeof(target.get(pname))))


func _coerce_variant(raw: Variant, target_type: int) -> Variant:
	if target_type == TYPE_VECTOR3 and raw is Dictionary:
		return _dict_to_vec3(raw, Vector3.ZERO)
	if target_type == TYPE_VECTOR2 and raw is Dictionary:
		return _dict_to_vec2(raw, Vector2.ZERO)
	return raw


func _dict_to_vec3(d: Dictionary, fallback: Vector3) -> Vector3:
	return Vector3(
		float(d.get("x", fallback.x)),
		float(d.get("y", fallback.y)),
		float(d.get("z", fallback.z))
	)


func _vec3_to_dict(v: Vector3) -> Dictionary:
	return {"x": v.x, "y": v.y, "z": v.z}


func _dict_to_vec2(d: Dictionary, fallback: Vector2) -> Vector2:
	return Vector2(float(d.get("x", fallback.x)), float(d.get("y", fallback.y)))


func _vec2_to_dict(v: Vector2) -> Dictionary:
	return {"x": v.x, "y": v.y}


func _variant_to_json_safe(val: Variant) -> Variant:
	if val is Vector3:
		return _vec3_to_dict(val)
	if val is Vector2:
		return _vec2_to_dict(val)
	if val is Color:
		var c := val as Color
		return {"r": c.r, "g": c.g, "b": c.b, "a": c.a}
	if val is int or val is float or val is bool or val is String or val == null:
		return val
	return str(val)


func _rpc_error(code: int, error_code: String, message: String) -> Dictionary:
	return {
		"_rpcError": true,
		"code": code,
		"errorCode": error_code,
		"message": message,
	}
