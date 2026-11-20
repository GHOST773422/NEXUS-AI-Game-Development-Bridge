@tool
extends RefCounted

## Godot 4.x State, DebuggerPlugin, ExportPlugin & Error Ring Buffer.

const MAX_ERRORS := 250
const MAX_DEBUGGER_EVENTS := 250


class NexusEditorDebuggerPlugin extends EditorDebuggerPlugin:
	var state_tracker: RefCounted

	func _has_capture(capture: String) -> bool:
		return capture == "nexus" or capture.begins_with("nexus:")

	func _capture(message: String, data: Array, session_id: int) -> bool:
		if state_tracker != null:
			state_tracker.record_debugger_message(session_id, message, data)
			return true
		return false

	func _setup_session(session_id: int) -> void:
		var session := get_session(session_id)
		if session == null or state_tracker == null:
			return
		session.started.connect(func() -> void: state_tracker.on_debug_session_event(session_id, "started"))
		session.stopped.connect(func() -> void: state_tracker.on_debug_session_event(session_id, "stopped"))
		session.breaked.connect(func(can_debug: bool) -> void: state_tracker.on_debug_session_event(session_id, "breaked", {"canDebug": can_debug}))
		session.continued.connect(func() -> void: state_tracker.on_debug_session_event(session_id, "continued"))


class NexusEditorExportPlugin extends EditorExportPlugin:
	var state_tracker: RefCounted
	var _active_preset_name: String = ""

	func _get_name() -> String:
		return "NexusExportTelemetry"

	func _export_begin(features: PackedStringArray, is_debug: bool, path: String, flags: int) -> void:
		_active_preset_name = path.get_file()
		if state_tracker != null:
			state_tracker.on_export_started(path, Array(features), is_debug)

	func _export_end() -> void:
		if state_tracker != null:
			state_tracker.on_export_finished(_active_preset_name)


class StateTracker extends RefCounted:
	var debugger_plugin: NexusEditorDebuggerPlugin
	var export_plugin: NexusEditorExportPlugin
	var errors: Array = []
	var debugger_events: Array = []
	var last_export: Dictionary = {"hasExportHistory": false, "status": "Idle"}
	var runtime_started_msec: int = 0
	var notification_callback: Callable

	func _init() -> void:
		debugger_plugin = NexusEditorDebuggerPlugin.new()
		debugger_plugin.state_tracker = self
		export_plugin = NexusEditorExportPlugin.new()
		export_plugin.state_tracker = self

	func emit_notification(method: String, params: Dictionary) -> void:
		if notification_callback.is_valid():
			notification_callback.call(method, params)

	func record_error(code: String, message: String, context: Dictionary = {}) -> void:
		var entry := {
			"timestamp": Time.get_datetime_string_from_system(true, true),
			"code": code,
			"message": message,
			"context": context,
		}
		errors.append(entry)
		if errors.size() > MAX_ERRORS:
			errors.pop_front()
		emit_notification("adapter.log", {"severity": "Error", "code": code, "message": message})

	func on_debug_session_event(session_id: int, event_name: String, extra: Dictionary = {}) -> void:
		var entry := {
			"timestamp": Time.get_datetime_string_from_system(true, true),
			"sessionId": session_id,
			"event": event_name,
			"extra": extra,
		}
		debugger_events.append(entry)
		if debugger_events.size() > MAX_DEBUGGER_EVENTS:
			debugger_events.pop_front()
		emit_notification("adapter.event", {"event": "debugger.%s" % event_name, "sessionId": session_id})

	func record_debugger_message(session_id: int, message: String, data: Array) -> void:
		var entry := {
			"timestamp": Time.get_datetime_string_from_system(true, true),
			"sessionId": session_id,
			"message": message,
			"data": data.duplicate(true),
		}
		debugger_events.append(entry)
		if debugger_events.size() > MAX_DEBUGGER_EVENTS:
			debugger_events.pop_front()
		emit_notification("adapter.event", {"event": "debugger.capture", "message": message, "sessionId": session_id})

	func on_export_started(path: String, features: Array, is_debug: bool) -> void:
		last_export = {
			"hasExportHistory": true,
			"status": "InProgress",
			"outputPath": path,
			"features": features,
			"isDebug": is_debug,
			"startedAt": Time.get_datetime_string_from_system(true, true),
		}
		emit_notification("adapter.event", {"event": "export.started", "outputPath": path})

	func on_export_finished(preset_file: String) -> void:
		last_export["status"] = "Completed"
		last_export["finishedAt"] = Time.get_datetime_string_from_system(true, true)
		last_export["artifact"] = preset_file
		emit_notification("adapter.event", {"event": "export.finished", "artifact": preset_file})

	func get_debugger_snapshot() -> Dictionary:
		var sessions: Array = []
		if debugger_plugin != null:
			for s in debugger_plugin.get_sessions():
				if s == null:
					continue
				sessions.append({
					"isActive": s.is_active(),
					"isBreaked": s.is_breaked(),
					"isDebuggable": s.is_debuggable(),
				})
		return {
			"sessionCount": sessions.size(),
			"sessions": sessions,
			"recentEvents": debugger_events.slice(max(0, debugger_events.size() - 50)),
		}

	func get_recent_errors(limit: int = 50, clear: bool = false) -> Dictionary:
		var recent := errors.slice(max(0, errors.size() - clampi(limit, 1, MAX_ERRORS)))
		if clear:
			errors.clear()
		var engine_log_tail := _read_godot_log_tail(30)
		return {
			"adapterErrors": recent,
			"godotLogTail": engine_log_tail,
		}

	func _read_godot_log_tail(max_lines: int) -> Array:
		var log_path := OS.get_user_data_dir().path_join("logs/godot.log")
		if not FileAccess.file_exists(log_path):
			return []
		var file := FileAccess.open(log_path, FileAccess.READ)
		if file == null:
			return []
		var text := file.get_as_text()
		var lines := text.split("\n", false)
		var start := max(0, lines.size() - max_lines)
		var out: Array = []
		for i in range(start, lines.size()):
			if lines[i].contains("ERROR") or lines[i].contains("WARNING") or lines[i].contains("SCRIPT"):
				out.append(lines[i])
		return out
