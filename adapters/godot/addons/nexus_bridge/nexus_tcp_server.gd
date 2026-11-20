@tool
extends RefCounted

## Loopback TCP NDJSON JSON-RPC 2.0 Server polled safely on Godot Editor's main thread (_process).

const VersionHelper := preload("res://addons/nexus_bridge/nexus_version.gd")
const ToolRegistry := preload("res://addons/nexus_bridge/nexus_tool_registry.gd")

var handlers: RefCounted
var state_tracker: RefCounted

var _server: TCPServer
var _port: int = 47202
var _peers: Array = []
var _is_listening: bool = false


func _init(editor_handlers: RefCounted, tracker: RefCounted) -> void:
	handlers = editor_handlers
	state_tracker = tracker
	state_tracker.notification_callback = Callable(self, "broadcast_notification")


func start(port: int) -> Error:
	stop()
	_port = port
	_server = TCPServer.new()
	var err := _server.listen(port, "127.0.0.1")
	_is_listening = (err == OK)
	if not _is_listening:
		state_tracker.record_error("NEXUS_TCP_LISTEN_FAILED", "Failed binding 127.0.0.1:%d (Error %d)." % [port, err])
	return err


func stop() -> void:
	for peer_info in _peers:
		var stream: StreamPeerTCP = peer_info["stream"]
		if stream != null:
			stream.disconnect_from_host()
	_peers.clear()
	if _server != null:
		_server.stop()
		_server = null
	_is_listening = false


func is_listening() -> bool:
	return _is_listening and _server != null and _server.is_listening()


func active_port() -> int:
	return _port


func active_client_count() -> int:
	return _peers.size()


func poll() -> void:
	if not is_listening():
		return

	while _server.is_connection_available():
		var client := _server.take_connection()
		if client != null:
			client.set_no_delay(true)
			_peers.append({
				"id": "godot-%d" % Time.get_ticks_usec(),
				"stream": client,
				"buffer": "",
				"connected": false,
				"subscriptions": [],
			})

	var idx := _peers.size() - 1
	while idx >= 0:
		var peer_info: Dictionary = _peers[idx]
		var stream: StreamPeerTCP = peer_info["stream"]
		stream.poll()
		var status := stream.get_status()
		if status == StreamPeerTCP.STATUS_NONE or status == StreamPeerTCP.STATUS_ERROR:
			_peers.remove_at(idx)
			idx -= 1
			continue

		if status == StreamPeerTCP.STATUS_CONNECTED:
			var avail := stream.get_available_bytes()
			if avail > 0:
				var chunk_res := stream.get_utf8_string(avail)
				peer_info["buffer"] = str(peer_info["buffer"]) + chunk_res
				_drain_ndjson_frames(peer_info)
		idx -= 1


func _drain_ndjson_frames(peer_info: Dictionary) -> void:
	var buf := str(peer_info["buffer"])
	var nl := buf.find("\n")
	while nl != -1:
		var line := buf.substr(0, nl).strip_edges()
		buf = buf.substr(nl + 1)
		if not line.is_empty():
			var parsed: Variant = JSON.parse_string(line)
			if parsed is Dictionary:
				var response := _handle_rpc_message(peer_info, parsed)
				if not response.is_empty():
					_send_json_line(peer_info["stream"], response)
		nl = buf.find("\n")
	peer_info["buffer"] = buf


func _handle_rpc_message(peer_info: Dictionary, msg: Dictionary) -> Dictionary:
	var req_id: Variant = msg.get("id", null)
	var method := str(msg.get("method", ""))
	var params: Dictionary = msg["params"] if msg.get("params") is Dictionary else {}
	var result: Variant

	match method:
		"getEngineInfo":
			result = handlers.get_engine_info(_port)
		"discoverProjects":
			result = handlers.discover_projects(_port)
		"connect":
			peer_info["connected"] = true
			var info: Dictionary = handlers.get_engine_info(_port)
			result = {
				"connected": true,
				"isTestAdapter": false,
				"sessionId": peer_info["id"],
				"protocolVersion": "1.0.0",
				"projectId": info["projectId"],
				"godotVersion": info["engineVersion"],
				"compatible": info["compatible"],
				"timestamp": Time.get_datetime_string_from_system(true, true),
			}
		"disconnect":
			peer_info["connected"] = false
			peer_info["subscriptions"] = []
			result = {"disconnected": true, "sessionId": peer_info["id"]}
		"getCapabilities":
			var compat := VersionHelper.check_compatibility()
			result = {
				"isTestAdapter": false,
				"compatible": compat["compatible"],
				"versionSupport": compat,
				"capabilities": ToolRegistry.discover_capabilities(compat),
			}
		"listTools":
			var compat_tools := VersionHelper.check_compatibility()
			result = {
				"isTestAdapter": false,
				"compatible": compat_tools["compatible"],
				"tools": ToolRegistry.build_tool_catalog(compat_tools),
			}
		"executeTool":
			var tool_id := str(params.get("toolId", ""))
			var proj_id := str(params.get("projectId", ""))
			var rid := str(params.get("requestId", ""))
			var t_args: Dictionary = params["arguments"] if params.get("arguments") is Dictionary else {}
			result = handlers.dispatch_tool(tool_id, proj_id, rid, t_args)
		"getProjectState":
			result = handlers.get_scene_state()
		"subscribeEvents":
			var topics: Array = params["topics"] if params.get("topics") is Array else []
			peer_info["subscriptions"] = topics
			result = {"subscribed": true, "topics": topics, "isTestAdapter": false}
		"captureScreenshot":
			result = handlers.capture_screenshot(params)
		"healthCheck":
			result = {
				"responsive": true,
				"connected": peer_info["connected"],
				"isTestAdapter": false,
				"listenerPort": _port,
				"godotVersion": VersionHelper.detect_version_info()["string"],
				"isPlayingScene": EditorInterface.is_playing_scene(),
				"timestamp": Time.get_datetime_string_from_system(true, true),
			}
		_:
			if req_id == null:
				return {}
			return {
				"jsonrpc": "2.0",
				"id": req_id,
				"error": {"code": -32601, "message": "Method '%s' not supported." % method},
			}

	if req_id == null:
		return {}

	if result is Dictionary and result.get("_rpcError", false):
		return {
			"jsonrpc": "2.0",
			"id": req_id,
			"error": {
				"code": int(result.get("code", -32000)),
				"message": str(result.get("message", "Godot RPC error")),
				"data": {"errorCode": result.get("errorCode", "NEXUS_GODOT_ERROR")},
			},
		}

	return {
		"jsonrpc": "2.0",
		"id": req_id,
		"result": result,
	}


func broadcast_notification(method: String, params: Dictionary) -> void:
	if _peers.is_empty():
		return
	var frame := {"jsonrpc": "2.0", "method": method, "params": params}
	for peer_info in _peers:
		var subs: Array = peer_info.get("subscriptions", [])
		if not subs.is_empty():
			_send_json_line(peer_info["stream"], frame)


func _send_json_line(stream: StreamPeerTCP, payload: Dictionary) -> void:
	if stream == null or stream.get_status() != StreamPeerTCP.STATUS_CONNECTED:
		return
	var raw := (JSON.stringify(payload) + "\n").to_utf8_buffer()
	stream.put_data(raw)
