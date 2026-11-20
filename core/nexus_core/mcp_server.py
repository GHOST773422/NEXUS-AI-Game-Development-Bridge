"""NEXUS Model Context Protocol (MCP) Server (Stdio + Optional Loopback Streamable HTTP)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import contextlib
from dataclasses import dataclass, field
import json
from pathlib import Path
import socket
import sys
from typing import TYPE_CHECKING, Any
import uuid

from core.nexus_core.config import APP_VERSION
from core.nexus_core.errors import AuthenticationError, NexusCoreError, NotFoundError, ValidationError
from sdk.python.nexus_sdk import NexusStatus, PermissionScope

if TYPE_CHECKING:
    from core.nexus_core.daemon import NexusDaemon

MCP_PROTOCOL_VERSION = "2025-03-26"

CoreToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(slots=True)
class MCPBridgeToolDef:
    name: str
    description: str
    input_schema: dict[str, Any]
    required_scope: PermissionScope
    read_only_hint: bool
    handler: CoreToolHandler


@dataclass(slots=True)
class MCPServerConfig:
    bind_host: str = "127.0.0.1"
    http_port: int = 47102
    require_bearer_token: bool = True
    supported_transports: list[str] = field(
        default_factory=lambda: ["stdio", "Streamable HTTP"]
    )


class NexusMCPServer:
    """Real MCP JSON-RPC 2.0 server backed by NexusDaemon, CoreToolRegistry, and PermissionManager."""

    def __init__(
        self,
        daemon: "NexusDaemon",
        config: MCPServerConfig | None = None,
    ) -> None:
        self.daemon = daemon
        self.config = config or MCPServerConfig(
            bind_host=daemon.config.bind_host,
            http_port=daemon.config.mcp_http_port,
            require_bearer_token=daemon.config.require_bearer_token,
        )
        self._bridge_tools: dict[str, MCPBridgeToolDef] = {}
        self._engine_tool_handlers: dict[str, CoreToolHandler] = {}
        self._register_core_bridge_tools()

    def _register_core_bridge_tools(self) -> None:
        async def handle_capabilities(_args: dict[str, Any]) -> dict[str, Any]:
            return await self.daemon.capabilities.discover()

        async def handle_diagnostics(_args: dict[str, Any]) -> dict[str, Any]:
            return await self.daemon.diagnostics.collect()

        async def handle_list_engines(_args: dict[str, Any]) -> dict[str, Any]:
            return {
                "engines": [
                    e.to_dict()
                    for e in self.daemon.engines.list_engines(
                        connected_adapters=self.daemon.adapters.list_adapters()
                    )
                ]
            }

        async def handle_list_projects(_args: dict[str, Any]) -> dict[str, Any]:
            projects = await self.daemon.projects.list_projects()
            return {"projects": [p.to_dict() for p in projects]}

        async def handle_register_project(args: dict[str, Any]) -> dict[str, Any]:
            record = await self.daemon.projects.register_project(
                name=str(args.get("name", "")),
                engine=str(args.get("engine", "")),
                root_path=str(args.get("rootPath", "")),
                engine_version=str(args.get("engineVersion", "Unverified")),
                notes=str(args.get("notes", "")),
                require_existing_dir=bool(args.get("requireExistingDir", False)),
            )
            return {"project": record.to_dict()}

        async def handle_list_tasks(_args: dict[str, Any]) -> dict[str, Any]:
            return {"tasks": await self.daemon.tasks.list_tasks()}

        async def handle_create_task_draft(args: dict[str, Any]) -> dict[str, Any]:
            task = await self.daemon.tasks.create_task_draft(
                project_id=str(args.get("projectId", "")),
                title=str(args.get("title", "")),
                priority=str(args.get("priority", "normal")),
                agent_id=str(args.get("agentId", "mcp_client")),
                operations=args.get("operations") if isinstance(args.get("operations"), list) else None,
                retry_policy=args.get("retryPolicy") if isinstance(args.get("retryPolicy"), dict) else None,
                execution_limits=args.get("executionLimits") if isinstance(args.get("executionLimits"), dict) else None,
                adapter_id=str(args["adapterId"]) if args.get("adapterId") else None,
                approved_scopes=args.get("approvedScopes") if isinstance(args.get("approvedScopes"), list) else None,
            )
            return {"task": task}

        async def handle_submit_autonomous_task(args: dict[str, Any]) -> dict[str, Any]:
            task = await self.daemon.tasks.create_task_draft(
                project_id=str(args.get("projectId", "")),
                title=str(args.get("title", "")),
                priority=str(args.get("priority", "normal")),
                agent_id=str(args.get("agentId", "mcp_client")),
                operations=args.get("operations") if isinstance(args.get("operations"), list) else None,
                retry_policy=args.get("retryPolicy") if isinstance(args.get("retryPolicy"), dict) else None,
                execution_limits=args.get("executionLimits") if isinstance(args.get("executionLimits"), dict) else None,
                adapter_id=str(args["adapterId"]) if args.get("adapterId") else None,
                approved_scopes=args.get("approvedScopes") if isinstance(args.get("approvedScopes"), list) else None,
            )
            if bool(args.get("executeNow", True)):
                task = await self.daemon.tasks.execute_task(
                    task["id"],
                    adapter_id=str(args["adapterId"]) if args.get("adapterId") else None,
                    approved_scopes=args.get("approvedScopes") if isinstance(args.get("approvedScopes"), list) else None,
                )
            return {"task": task}

        async def handle_get_task_status(args: dict[str, Any]) -> dict[str, Any]:
            task_id = str(args.get("taskId", "")).strip()
            return {"task": await self.daemon.tasks.get_task(task_id)}

        async def handle_control_task(args: dict[str, Any]) -> dict[str, Any]:
            task_id = str(args.get("taskId", "")).strip()
            action = str(args.get("action", "")).strip().lower()
            if action == "approve":
                task = await self.daemon.tasks.approve_task_checkpoint(
                    task_id,
                    approved=bool(args.get("approved", True)),
                    approved_scopes=args.get("approvedScopes") if isinstance(args.get("approvedScopes"), list) else None,
                    resume_execution=bool(args.get("resumeExecution", True)),
                    adapter_id=str(args["adapterId"]) if args.get("adapterId") else None,
                )
                return {"task": task}
            if action == "rollback" and isinstance(args.get("files"), list):
                files_list = [str(f) for f in args["files"] if isinstance(f, str) and f.strip()]
                task = await self.daemon.tasks.rollback_task(task_id, target_files=files_list)
                return {"task": task}
            task = await self.daemon.tasks.control_task(
                task_id,
                action,
                adapter_id=str(args["adapterId"]) if args.get("adapterId") else None,
                approved_scopes=args.get("approvedScopes") if isinstance(args.get("approvedScopes"), list) else None,
            )
            return {"task": task}

        async def handle_get_task_recovery(args: dict[str, Any]) -> dict[str, Any]:
            task_id = str(args.get("taskId", "")).strip()
            return await self.daemon.tasks.get_task_recovery_details(task_id)

        async def handle_list_concurrency_locks(_args: dict[str, Any]) -> dict[str, Any]:
            return self.daemon.concurrency.snapshot()

        defs = [
            MCPBridgeToolDef(
                name="nexus_get_capabilities",
                description="Inspect NEXUS host OS capabilities, connected engine count, and verified tool registry count.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                required_scope=PermissionScope.READ_PROJECT,
                read_only_hint=True,
                handler=handle_capabilities,
            ),
            MCPBridgeToolDef(
                name="nexus_get_diagnostics",
                description="Collect daemon diagnostics including PID, Python version, safe configuration, and SQLite integrity.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                required_scope=PermissionScope.READ_PROJECT,
                read_only_hint=True,
                handler=handle_diagnostics,
            ),
            MCPBridgeToolDef(
                name="nexus_list_engines",
                description="List Unity and Godot engine binary probes, installation paths, and native plugin connection states.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                required_scope=PermissionScope.READ_PROJECT,
                read_only_hint=True,
                handler=handle_list_engines,
            ),
            MCPBridgeToolDef(
                name="nexus_list_projects",
                description="List all persisted Unity and Godot projects registered in the NEXUS SQLite registry.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                required_scope=PermissionScope.READ_PROJECT,
                read_only_hint=True,
                handler=handle_list_projects,
            ),
            MCPBridgeToolDef(
                name="nexus_register_project",
                description="Register a Unity or Godot project path in SQLite after PermissionManager sandbox checks.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "engine": {"type": "string", "enum": ["Unity", "Godot"]},
                        "rootPath": {"type": "string"},
                        "engineVersion": {"type": "string"},
                        "notes": {"type": "string"},
                    },
                    "required": ["name", "engine", "rootPath"],
                    "additionalProperties": False,
                },
                required_scope=PermissionScope.WRITE_SCRIPT,
                read_only_hint=False,
                handler=handle_register_project,
            ),
            MCPBridgeToolDef(
                name="nexus_list_tasks",
                description="List persisted multi-phase autonomous task plans, priorities, progress, and statuses.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                required_scope=PermissionScope.READ_PROJECT,
                read_only_hint=True,
                handler=handle_list_tasks,
            ),
            MCPBridgeToolDef(
                name="nexus_create_task_draft",
                description="Create a persistent NEXUS task execution plan draft attached to a registered project.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "projectId": {"type": "string"},
                        "title": {"type": "string"},
                        "priority": {"type": "string", "enum": ["low", "normal", "high", "critical"]},
                        "agentId": {"type": "string"},
                    },
                    "required": ["projectId", "title"],
                    "additionalProperties": False,
                },
                required_scope=PermissionScope.WRITE_SCRIPT,
                read_only_hint=False,
                handler=handle_create_task_draft,
            ),
            MCPBridgeToolDef(
                name="nexus_submit_autonomous_task",
                description="Submit and optionally execute a checkpointed 16-phase autonomous development task against a live connected engine.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "projectId": {"type": "string"},
                        "title": {"type": "string"},
                        "priority": {"type": "string", "enum": ["low", "normal", "high", "critical"]},
                        "agentId": {"type": "string"},
                        "adapterId": {"type": "string"},
                        "executeNow": {"type": "boolean"},
                        "operations": {"type": "array"},
                        "retryPolicy": {"type": "object"},
                        "executionLimits": {"type": "object"},
                        "approvedScopes": {"type": "array"},
                    },
                    "required": ["projectId", "title"],
                    "additionalProperties": False,
                },
                required_scope=PermissionScope.EXECUTE_EDITOR_ACTION,
                read_only_hint=False,
                handler=handle_submit_autonomous_task,
            ),
            MCPBridgeToolDef(
                name="nexus_get_task_status",
                description="Inspect an autonomous task's phase breakdown, context, diagnostics, screenshots, checkpoint ID, and completion report.",
                input_schema={
                    "type": "object",
                    "properties": {"taskId": {"type": "string"}},
                    "required": ["taskId"],
                    "additionalProperties": False,
                },
                required_scope=PermissionScope.READ_PROJECT,
                read_only_hint=True,
                handler=handle_get_task_status,
            ),
            MCPBridgeToolDef(
                name="nexus_control_task",
                description="Control an autonomous task (execute, pause, resume, cancel, selective rollback, or approve checkpoint).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "taskId": {"type": "string"},
                        "action": {"type": "string", "enum": ["execute", "pause", "resume", "cancel", "rollback", "approve"]},
                        "adapterId": {"type": "string"},
                        "approved": {"type": "boolean"},
                        "approvedScopes": {"type": "array"},
                        "resumeExecution": {"type": "boolean"},
                        "files": {"type": "array"},
                    },
                    "required": ["taskId", "action"],
                    "additionalProperties": False,
                },
                required_scope=PermissionScope.EXECUTE_EDITOR_ACTION,
                read_only_hint=False,
                handler=handle_control_task,
            ),
            MCPBridgeToolDef(
                name="nexus_get_task_recovery",
                description="Inspect persistent operation journal, failed operation records, checkpoints, and file change manifest for a task.",
                input_schema={
                    "type": "object",
                    "properties": {"taskId": {"type": "string"}},
                    "required": ["taskId"],
                    "additionalProperties": False,
                },
                required_scope=PermissionScope.READ_PROJECT,
                read_only_hint=True,
                handler=handle_get_task_recovery,
            ),
            MCPBridgeToolDef(
                name="nexus_list_concurrency_locks",
                description="Inspect active multi-agent project locks, resource claims, and in-flight operations.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                required_scope=PermissionScope.READ_PROJECT,
                read_only_hint=True,
                handler=handle_list_concurrency_locks,
            ),
        ]
        for item in defs:
            self._bridge_tools[item.name] = item

    def attach_engine_tool_handler(self, tool_id: str, handler: CoreToolHandler) -> None:
        """Attaches an execution handler for a verified tool present in CoreToolRegistry."""
        self.daemon.tools.get_tool(tool_id)
        self._engine_tool_handlers[tool_id] = handler

    def list_tools(self) -> list[dict[str, Any]]:
        """Dynamically lists NEXUS bridge tools plus any verified engine adapter tools."""
        result: list[dict[str, Any]] = []
        for tool_def in self._bridge_tools.values():
            result.append(
                {
                    "name": tool_def.name,
                    "description": tool_def.description,
                    "inputSchema": tool_def.input_schema,
                    "annotations": {
                        "readOnlyHint": tool_def.read_only_hint,
                        "destructiveHint": False,
                        "idempotentHint": tool_def.read_only_hint,
                    },
                }
            )
        for engine_tool in self.daemon.tools.list_tools():
            perms = [str(p) for p in engine_tool.get("required_permissions", [])]
            requires_approval = any(
                self.daemon.permissions.requires_approval(PermissionScope(p))
                for p in perms
            )
            read_only = perms == [PermissionScope.READ_PROJECT.value]
            result.append(
                {
                    "name": engine_tool["id"],
                    "description": engine_tool["description"],
                    "inputSchema": engine_tool["input_schema"],
                    "annotations": {
                        "readOnlyHint": read_only,
                        "destructiveHint": requires_approval,
                        "engines": [str(e) for e in engine_tool.get("engine_compatibility", [])],
                        "category": engine_tool["category"],
                    },
                }
            )
        return result

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Executes either a verified CoreToolRegistry engine tool or a core bridge tool."""
        if name in self._bridge_tools:
            tool_def = self._bridge_tools[name]
            payload = await tool_def.handler(arguments)
            await self.daemon.storage.record_audit(
                "mcp_client",
                f"mcp.tool_call:{name}",
                "success",
                detail={"readOnly": tool_def.read_only_hint},
            )
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(payload, separators=(",", ":"), ensure_ascii=True),
                    }
                ],
                "isError": False,
            }

        contract = self.daemon.tools.get_tool(name)
        if contract.implementation_status in {NexusStatus.PLANNED, NexusStatus.UNAVAILABLE}:
            raise ValidationError(
                f"Tool '{name}' is '{contract.implementation_status.value}' and cannot execute."
            )
        gated_scopes = self.daemon.permissions.requires_approval_for_tool(
            name, list(contract.required_permissions)
        )
        for scope in gated_scopes:
            if not bool(arguments.get("_approved")):
                raise ValidationError(
                    f"Tool '{name}' requires explicit operator approval for scope '{scope.value}'.",
                    details={"toolId": name, "scope": scope.value},
                )

        project_id_arg = str(arguments.get("projectId") or "").strip()
        resolved_root: Path | None = None
        if project_id_arg and self.daemon.storage.is_initialized:
            rows = await self.daemon.storage.execute(
                "SELECT root_path FROM projects WHERE id = ?",
                (project_id_arg,),
            )
            if rows:
                resolved_root = Path(str(rows[0]["root_path"]))

        clean_args = {k: v for k, v in arguments.items() if k not in {"_approved", "projectId"}}
        self.daemon.permissions.validate_tool_arguments(
            name,
            clean_args,
            project_root=resolved_root,
        )

        handler = self._engine_tool_handlers.get(name)
        if handler is not None:
            payload = await handler(arguments)
        else:
            matched_adapter = next(
                (
                    rec
                    for rec in self.daemon.adapters.list_adapters()
                    if not rec["isTestAdapter"]
                    and rec["lifecycleState"] == NexusStatus.CONNECTED.value
                    and name.startswith(f"{rec['adapterId']}.")
                ),
                None,
            )
            if matched_adapter is None:
                raise NotFoundError(
                    f"No active engine adapter handler attached for tool '{name}'.",
                    details={"toolId": name},
                )
            adapter_id = str(matched_adapter["adapterId"])
            raw_tool_id = name[len(adapter_id) + 1 :]
            project_id = str(
                arguments.get("projectId")
                or (matched_adapter.get("engineInfo") or {}).get("projectId")
                or ""
            )
            payload = await self.daemon.adapters.execute_tool(
                adapter_id=adapter_id,
                tool_id=raw_tool_id,
                project_id=project_id,
                arguments=clean_args,
                approved=bool(arguments.get("_approved")),
                project_root=resolved_root,
            )
        await self.daemon.storage.record_audit(
            "mcp_client",
            f"mcp.engine_tool_call:{name}",
            "success",
            detail={"engines": [e.value for e in contract.engine_compatibility]},
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(payload, separators=(",", ":"), ensure_ascii=True),
                }
            ],
            "isError": False,
        }

    def list_resources(self) -> list[dict[str, Any]]:
        return [
            {
                "uri": "nexus://engines",
                "name": "NEXUS Engine Adapters",
                "description": "Detected Unity & Godot installations and adapter connection status.",
                "mimeType": "application/json",
            },
            {
                "uri": "nexus://projects",
                "name": "NEXUS Registered Projects",
                "description": "Persistent SQLite engine project registry.",
                "mimeType": "application/json",
            },
            {
                "uri": "nexus://capabilities",
                "name": "NEXUS Runtime Capabilities",
                "description": "Available host capabilities, adapter counts, and planned tool categories.",
                "mimeType": "application/json",
            },
            {
                "uri": "nexus://tasks",
                "name": "NEXUS Task Plans & Status",
                "description": "Persisted 12-step task drafts and task statuses.",
                "mimeType": "application/json",
            },
            {
                "uri": "nexus://diagnostics",
                "name": "NEXUS Daemon Diagnostics",
                "description": "Live daemon PID, SQLite integrity check, and redacted runtime configuration.",
                "mimeType": "application/json",
            },
            {
                "uri": "nexus://providers",
                "name": "NEXUS AI Providers (Metadata Only)",
                "description": "Configured built-in AI provider metadata without raw secrets.",
                "mimeType": "application/json",
            },
        ]

    async def read_resource(self, uri: str) -> dict[str, Any]:
        if uri == "nexus://engines":
            data: Any = {
                "engines": [
                    e.to_dict()
                    for e in self.daemon.engines.list_engines(
                        connected_adapters=self.daemon.adapters.list_adapters()
                    )
                ]
            }
        elif uri == "nexus://projects":
            projects = await self.daemon.projects.list_projects()
            data = {"projects": [p.to_dict() for p in projects]}
        elif uri == "nexus://capabilities":
            data = await self.daemon.capabilities.discover()
        elif uri == "nexus://tasks":
            data = {
                "tasks": await self.daemon.tasks.list_tasks(),
                "concurrency": self.daemon.concurrency.snapshot(),
            }
        elif uri == "nexus://diagnostics":
            data = await self.daemon.diagnostics.collect()
        elif uri == "nexus://providers":
            data = {"providers": await self.daemon.providers.list_providers()}
        else:
            raise NotFoundError(f"Unknown MCP resource URI '{uri}'.", details={"uri": uri})

        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(data, separators=(",", ":"), ensure_ascii=True),
                }
            ]
        }

    def list_prompts(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "inspect_project_architecture",
                "description": "Generates a grounded inspection prompt for a registered Unity or Godot project.",
                "arguments": [
                    {
                        "name": "projectId",
                        "description": "Registered project identifier from nexus://projects.",
                        "required": True,
                    }
                ],
            },
            {
                "name": "plan_engine_automation_task",
                "description": "Creates a 12-step NEXUS workflow plan respecting current engine connection status.",
                "arguments": [
                    {"name": "goal", "description": "Game development objective.", "required": True},
                    {
                        "name": "projectId",
                        "description": "Optional registered project ID.",
                        "required": False,
                    },
                ],
            },
            {
                "name": "diagnose_bridge_health",
                "description": "Audits NEXUS daemon diagnostics, SQLite health, and engine readiness.",
                "arguments": [],
            },
        ]

    async def get_prompt(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "inspect_project_architecture":
            project_id = str(arguments.get("projectId", "")).strip()
            if not project_id:
                raise ValidationError("Prompt 'inspect_project_architecture' requires projectId.")
            project = await self.daemon.projects.get_project(project_id)
            text = (
                f"Inspect NEXUS registered project '{project.name}' ({project.engine}) at "
                f"'{project.root_path}'. Current adapter status: {project.status}. "
                f"Use nexus_get_capabilities and nexus_list_engines before proposing engine actions."
            )
            return {
                "description": "Project architecture inspection prompt",
                "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
            }

        if name == "plan_engine_automation_task":
            goal = str(arguments.get("goal", "")).strip() or "Analyze project and plan next milestone"
            project_id = str(arguments.get("projectId", "")).strip() or "unspecified"
            caps = await self.daemon.capabilities.discover()
            text = (
                f"Create a safe 12-step NEXUS execution plan for goal: '{goal}' (projectId: {project_id}). "
                f"Connected engine adapters: {caps['connectedEngineCount']}, "
                f"verified engine tools: {caps['registeredToolCount']}."
            )
            return {
                "description": "12-step automation task planner",
                "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
            }

        if name == "diagnose_bridge_health":
            diag = await self.daemon.diagnostics.collect()
            text = (
                "Analyze this live NEXUS diagnostics snapshot and report any disconnected adapters, "
                "missing project paths, or configuration issues:\n"
                + json.dumps(diag, indent=2, ensure_ascii=True)
            )
            return {
                "description": "Bridge health diagnostics prompt",
                "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
            }

        raise NotFoundError(f"Unknown MCP prompt '{name}'.", details={"prompt": name})

    async def handle_jsonrpc(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Handles a single MCP JSON-RPC 2.0 request or notification."""
        req_id = payload.get("id")
        method = str(payload.get("method", ""))
        params = payload.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": "params must be a JSON object."},
            }

        if method == "notifications/initialized":
            return None

        try:
            if method == "initialize":
                result: Any = {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {"listChanged": True},
                        "resources": {"subscribe": False, "listChanged": False},
                        "prompts": {"listChanged": False},
                    },
                    "serverInfo": {"name": "nexus-mcp", "version": APP_VERSION},
                }
            elif method == "ping":
                result = {"status": "ok"}
            elif method == "tools/list":
                result = {"tools": self.list_tools()}
            elif method == "tools/call":
                tool_name = str(params.get("name", ""))
                tool_args = params.get("arguments") or {}
                if not isinstance(tool_args, dict):
                    raise ValidationError("tools/call arguments must be an object.")
                result = await self.call_tool(tool_name, tool_args)
            elif method == "resources/list":
                result = {"resources": self.list_resources()}
            elif method == "resources/read":
                result = await self.read_resource(str(params.get("uri", "")))
            elif method == "prompts/list":
                result = {"prompts": self.list_prompts()}
            elif method == "prompts/get":
                p_args = params.get("arguments") or {}
                result = await self.get_prompt(
                    str(params.get("name", "")),
                    p_args if isinstance(p_args, dict) else {},
                )
            else:
                if req_id is None:
                    return None
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method '{method}' not found."},
                }

            if req_id is None:
                return None
            return {"jsonrpc": "2.0", "id": req_id, "result": result}

        except NexusCoreError as exc:
            if req_id is None:
                return None
            if method == "tools/call":
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(exc.to_envelope(), ensure_ascii=True),
                            }
                        ],
                        "isError": True,
                    },
                }
            rpc_code = -32602 if isinstance(exc, (ValidationError, NotFoundError)) else -32000
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": rpc_code, "message": exc.message, "data": exc.details},
            }
        except Exception as exc:  # pragma: no cover
            if req_id is None:
                return None
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(exc)},
            }

    async def serve_stdio_lines(
        self,
        lines: list[str] | None = None,
    ) -> list[str]:
        """Processes newline-delimited JSON-RPC lines; helper for tests and stdio loops."""
        if lines is not None:
            outputs: list[str] = []
            for raw in lines:
                stripped = raw.strip()
                if not stripped:
                    continue
                try:
                    req = json.loads(stripped)
                except json.JSONDecodeError:
                    outputs.append(
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "id": None,
                                "error": {"code": -32700, "message": "Parse error"},
                            }
                        )
                    )
                    continue
                if not isinstance(req, dict):
                    continue
                resp = await self.handle_jsonrpc(req)
                if resp is not None:
                    outputs.append(json.dumps(resp, ensure_ascii=True))
            return outputs

        loop = asyncio.get_running_loop()
        while not self.daemon.stop_requested:
            raw_line = await loop.run_in_executor(None, sys.stdin.readline)
            if not raw_line:
                break
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                req = json.loads(stripped)
            except json.JSONDecodeError:
                err_line = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": "Parse error"},
                    }
                )
                sys.stdout.write(err_line + "\n")
                sys.stdout.flush()
                continue
            if isinstance(req, dict):
                resp = await self.handle_jsonrpc(req)
                if resp is not None:
                    sys.stdout.write(json.dumps(resp, ensure_ascii=True) + "\n")
                    sys.stdout.flush()
        return []


class MCPStreamableHttpServer:
    """Optional loopback Streamable HTTP transport for MCP clients (POST/GET /mcp)."""

    def __init__(
        self,
        mcp_server: NexusMCPServer,
        host: str = "127.0.0.1",
        port: int = 47102,
    ) -> None:
        self.mcp = mcp_server
        self.host = host
        self.port = port
        self._server: asyncio.AbstractServer | None = None
        self._active_tasks: set[asyncio.Task[Any]] = set()
        self._active_writers: set[asyncio.StreamWriter] = set()
        self.bound_port: int | None = None

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)
        sockets = self._server.sockets
        if sockets:
            self.bound_port = int(sockets[0].getsockname()[1])
        return self.bound_port or self.port

    async def stop(self) -> None:
        for writer in list(self._active_writers):
            with contextlib.suppress(Exception):
                writer.close()
        for task in list(self._active_tasks):
            if not task.done():
                task.cancel()
        if self._active_tasks:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(
                    asyncio.gather(*list(self._active_tasks), return_exceptions=True),
                    timeout=0.5,
                )
        self._active_tasks.clear()
        self._active_writers.clear()
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._server.wait_closed(), timeout=0.5)
            self._server = None

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        current_task = asyncio.current_task()
        if current_task is not None:
            self._active_tasks.add(current_task)
        self._active_writers.add(writer)
        sock = writer.get_extra_info("socket")
        if sock is not None:
            with contextlib.suppress(OSError):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        try:
            for _ in range(500):
                if self.mcp.daemon.stop_requested:
                    break
                raw_head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5.0)
                lines = raw_head.decode("latin-1").split("\r\n")
                if not lines or " " not in lines[0]:
                    break
                method, target, proto = lines[0].split(" ", 2)
                headers: dict[str, str] = {}
                for line in lines[1:]:
                    if ":" in line:
                        k, v = line.split(":", 1)
                        headers[k.strip().lower()] = v.strip()

                conn_hdr = headers.get("connection", "").lower()
                if self.mcp.daemon.stop_requested or conn_hdr == "close":
                    keep_alive = False
                elif proto.upper().startswith("HTTP/1.0"):
                    keep_alive = conn_hdr == "keep-alive"
                else:
                    keep_alive = True

                content_len = int(headers.get("content-length", "0") or "0")
                body = await reader.readexactly(content_len) if content_len > 0 else b""
                path = target.split("?", 1)[0].rstrip("/") or "/"

                if method.upper() == "OPTIONS":
                    self._write_response(writer, 204, b"", keep_alive=keep_alive)
                    await writer.drain()
                    if not keep_alive:
                        break
                    continue

                try:
                    self.mcp.daemon.permissions.validate_bearer_header(headers.get("authorization"))
                except AuthenticationError as exc:
                    err_bytes = json.dumps(
                        exc.to_envelope(), separators=(",", ":"), ensure_ascii=True
                    ).encode("utf-8")
                    self._write_response(writer, 401, err_bytes, keep_alive=keep_alive)
                    await writer.drain()
                    if not keep_alive:
                        break
                    continue

                if path != "/mcp":
                    err_bytes = json.dumps(
                        NotFoundError(f"MCP route {method} {path} not found.").to_envelope(),
                        separators=(",", ":"),
                        ensure_ascii=True,
                    ).encode("utf-8")
                    self._write_response(writer, 404, err_bytes, keep_alive=keep_alive)
                    await writer.drain()
                    if not keep_alive:
                        break
                    continue

                session_id = headers.get("mcp-session-id") or uuid.uuid4().hex
                if method.upper() == "GET":
                    meta = {
                        "server": "nexus-mcp",
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "transport": "Streamable HTTP",
                        "toolsCount": len(self.mcp.list_tools()),
                        "resourcesCount": len(self.mcp.list_resources()),
                        "promptsCount": len(self.mcp.list_prompts()),
                    }
                    self._write_response(
                        writer,
                        200,
                        json.dumps(meta, separators=(",", ":"), ensure_ascii=True).encode("utf-8"),
                        extra_headers={"Mcp-Session-Id": session_id},
                        keep_alive=keep_alive,
                    )
                    await writer.drain()
                    if not keep_alive:
                        break
                    continue

                if method.upper() == "POST":
                    try:
                        decoded = json.loads(body.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        err = {
                            "jsonrpc": "2.0",
                            "id": None,
                            "error": {"code": -32700, "message": "Invalid JSON body"},
                        }
                        self._write_response(
                            writer,
                            400,
                            json.dumps(err, separators=(",", ":"), ensure_ascii=True).encode("utf-8"),
                            extra_headers={"Mcp-Session-Id": session_id},
                            keep_alive=keep_alive,
                        )
                        await writer.drain()
                        if not keep_alive:
                            break
                        continue

                    if isinstance(decoded, list):
                        results = []
                        for item in decoded:
                            if isinstance(item, dict):
                                resp = await self.mcp.handle_jsonrpc(item)
                                if resp is not None:
                                    results.append(resp)
                        payload_bytes = json.dumps(
                            results, separators=(",", ":"), ensure_ascii=True
                        ).encode("utf-8")
                        self._write_response(
                            writer,
                            200 if results else 202,
                            payload_bytes if results else b"",
                            extra_headers={"Mcp-Session-Id": session_id},
                            keep_alive=keep_alive,
                        )
                    elif isinstance(decoded, dict):
                        resp = await self.mcp.handle_jsonrpc(decoded)
                        if resp is None:
                            self._write_response(
                                writer,
                                202,
                                b"",
                                extra_headers={"Mcp-Session-Id": session_id},
                                keep_alive=keep_alive,
                            )
                        else:
                            self._write_response(
                                writer,
                                200,
                                json.dumps(
                                    resp, separators=(",", ":"), ensure_ascii=True
                                ).encode("utf-8"),
                                extra_headers={"Mcp-Session-Id": session_id},
                                keep_alive=keep_alive,
                            )
                    else:
                        self._write_response(
                            writer,
                            400,
                            json.dumps(
                                {
                                    "jsonrpc": "2.0",
                                    "id": None,
                                    "error": {"code": -32600, "message": "Invalid JSON-RPC payload"},
                                },
                                separators=(",", ":"),
                            ).encode("utf-8"),
                            keep_alive=keep_alive,
                        )
                    await writer.drain()
                    if not keep_alive:
                        break
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError, ValueError):
            pass
        finally:
            self._active_writers.discard(writer)
            if current_task is not None:
                self._active_tasks.discard(current_task)
            writer.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(writer.wait_closed(), timeout=0.2)

    @staticmethod
    def _write_response(
        writer: asyncio.StreamWriter,
        status: int,
        body: bytes,
        extra_headers: dict[str, str] | None = None,
        *,
        keep_alive: bool = False,
    ) -> None:
        reason = {
            200: "OK",
            202: "Accepted",
            204: "No Content",
            400: "Bad Request",
            401: "Unauthorized",
            404: "Not Found",
        }.get(status, "OK")
        header_lines = [
            f"HTTP/1.1 {status} {reason}",
            "Content-Type: application/json",
            f"Content-Length: {len(body)}",
            "Connection: keep-alive" if keep_alive else "Connection: close",
        ]
        if keep_alive:
            header_lines.append("Keep-Alive: timeout=5, max=500")
        for k, v in (extra_headers or {}).items():
            header_lines.append(f"{k}: {v}")
        head = ("\r\n".join(header_lines) + "\r\n\r\n").encode("latin-1")
        writer.write(head + body)
