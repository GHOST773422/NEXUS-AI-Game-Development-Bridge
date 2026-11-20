@tool
extends EditorPlugin

## Primary NEXUS Godot 4.2+ EditorPlugin Entrypoint (adapters/godot/nexus-adapter.manifest.json).

const DefaultPort := 47202

const VersionHelper := preload("res://addons/nexus_bridge/nexus_version.gd")
const StatePlugins := preload("res://addons/nexus_bridge/nexus_state_plugins.gd")
const GodotHandlers := preload("res://addons/nexus_bridge/nexus_godot_handlers.gd")
const TcpRpcServer := preload("res://addons/nexus_bridge/nexus_tcp_server.gd")
const BridgeDock := preload("res://addons/nexus_bridge/nexus_dock.gd")

var state_tracker: RefCounted
var handlers: RefCounted
var tcp_server: RefCounted
var _dock: Control
var _dock_refresh_timer: float = 0.0


func _enter_tree() -> void:
	state_tracker = StatePlugins.StateTracker.new()
	add_debugger_plugin(state_tracker.debugger_plugin)
	add_export_plugin(state_tracker.export_plugin)

	handlers = GodotHandlers.new(self, state_tracker)
	tcp_server = TcpRpcServer.new(handlers, state_tracker)

	var port := _resolve_configured_port()
	var compat := VersionHelper.check_compatibility()
	if not compat["compatible"]:
		for reason in compat["reasons"]:
			state_tracker.record_error("NEXUS_GODOT_UNSUPPORTED_VERSION", str(reason))
		push_warning("NEXUS Bridge: %s" % ", ".join(compat["reasons"]))

	tcp_server.start(port)

	_dock = BridgeDock.new(port, Callable(self, "_on_restart_port"))
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, _dock)
	set_process(true)


func _exit_tree() -> void:
	set_process(false)
	if _dock != null:
		remove_control_from_docks(_dock)
		_dock.queue_free()
		_dock = null
	if tcp_server != null:
		tcp_server.stop()
		tcp_server = null
	if state_tracker != null:
		remove_debugger_plugin(state_tracker.debugger_plugin)
		remove_export_plugin(state_tracker.export_plugin)
		state_tracker = null
	handlers = null


func _process(delta: float) -> void:
	if tcp_server != null:
		tcp_server.poll()
		_dock_refresh_timer += delta
		if _dock != null and _dock_refresh_timer >= 0.5:
			_dock_refresh_timer = 0.0
			_dock.refresh_status(
				tcp_server.active_port(),
				tcp_server.is_listening(),
				tcp_server.active_client_count()
			)


func _on_restart_port(new_port: int) -> void:
	var clamped := clampi(new_port, 1024, 65535)
	var setting_key := "nexus/bridge/port_%s" % VersionHelper.compute_project_id()
	EditorInterface.get_editor_settings().set_setting(setting_key, clamped)
	if tcp_server != null:
		tcp_server.start(clamped)
		if _dock != null:
			_dock.refresh_status(clamped, tcp_server.is_listening(), tcp_server.active_client_count())


func _resolve_configured_port() -> int:
	var env_val := OS.get_environment("NEXUS_GODOT_PORT").strip_edges()
	if env_val.is_valid_int():
		var env_port := int(env_val)
		if env_port >= 1024 and env_port <= 65535:
			return env_port

	var editor_settings := EditorInterface.get_editor_settings()
	var setting_key := "nexus/bridge/port_%s" % VersionHelper.compute_project_id()
	if editor_settings != null and editor_settings.has_setting(setting_key):
		var saved := int(editor_settings.get_setting(setting_key))
		if saved >= 1024 and saved <= 65535:
			return saved
	return DefaultPort
