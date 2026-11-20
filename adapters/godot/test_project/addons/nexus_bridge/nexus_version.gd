@tool
extends RefCounted
class_name NexusGodotVersion

## Godot 4.2+ Version Detection, Capability Compatibility & Deterministic Project Identity.

const MIN_MAJOR := 4
const MIN_MINOR := 2


static func detect_version_info() -> Dictionary:
	var info := Engine.get_version_info()
	var major := int(info.get("major", 0))
	var minor := int(info.get("minor", 0))
	var patch := int(info.get("patch", 0))
	var status := str(info.get("status", "stable"))
	return {
		"major": major,
		"minor": minor,
		"patch": patch,
		"status": status,
		"string": str(info.get("string", "%d.%d.%d" % [major, minor, patch])),
		"hex": int(info.get("hex", 0)),
	}


static func check_compatibility() -> Dictionary:
	var ver := detect_version_info()
	var major := int(ver["major"])
	var minor := int(ver["minor"])
	var is_compatible := major == MIN_MAJOR and minor >= MIN_MINOR

	var reasons: Array = []
	if major != MIN_MAJOR:
		reasons.append("Unsupported Godot major version %d; NEXUS requires Godot 4.2+." % major)
	elif minor < MIN_MINOR:
		reasons.append("Godot 4.%d is below minimum supported Godot 4.2." % minor)

	return {
		"compatible": is_compatible,
		"version": ver,
		"minimumSupported": "4.2.0",
		"hasEditorDebuggerPlugin": major >= 4 and minor >= 2,
		"hasEditorUndoRedoManager": major >= 4,
		"hasEditorViewportCapture": major >= 4 and minor >= 2,
		"hasResourceUid": major >= 4 and minor >= 3,
		"reasons": reasons,
	}


static func get_project_root_path() -> String:
	return ProjectSettings.globalize_path("res://").rstrip("/\\")


static func compute_project_id(root_path: String = "") -> String:
	var target := root_path if not root_path.is_empty() else get_project_root_path()
	var normalized := target.replace("\\", "/").to_lower().rstrip("/")
	var ctx := HashingContext.new()
	ctx.start(HashingContext.HASH_SHA256)
	ctx.update(normalized.to_utf8_buffer())
	var digest := ctx.finish().hex_encode()
	return "godot-%s" % digest.substr(0, 12)
