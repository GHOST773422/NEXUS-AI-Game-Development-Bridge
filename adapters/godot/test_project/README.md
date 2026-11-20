# NEXUS Bridge Godot 4.x Test Project

Actual Godot `4.2+` project pre-configured with `addons/nexus_bridge` enabled (`config_version=5`).

## Contents
- `project.godot`: Enables `res://addons/nexus_bridge/plugin.cfg` and sets `res://scenes/main.tscn` as main scene.
- `scenes/main.tscn`: 3D test scene (`Main` -> `Camera3D`, `DirectionalLight3D`, `TargetMarker`, `TestActor`).
- `scripts/test_actor.gd`: Sample actor script exposing `@export var speed` and `signal status_changed(new_state: String)`.
- `export_presets.cfg`: Sample `Windows Desktop` export preset verified by `godot.get_export_status`.
- `tests/nexus_godot_verification.gd`: Headless Godot verification script (`SceneTree`) checking compatibility, node manipulation, transforms, signals, GDScript `.reload()`, `.tres` persistence, and `export_presets.cfg`.

## Running Locally on Windows / Desktop Godot 4.2+

1. Keep the addon synchronized after edits to `adapters/godot/addons/nexus_bridge/`:
   ```bash
   npm run sync:godot-addon
   ```
2. Open `adapters/godot/test_project/project.godot` in Godot `4.2+`.
   - Confirm the **NEXUS Bridge** dock appears showing `Godot 4.x (Compatible)` and `Bind: 127.0.0.1:47202 (Listening)`.
3. Run the headless verification script:
   ```bash
   godot --headless --path adapters/godot/test_project --script res://tests/nexus_godot_verification.gd
   ```
4. Connect the NEXUS Python daemon against `127.0.0.1:47202` (`nexus.godot.gdscript_editor`) to exercise scene editing, script creation/compilation, signals, debugger telemetry, runtime play/stop, screenshots, and export inspection.
