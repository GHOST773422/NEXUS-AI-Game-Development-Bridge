extends SceneTree

## Headless Godot 4.2+ Verification Harness for NEXUS Godot Adapter.
## Run: godot --headless --path adapters/godot/test_project --script res://tests/nexus_godot_verification.gd

const VersionHelper := preload("res://addons/nexus_bridge/nexus_version.gd")
const ToolRegistry := preload("res://addons/nexus_bridge/nexus_tool_registry.gd")


func _init() -> void:
	var failures: Array[String] = []

	var compat := VersionHelper.check_compatibility()
	if not bool(compat.get("compatible", false)):
		failures.append("Godot version compatibility check failed: %s" % str(compat.get("reasons", [])))

	var project_id := VersionHelper.compute_project_id()
	if not project_id.begins_with("godot-"):
		failures.append("Invalid projectId format: %s" % project_id)

	var caps := ToolRegistry.discover_capabilities(compat)
	var tools := ToolRegistry.build_tool_catalog(compat)
	if caps.size() < 19 or tools.size() < 17:
		failures.append("Expected >=19 capabilities and >=17 tools, got caps=%d tools=%d" % [caps.size(), tools.size()])

	var packed := load("res://scenes/main.tscn") as PackedScene
	if packed == null:
		failures.append("Failed loading res://scenes/main.tscn")
	else:
		var root := packed.instantiate()
		if root == null or root.name != "Main":
			failures.append("Main scene instantiation failed.")
		else:
			var dynamic_node := Node3D.new()
			dynamic_node.name = "NexusVerificationNode"
			root.add_child(dynamic_node)
			dynamic_node.position = Vector3(1.5, 2.0, -3.5)
			if dynamic_node.position != Vector3(1.5, 2.0, -3.5):
				failures.append("3D transform assignment failed.")

			var actor := root.get_node_or_null("TestActor")
			if actor == null or not actor.has_signal("status_changed"):
				failures.append("TestActor missing or missing status_changed signal.")
			else:
				var cb := Callable(actor, "_on_status_changed")
				actor.connect("status_changed", cb)
				actor.call("set_actor_state", "verified")
				if str(actor.get("last_observed_signal")) != "verified":
					failures.append("Signal emission did not invoke connected callback.")

			root.remove_child(dynamic_node)
			dynamic_node.free()
			root.free()

	var actor_script := ResourceLoader.load("res://scripts/test_actor.gd", "GDScript") as GDScript
	if actor_script == null or actor_script.reload(true) != OK:
		failures.append("test_actor.gd failed GDScript reload compilation check.")

	var res := StandardMaterial3D.new()
	res.roughness = 0.25
	var res_path := "res://tests/.nexus_tmp_verify_mat.tres"
	if ResourceSaver.save(res, res_path) != OK:
		failures.append("Failed saving .tres verification resource.")
	else:
		var loaded_mat := ResourceLoader.load(res_path, "", ResourceLoader.CACHE_MODE_REPLACE) as StandardMaterial3D
		if loaded_mat == null or not is_equal_approx(loaded_mat.roughness, 0.25):
			failures.append("Loaded .tres material properties did not persist.")
		DirAccess.remove_absolute(ProjectSettings.globalize_path(res_path))

	var cfg := ConfigFile.new()
	if cfg.load("res://export_presets.cfg") != OK or not cfg.has_section("preset.0"):
		failures.append("Failed parsing res://export_presets.cfg preset.0.")

	if failures.is_empty():
		print("NEXUS_GODOT_VERIFICATION_PASSED tools=%d projectId=%s" % [tools.size(), project_id])
		quit(0)
	else:
		for f in failures:
			push_error("NEXUS_GODOT_VERIFICATION_FAILURE: %s" % f)
		quit(1)
