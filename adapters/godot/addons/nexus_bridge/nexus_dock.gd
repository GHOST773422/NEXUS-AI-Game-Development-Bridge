@tool
extends VBoxContainer

## Minimal Editor Dock UI for inspecting Godot compatibility, project ID, connected clients, and port binding.

const VersionHelper := preload("res://addons/nexus_bridge/nexus_version.gd")

var _port_spin: SpinBox
var _status_label: Label
var _apply_callback: Callable


func _init(current_port: int, on_apply_port: Callable) -> void:
	name = "NEXUS Bridge"
	_apply_callback = on_apply_port
	_build_ui(current_port)


func _build_ui(current_port: int) -> void:
	var title := Label.new()
	title.text = "NEXUS Godot Adapter (v1.0.0)"
	add_child(title)

	var compat := VersionHelper.check_compatibility()
	var ver_label := Label.new()
	ver_label.text = "Godot %s (%s)" % [compat["version"]["string"], "Compatible" if compat["compatible"] else "Incompatible"]
	add_child(ver_label)

	var proj_label := Label.new()
	proj_label.text = "Project ID: %s" % VersionHelper.compute_project_id()
	add_child(proj_label)

	_status_label = Label.new()
	_status_label.text = "Bind: 127.0.0.1:%d · Clients: 0" % current_port
	add_child(_status_label)

	var port_row := HBoxContainer.new()
	var port_caption := Label.new()
	port_caption.text = "Port:"
	port_row.add_child(port_caption)

	_port_spin = SpinBox.new()
	_port_spin.min_value = 1024
	_port_spin.max_value = 65535
	_port_spin.value = current_port
	port_row.add_child(_port_spin)

	var apply_btn := Button.new()
	apply_btn.text = "Restart"
	apply_btn.pressed.connect(func() -> void:
		if _apply_callback.is_valid():
			_apply_callback.call(int(_port_spin.value))
	)
	port_row.add_child(apply_btn)
	add_child(port_row)


func refresh_status(port: int, listening: bool, client_count: int) -> void:
	if _status_label != null:
		_status_label.text = "Bind: 127.0.0.1:%d (%s) · Clients: %d" % [
			port,
			"Listening" if listening else "Stopped",
			client_count,
		]
