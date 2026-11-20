extends Node3D

signal status_changed(new_state: String)

@export var speed: float = 5.0

var current_state: String = "idle"
var last_observed_signal: String = ""


func _ready() -> void:
	set_actor_state("ready")


func set_actor_state(new_state: String) -> void:
	current_state = new_state
	status_changed.emit(new_state)


func _on_status_changed(new_state: String) -> void:
	last_observed_signal = new_state
