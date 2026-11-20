# NEXUS Unity Test Project (`2022.3.42f1`)

A standalone minimal Unity project referencing the local UPM package `com.nexus.bridge` via `Packages/manifest.json` (`"com.nexus.bridge": "file:../.."`).

## Contents

- `ProjectSettings/ProjectVersion.txt`: Targets `2022.3.42f1`.
- `Packages/manifest.json`: Loads `com.nexus.bridge` as a testable UPM package alongside `com.unity.test-framework`.
- `Assets/Scenes/Main.unity`: Baseline scene with `Main Camera` and `TestActor`.
- `Assets/Scripts/TestActor.cs`: Sample MonoBehaviour verified during scene, transform, and Play Mode checks.

## Verification on Windows Unity Host

1. Open `adapters/unity/test_project` in **Unity 2022.3 LTS+**.
2. Open **Window → NEXUS Bridge** (`NexusBridgeWindow`) and verify TCP loopback listener `127.0.0.1:47201` starts.
3. Open **Window → General → Test Runner → EditMode** and run `NexusUnityIntegrationTests`.
4. Note: Headless Linux containers without `Unity.exe` validate the project structure, manifest references, C# source integrity, and wire protocol externally via `tests/python/`.
