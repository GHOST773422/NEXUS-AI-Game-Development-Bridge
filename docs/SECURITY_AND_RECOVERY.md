# NEXUS Security, Permissions & Recovery Architecture (Stages 8–9)

This document defines the security model, capability-based permission categories, autonomous safety gates, and crash/rollback recovery mechanisms implemented across `core/nexus_core/`.

---

## 1. Capability-Based Permission Categories

Every tool registered in `CoreToolRegistry` or routed through `AutonomousOrchestrator` and `NexusMCPServer` maps cleanly to one of 7 capability-based permission categories defined in `core/nexus_core/security.py` (`PERMISSION_CATEGORIES`):

| Category | Permission Scopes | Destructive | Explicit Gate Required |
| :--- | :--- | :--- | :--- |
| **Read-only inspection** | `project:read` | No | No |
| **Non-destructive modification** | `editor:execute` | No | No |
| **Project modification** | `scene:write`, `assets:modify` | Yes | `assets:modify` requires approval |
| **Script execution** | `script:write`, `tests:run` | `script:write` | Audited + checkpointed |
| **Runtime control** | `editor:execute`, `tests:run` | No | No |
| **Build and export** | `build:export` | Yes | Always requires operator approval |
| **External process access** | `process:restricted` | Yes | Always blocked inside autonomous execution; restricted to executable allowlist |

---

## 2. Security Controls (`core/nexus_core/security.py`)

1. **Tool Input Validation (`validate_tool_arguments`)**:
   - Validates tool identifier grammar (`_TOOL_ID_RE`), enforces JSON object root, caps argument keys (`<= 64`), array sizes (`<= 500`), and recursion depth (`<= 8`), and rejects `NUL` (`\x00`) bytes and control characters.
   - Blocks shell metacharacters (`;`, `&`, `|`, `` ` ``, `$`, `>`, `<`) and rejects any executable not present in `ALLOWED_PROCESS_NAMES` (`Unity`, `Godot`, `dotnet`).
2. **Project-Root Sandboxing & Traversal Prevention (`resolve_engine_resource_path`)**:
   - Translates `res://...` and `Assets/...` cleanly relative to the registered `ProjectRecord.root_path`.
   - Rejects `..` path traversal segments cleanly across both POSIX paths and cross-platform Windows drive (`C:/...`) / UNC (`//server/...`) strings.
3. **Network Restriction (`assert_loopback_bind`)**:
   - Refuses daemon startup unless `bind_host` is strictly `127.0.0.1`, `localhost`, or `::1`.
4. **Local Connection Authentication**:
   - Every `/api/v1/*` REST endpoint, WebSocket connection, and MCP Streamable HTTP `/mcp` request requires constant-time `hmac.compare_digest` verification of the local `Bearer` token (`daemon.token`).
5. **Credential Protection & Log Redaction (`redact_sensitive_fields`)**:
   - Keys, passwords, API tokens, and `Authorization` headers are redacted (`[REDACTED]`) before persisting `failed_operations`, `audit_logs`, or JSON stdout logs.
6. **Plugin & Adapter Integrity Validation (`core/nexus_core/adapters/manifest.py`)**:
   - Enforces manifest schema `1.0`, SemVer compatibility against daemon protocol `1.0.0`, loopback-only TCP host rules, `entrypoint` traversal prevention, and mandatory SHA-256 verification when `checksumSha256` is declared.
7. **Strict Engine Result Verification (`AutonomousOrchestrator`)**:
   - Never treats HTTP/RPC transport `200 OK` as proof of success. Tool outputs with `verified: false`, `isError: true`, `success: false`, `status: "Failed"`, or non-empty `error` fields trigger `ValidationError` and record a `failed_operations` row.

---

## 3. Checkpoints, Operation Journaling & Recovery

### 3.1 SQLite Persistence (`core/nexus_core/storage.py`)
- **`checkpoints`**: Tracks `id`, `task_id`, `project_id`, and disk path to `manifest.json`.
- **`operation_journal`**: Persists every planned operation (`task_id`, `op_id`, `tool_id`, `fingerprint`, `status` [`Running` → `Succeeded` / `Failed` / `Interrupted`], `reversible`, `file_changes_json`, `started_at`, `finished_at`).
- **`failed_operations`**: Records every failure (`arguments_json` sanitized via `redact_sensitive_fields`, SHA-256 `fingerprint`, `error_code`, `error_message`, live engine `diagnostics_json`, and `repair_attempted`).

### 3.2 File Change Manifests & Selective Rollback (`core/nexus_core/checkpoints.py`)
- Before executing mutating operations (Phase 9), `CheckpointManager.create_checkpoint()` snapshots target files (`backupFile`, `beforeHash` SHA-256, `existed` boolean) under `~/.nexus/checkpoints/<id>/`.
- On task completion or failure, `finalize_file_change_manifest()` computes `afterHash` and writes `file_change_manifest.json` classifying each file (`created`, `modified`, `deleted`, `unchanged`).
- `POST /api/v1/tasks/:id/rollback` (with optional `{"files": ["Assets/Scripts/FileA.cs"]}`) or MCP `nexus_control_task(..., action="rollback", files=[...])` invokes `CheckpointManager.selective_rollback()`:
  - **Selective**: Restores or removes only the requested target files inside the sandbox while preserving other changes.
  - **Full**: Restores all checkpointed files and deletes newly created files from that checkpoint.

### 3.3 Daemon Restart & Interrupted Task Recovery (`core/nexus_core/task_manager.py`)
- On boot, `NexusDaemon.start()` runs `TaskManager.recover_interrupted_tasks()`:
  - Detects any tasks left in `Running` status from an unclean termination.
  - Marks in-flight `operation_journal` rows (`Running`) as `Interrupted` with `error_code = "DAEMON_RESTART_INTERRUPTED"`.
  - Transitions orphaned tasks cleanly from `Running` → `Unavailable`, preserves their `checkpointId`, logs `task.recover_interrupted` in `audit_logs`, and surfaces `recoveredInterruptedTasks` in `/health`.
