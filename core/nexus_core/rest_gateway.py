"""NEXUS REST Communication Layer (FastAPI App Factory + Async Stdlib Server)."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
import json
from pathlib import Path
import socket
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from core.nexus_core.config import APP_VERSION
from core.nexus_core.errors import NexusCoreError, NotFoundError, ValidationError
from core.nexus_core.providers import ProviderCompletionRequest
from sdk.python.nexus_sdk import EngineKind, NexusStatus

if TYPE_CHECKING:
    from core.nexus_core.daemon import NexusDaemon


@dataclass(slots=True)
class RestGatewayConfig:
    host: str = "127.0.0.1"
    port: int = 47100
    require_bearer_token: bool = True


async def dispatch_rest_request(
    daemon: "NexusDaemon",
    method: str,
    raw_path: str,
    headers: dict[str, str],
    body_bytes: bytes = b"",
) -> tuple[int, dict[str, Any]]:
    """Shared async REST request router used by both FastAPI and stdlib loopback server."""
    parsed = urlparse(raw_path)
    path = parsed.path.rstrip("/") or "/"
    upper_method = method.upper()
    auth_header = headers.get("authorization")

    try:
        if upper_method == "GET" and path == "/health":
            return 200, await daemon.health()

        if path.startswith("/api/v1/"):
            daemon.permissions.validate_bearer_header(auth_header)

        payload: dict[str, Any] = {}
        if body_bytes:
            try:
                decoded = json.loads(body_bytes.decode("utf-8"))
                if not isinstance(decoded, dict):
                    raise ValidationError("JSON request body must be an object.")
                payload = decoded
            except UnicodeDecodeError as exc:
                raise ValidationError("Request body must be valid UTF-8.") from exc
            except json.JSONDecodeError as exc:
                raise ValidationError(
                    "Invalid JSON payload.", details={"reason": str(exc)}
                ) from exc

        if upper_method == "GET" and path == "/api/v1/capabilities":
            return 200, await daemon.capabilities.discover()

        if upper_method == "GET" and path == "/api/v1/diagnostics":
            return 200, await daemon.diagnostics.collect()

        if upper_method == "GET" and path == "/api/v1/engines":
            return 200, {
                "engines": [
                    e.to_dict()
                    for e in daemon.engines.list_engines(
                        connected_adapters=daemon.adapters.list_adapters()
                    )
                ]
            }

        if path.startswith("/api/v1/engines/"):
            parts = path.split("/")
            if len(parts) == 5 and upper_method == "PATCH":
                raw_engine = parts[4].strip()
                engine_lookup = {
                    EngineKind.UNITY.value.lower(): EngineKind.UNITY,
                    EngineKind.GODOT.value.lower(): EngineKind.GODOT,
                }
                engine_kind = engine_lookup.get(raw_engine.lower())
                if engine_kind is None:
                    raise ValidationError(
                        f"Unsupported engine '{raw_engine}'. Expected Unity or Godot.",
                        details={"engine": raw_engine},
                    )
                raw_exec = payload.get("executablePath")
                if raw_exec is None or not isinstance(raw_exec, str):
                    raise ValidationError(
                        "Field 'executablePath' must be a string (empty to clear).",
                        details={"engine": engine_kind.value},
                    )
                cleaned_exec = raw_exec.strip()
                if "\x00" in cleaned_exec:
                    raise ValidationError(
                        "Executable path contains invalid NUL bytes.",
                        details={"engine": engine_kind.value},
                    )
                resolved_exec: Path | None = None
                if cleaned_exec:
                    candidate = Path(cleaned_exec).expanduser()
                    if ".." in candidate.parts:
                        raise ValidationError(
                            "Executable path must not contain '..' traversal segments.",
                            details={"engine": engine_kind.value},
                        )
                    resolved_exec = candidate.resolve()
                daemon.engines.set_engine_executable_path(engine_kind, resolved_exec)
                await daemon.storage.record_audit(
                    "operator",
                    "engines.set_executable_path",
                    "success",
                    target=engine_kind.value,
                    detail={"executablePath": str(resolved_exec) if resolved_exec else None},
                )
                return 200, {
                    "engines": [
                        e.to_dict()
                        for e in daemon.engines.list_engines(
                            connected_adapters=daemon.adapters.list_adapters()
                        )
                    ]
                }

        if upper_method == "GET" and path == "/api/v1/tools":
            return 200, {"tools": daemon.tools.list_tools()}

        if upper_method == "GET" and path == "/api/v1/events/recent":
            return 200, {"events": daemon.events.recent_events(limit=50)}

        if upper_method == "GET" and path == "/api/v1/projects":
            records = await daemon.projects.list_projects()
            return 200, {"projects": [p.to_dict() for p in records]}

        if upper_method == "POST" and path == "/api/v1/projects":
            record = await daemon.projects.register_project(
                name=str(payload.get("name", "")),
                engine=str(payload.get("engine", "")),
                root_path=str(payload.get("rootPath", "")),
                engine_version=str(payload.get("engineVersion", "Unverified")),
                notes=str(payload.get("notes", "")),
                require_existing_dir=bool(payload.get("requireExistingDir", False)),
            )
            return 201, {"project": record.to_dict()}

        if path.startswith("/api/v1/projects/"):
            project_id = path.split("/", 4)[-1]
            if upper_method == "GET":
                record = await daemon.projects.get_project(project_id)
                return 200, {"project": record.to_dict()}
            if upper_method == "PATCH":
                record = await daemon.projects.update_engine_association(
                    project_id, str(payload.get("engine", ""))
                )
                return 200, {"project": record.to_dict()}
            if upper_method == "DELETE":
                await daemon.projects.remove_project(project_id)
                return 200, {"deleted": True, "projectId": project_id}

        if upper_method == "GET" and path == "/api/v1/tasks":
            return 200, {
                "tasks": await daemon.tasks.list_tasks(),
                "concurrency": daemon.concurrency.snapshot(),
            }

        if upper_method == "GET" and path == "/api/v1/tasks/locks":
            return 200, daemon.concurrency.snapshot()

        if upper_method == "POST" and path == "/api/v1/tasks":
            created = await daemon.tasks.create_task_draft(
                project_id=str(payload.get("projectId", "")),
                title=str(payload.get("title", "")),
                priority=str(payload.get("priority", "normal")),
                agent_id=str(payload.get("agentId", "operator")),
                operations=payload.get("operations")
                if isinstance(payload.get("operations"), list)
                else None,
                retry_policy=payload.get("retryPolicy")
                if isinstance(payload.get("retryPolicy"), dict)
                else None,
                execution_limits=payload.get("executionLimits")
                if isinstance(payload.get("executionLimits"), dict)
                else None,
                adapter_id=str(payload["adapterId"]) if payload.get("adapterId") else None,
                approved_scopes=payload.get("approvedScopes")
                if isinstance(payload.get("approvedScopes"), list)
                else None,
            )
            if bool(payload.get("executeNow", False)):
                created = await daemon.tasks.execute_task(
                    created["id"],
                    adapter_id=str(payload["adapterId"]) if payload.get("adapterId") else None,
                )
            return 201, {"task": created}

        if upper_method == "GET" and path == "/api/v1/permissions/categories":
            return 200, {"categories": daemon.permissions.list_permission_categories()}

        if path.startswith("/api/v1/tasks/"):
            parts = path.split("/")
            if len(parts) == 5 and upper_method == "GET":
                task_id = parts[4]
                return 200, {"task": await daemon.tasks.get_task(task_id)}
            if len(parts) == 6 and upper_method == "GET" and parts[5] == "journal":
                task_id = parts[4]
                return 200, await daemon.tasks.get_task_recovery_details(task_id)
            if len(parts) == 6 and upper_method == "POST":
                task_id, action_route = parts[4], parts[5]
                if action_route == "control":
                    updated = await daemon.tasks.control_task(
                        task_id,
                        str(payload.get("action", "")),
                        adapter_id=str(payload["adapterId"]) if payload.get("adapterId") else None,
                        approved_scopes=payload.get("approvedScopes")
                        if isinstance(payload.get("approvedScopes"), list)
                        else None,
                    )
                    return 200, {"task": updated}
                if action_route == "execute":
                    executed = await daemon.tasks.execute_task(
                        task_id,
                        adapter_id=str(payload["adapterId"]) if payload.get("adapterId") else None,
                        approved_scopes=payload.get("approvedScopes")
                        if isinstance(payload.get("approvedScopes"), list)
                        else None,
                    )
                    return 200, {"task": executed}
                if action_route == "approve":
                    approved_task = await daemon.tasks.approve_task_checkpoint(
                        task_id,
                        approved=bool(payload.get("approved", True)),
                        approved_scopes=payload.get("approvedScopes")
                        if isinstance(payload.get("approvedScopes"), list)
                        else None,
                        resume_execution=bool(payload.get("resumeExecution", True)),
                        adapter_id=str(payload["adapterId"]) if payload.get("adapterId") else None,
                    )
                    return 200, {"task": approved_task}
                if action_route == "rollback":
                    raw_files = payload.get("files")
                    target_files = (
                        [str(f) for f in raw_files if isinstance(f, str) and f.strip()]
                        if isinstance(raw_files, list)
                        else None
                    )
                    rolled = await daemon.tasks.rollback_task(
                        task_id,
                        target_files=target_files,
                    )
                    return 200, {"task": rolled, "rollback": rolled.get("lastRollback")}

        if upper_method == "GET" and path == "/api/v1/providers":
            return 200, {"providers": await daemon.providers.list_providers()}

        if upper_method == "POST" and path == "/api/v1/providers":
            created_provider = await daemon.providers.register_provider(
                name=str(payload.get("name", "")),
                kind=str(payload.get("kind", "Custom Provider")),
                model_id=str(payload.get("modelId", "custom-model")),
                endpoint_url=str(payload.get("endpointUrl", "")),
                credential_ref=str(payload.get("credentialRef", "vault://nexus/custom_provider")),
                enabled=bool(payload.get("enabled", True)),
                options=payload.get("options") if isinstance(payload.get("options"), dict) else {},
                is_custom=True,
            )
            return 201, {"provider": created_provider}

        if path.startswith("/api/v1/providers/"):
            parts = path.split("/")
            # /api/v1/providers/{id}
            if len(parts) == 5:
                provider_id = parts[4]
                if upper_method == "PATCH":
                    updated_provider = await daemon.providers.update_provider(
                        provider_id,
                        enabled=payload.get("enabled")
                        if isinstance(payload.get("enabled"), bool)
                        else None,
                        model_id=str(payload["modelId"])
                        if "modelId" in payload
                        else None,
                        endpoint_url=str(payload["endpointUrl"])
                        if "endpointUrl" in payload
                        else None,
                        credential_ref=str(payload["credentialRef"])
                        if "credentialRef" in payload
                        else None,
                        options=payload.get("options")
                        if isinstance(payload.get("options"), dict)
                        else None,
                    )
                    return 200, {"provider": updated_provider}
                if upper_method == "DELETE":
                    await daemon.providers.delete_provider(provider_id)
                    return 200, {"deleted": True, "providerId": provider_id}
            # /api/v1/providers/{id}/{action}
            if len(parts) == 6 and upper_method == "POST":
                provider_id, action = parts[4], parts[5]
                if action == "secret":
                    stored = await daemon.providers.store_provider_secret(
                        provider_id, str(payload.get("secret", ""))
                    )
                    return 200, stored
                if action == "verify":
                    verified = await daemon.providers.verify_provider(provider_id)
                    return 200, {"verification": verified.to_dict()}
                if action == "generate":
                    raw_messages = payload.get("messages")
                    if not isinstance(raw_messages, list) or not raw_messages:
                        prompt_text = str(payload.get("prompt", "")).strip()
                        if not prompt_text:
                            raise ValidationError(
                                "Provide either non-empty 'messages' list or 'prompt' string."
                            )
                        raw_messages = [{"role": "user", "content": prompt_text}]
                    req_obj = ProviderCompletionRequest(
                        messages=raw_messages,
                        model=str(payload["model"]) if payload.get("model") else None,
                        system_instruction=str(payload["systemInstruction"])
                        if payload.get("systemInstruction")
                        else None,
                        max_tokens=int(payload["maxTokens"])
                        if payload.get("maxTokens") is not None
                        else None,
                        temperature=float(payload["temperature"])
                        if payload.get("temperature") is not None
                        else None,
                    )
                    resp = await daemon.providers.generate(provider_id, req_obj)
                    return 200, {"completion": resp.to_dict()}

        if upper_method == "GET" and path == "/api/v1/mcp/status":
            return 200, {
                "serverName": "nexus-mcp",
                "protocolVersion": "2025-03-26",
                "transports": daemon.mcp.config.supported_transports,
                "mcpHttpPort": daemon.mcp_port,
                "tools": daemon.mcp.list_tools(),
                "resources": daemon.mcp.list_resources(),
                "prompts": daemon.mcp.list_prompts(),
            }

        if upper_method == "GET" and path == "/api/v1/adapters":
            return 200, {
                "adapters": daemon.adapters.list_adapters(),
                "capabilities": daemon.adapters.capabilities.summary(),
                "errors": daemon.adapters.list_errors(),
            }

        if upper_method == "POST" and path == "/api/v1/adapters/install":
            raw_manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else payload
            installed = await daemon.adapters.install_adapter(raw_manifest)
            return 201, {"adapter": installed}

        if path.startswith("/api/v1/adapters/"):
            parts = path.split("/")
            if len(parts) == 5:
                adapter_id = parts[4]
                if upper_method == "GET":
                    return 200, {"adapter": daemon.adapters.get_record(adapter_id).to_descriptor()}
                if upper_method == "DELETE":
                    await daemon.adapters.uninstall_adapter(adapter_id)
                    return 200, {"uninstalled": True, "adapterId": adapter_id}
            if len(parts) == 6:
                adapter_id, action = parts[4], parts[5]
                if upper_method == "POST" and action == "connect":
                    return 200, {"adapter": await daemon.adapters.connect_adapter(adapter_id)}
                if upper_method == "POST" and action == "disconnect":
                    return 200, {"adapter": await daemon.adapters.disconnect_adapter(adapter_id)}
                if upper_method == "POST" and action == "health":
                    return 200, await daemon.adapters.health_check_adapter(adapter_id)
                if upper_method == "GET" and action == "tools":
                    return 200, {"tools": daemon.adapters.list_tools_for_adapter(adapter_id)}
                if upper_method == "POST" and action == "screenshot":
                    return 200, {
                        "screenshot": await daemon.adapters.capture_screenshot(
                            adapter_id,
                            project_id=str(payload.get("projectId", "")),
                            viewport=str(payload.get("viewport", "SceneView")),
                        )
                    }
                if upper_method == "GET" and action == "state":
                    project_id = parsed.query.split("projectId=")[-1].split("&")[0] if "projectId=" in parsed.query else ""
                    return 200, {
                        "projectState": await daemon.adapters.get_project_state(
                            adapter_id, project_id=project_id
                        )
                    }
            if len(parts) == 7 and parts[5] == "tools" and parts[6] == "execute" and upper_method == "POST":
                adapter_id = parts[4]
                raw_args = (
                    payload.get("arguments")
                    if isinstance(payload.get("arguments"), dict)
                    else {}
                )
                result = await daemon.adapters.execute_tool(
                    adapter_id=adapter_id,
                    tool_id=str(payload.get("toolId", "")),
                    project_id=str(payload.get("projectId", "")),
                    arguments=raw_args,
                    approved=bool(
                        payload.get("approved")
                        or payload.get("_approved")
                        or raw_args.get("_approved")
                    ),
                    approved_scopes=payload.get("approvedScopes")
                    if isinstance(payload.get("approvedScopes"), list)
                    else None,
                )
                return 200, {"result": result}

        if upper_method == "POST" and path == "/api/v1/daemon/shutdown":
            daemon.request_shutdown()
            return 202, {"status": NexusStatus.DISCONNECTED.value, "shuttingDown": True}

        raise NotFoundError(f"Route {upper_method} {path} not found.")

    except NexusCoreError as exc:
        return exc.status_code, exc.to_envelope()
    except Exception as exc:  # pragma: no cover
        daemon.logger.exception("Unhandled REST dispatch error")
        err = NexusCoreError(
            "Internal daemon error.",
            details={"type": type(exc).__name__},
        )
        return 500, err.to_envelope()


_HTTP_REASON_MAP: dict[int, str] = {
    200: "OK",
    201: "Created",
    202: "Accepted",
    204: "No Content",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    409: "Conflict",
    413: "Payload Too Large",
    422: "Unprocessable Entity",
    500: "Internal Server Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
}


class StdlibLoopbackHttpServer:
    """Zero-dependency asyncio HTTP/1.1 JSON server bound to loopback with Keep-Alive."""

    def __init__(self, daemon: "NexusDaemon", host: str, port: int) -> None:
        self.daemon = daemon
        self.host = host
        self.port = port
        self._server: asyncio.AbstractServer | None = None
        self._active_tasks: set[asyncio.Task[Any]] = set()
        self._active_writers: set[asyncio.StreamWriter] = set()
        self.bound_port: int | None = None

    async def start(self) -> int:
        self._server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
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
                if self.daemon.stop_requested:
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

                content_len = int(headers.get("content-length", "0") or "0")
                if content_len > 1_048_576:
                    status, payload = 413, {
                        "error": {
                            "code": "NEXUS_PAYLOAD_TOO_LARGE",
                            "message": "Payload exceeds 1MB limit.",
                        }
                    }
                    keep_alive = False
                else:
                    body = await reader.readexactly(content_len) if content_len > 0 else b""
                    if method.upper() == "OPTIONS":
                        status, payload = 204, {}
                    else:
                        status, payload = await dispatch_rest_request(
                            self.daemon, method, target, headers, body
                        )
                    conn_hdr = headers.get("connection", "").lower()
                    if self.daemon.stop_requested or conn_hdr == "close":
                        keep_alive = False
                    elif proto.upper().startswith("HTTP/1.0"):
                        keep_alive = conn_hdr == "keep-alive"
                    else:
                        keep_alive = True

                encoded = (
                    b""
                    if status == 204
                    else json.dumps(
                        payload, separators=(",", ":"), ensure_ascii=True
                    ).encode("utf-8")
                )
                reason = _HTTP_REASON_MAP.get(status, "OK")
                conn_header_line = (
                    "Connection: keep-alive\r\nKeep-Alive: timeout=5, max=500"
                    if keep_alive
                    else "Connection: close"
                )
                response_head = (
                    f"HTTP/1.1 {status} {reason}\r\n"
                    f"Content-Type: application/json\r\n"
                    f"Content-Length: {len(encoded)}\r\n"
                    f"{conn_header_line}\r\n\r\n"
                ).encode("latin-1")
                writer.write(response_head + encoded)
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


def create_fastapi_app(daemon: "NexusDaemon") -> Any:
    """Builds a FastAPI application wired to NexusDaemon when fastapi is installed."""
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse

    app = FastAPI(title="NEXUS Local Daemon API", version=APP_VERSION)

    @app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def nexus_proxy(request: Request, full_path: str) -> JSONResponse:
        body = await request.body()
        headers = {k.lower(): v for k, v in request.headers.items()}
        status, payload = await dispatch_rest_request(
            daemon, request.method, "/" + full_path, headers, body
        )
        return JSONResponse(status_code=status, content=payload)

    return app
