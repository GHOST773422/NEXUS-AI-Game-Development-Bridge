# NEXUS Adapter Plugin Manifest Specification (`nexus-adapter.manifest.json`)

**Schema Version**: `1.0`  
**Daemon Protocol Version**: `1.0.0`

---

## 1. Schema Definition

| Field | Type | Required | Rules & Validation |
| :--- | :--- | :--- | :--- |
| `manifestVersion` | `string` | Yes | Must equal `"1.0"` |
| `adapterId` | `string` | Yes | 3–80 chars `[a-zA-Z0-9._-]` |
| `displayName` | `string` | Yes | Non-empty human label |
| `version` | `string` | Yes | Strict SemVer (`MAJOR.MINOR.PATCH`) |
| `runtimeLanguage` | `string` | Yes | One of `C#`, `GDScript`, `C++`, `Python`, `NodeTS`, `Rust`, `Other` |
| `engineKind` | `string` | Yes | One of `Unity`, `Godot`, `Unreal`, `Custom`, `TestHarness` |
| `isTestAdapter` | `boolean` | Yes | Must be `true` for `TestHarness`; cannot be `true` with `Unity`/`Godot`/`Unreal` |
| `protocolVersion` | `string` | Yes | SemVer matching daemon major version (`1.x.x`) |
| `minDaemonProtocolVersion` | `string` | Optional | Defaults `"1.0.0"`; daemon version must be `>= min` |
| `maxDaemonProtocolVersion` | `string` | Optional | Defaults `"1.99.99"`; daemon version must be `<= max` |
| `transport` | `object` | Yes | `{ "kind": "stdio", "command": [...] }` OR `{ "kind": "tcp-loopback", "host": "127.0.0.1", "port": <1..65535> }` |
| `entrypoint` | `string` | Yes | Relative path to adapter entrypoint; verified if `checksumSha256` is supplied |
| `capabilities` | `string[]` | Optional | Declared capability keys |
| `requestedPermissions` | `string[]` | Optional | Every entry must match a `PermissionScope` value (`project:read`, `scene:write`, `script:write`, `assets:modify`, `editor:execute`, `tests:run`, `build:export`, `process:restricted`) |
| `supportedEngineVersions` | `string[]` | Optional | Target engine version strings |
| `checksumSha256` | `string` | Optional | Hex SHA-256 verified against `entrypoint` on installation & activation |

---

## 2. Independent Install, Validation & Removal

1. **Install (`POST /api/v1/adapters/install`)**: Parses manifest, enforces SemVer range checks, loopback host guard, `PermissionScope` validation, test-adapter honesty checks, and optional SHA-256 verification before inserting into SQLite `installed_adapters`.
2. **Pre-Activation Check**: Re-validates compatibility whenever transitioning from `Installed` / `Validated` to `Connecting`.
3. **Uninstall (`DELETE /api/v1/adapters/{adapterId}`)**: Cancels reconnection tasks, disconnects cleanly, removes capabilities and tools from registries, and deletes the persisted SQLite record.
