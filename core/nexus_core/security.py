"""NEXUS Stage 9 Permission Categories, Input Validation, Sandboxing & Local Bearer Auth."""

from __future__ import annotations

import hmac
from pathlib import Path
import re
from typing import Any

from core.nexus_core.errors import AuthenticationError, PermissionDeniedError, ValidationError
from sdk.python.nexus_sdk import PermissionScope

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

ALLOWED_PROCESS_NAMES = frozenset(
    {
        "unity.exe",
        "unity",
        "godot.exe",
        "godot_v4.exe",
        "godot",
        "godot4",
        "dotnet.exe",
        "dotnet",
    }
)

# Explicit Stage 9 Capability-Based Permission Categories
PERMISSION_CATEGORIES: dict[str, dict[str, Any]] = {
    "Read-only inspection": {
        "scopes": [PermissionScope.READ_PROJECT.value],
        "destructive": False,
        "requiresApproval": False,
    },
    "Non-destructive modification": {
        "scopes": [PermissionScope.EXECUTE_EDITOR_ACTION.value],
        "destructive": False,
        "requiresApproval": False,
    },
    "Project modification": {
        "scopes": [PermissionScope.WRITE_SCENE.value, PermissionScope.MODIFY_ASSETS.value],
        "destructive": True,
        "requiresApproval": True,
    },
    "Script execution": {
        "scopes": [PermissionScope.WRITE_SCRIPT.value, PermissionScope.RUN_TESTS.value],
        "destructive": True,
        "requiresApproval": False,
    },
    "Runtime control": {
        "scopes": [PermissionScope.EXECUTE_EDITOR_ACTION.value, PermissionScope.RUN_TESTS.value],
        "destructive": False,
        "requiresApproval": False,
    },
    "Build and export": {
        "scopes": [PermissionScope.BUILD_EXPORT.value],
        "destructive": True,
        "requiresApproval": True,
    },
    "External process access": {
        "scopes": [PermissionScope.PROCESS_SPAWN_RESTRICTED.value],
        "destructive": True,
        "requiresApproval": True,
    },
}

PERMISSION_CATEGORY_BY_SCOPE: dict[PermissionScope, str] = {
    PermissionScope.READ_PROJECT: "Read-only inspection",
    PermissionScope.EXECUTE_EDITOR_ACTION: "Non-destructive modification",
    PermissionScope.WRITE_SCENE: "Project modification",
    PermissionScope.MODIFY_ASSETS: "Project modification",
    PermissionScope.WRITE_SCRIPT: "Script execution",
    PermissionScope.RUN_TESTS: "Runtime control",
    PermissionScope.BUILD_EXPORT: "Build and export",
    PermissionScope.PROCESS_SPAWN_RESTRICTED: "External process access",
}

DESTRUCTIVE_SCOPES = frozenset(
    {
        PermissionScope.WRITE_SCENE,
        PermissionScope.MODIFY_ASSETS,
        PermissionScope.BUILD_EXPORT,
        PermissionScope.PROCESS_SPAWN_RESTRICTED,
    }
)

_TOOL_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{1,120}$")
_WINDOWS_DRIVE_OR_UNC_RE = re.compile(r"^([a-zA-Z]:/|//)")
_PATH_ARG_KEYS = frozenset(
    {
        "path",
        "filePath",
        "assetPath",
        "resourcePath",
        "scenePath",
        "scriptPath",
        "targetPath",
        "outputPath",
        "exportPath",
    }
)
_SHELL_META_RE = re.compile(r"[;&|`$><]")
_SENSITIVE_KEY_TOKENS = ("secret", "apikey", "api_key", "token", "password", "credential")


class PermissionManager:
    """Enforces capability-based permissions, input validation, path sandboxing & loopback auth."""

    def __init__(
        self,
        allowed_roots: list[Path] | None = None,
        api_token: str | None = None,
        require_auth: bool = True,
    ) -> None:
        self.allowed_roots = [p.expanduser().resolve() for p in (allowed_roots or [])]
        self._api_token = api_token
        self.require_auth = require_auth

    def set_api_token(self, token: str) -> None:
        self._api_token = token

    def list_permission_categories(self) -> dict[str, dict[str, Any]]:
        return PERMISSION_CATEGORIES

    def get_permission_category(self, scope: PermissionScope) -> str:
        return PERMISSION_CATEGORY_BY_SCOPE.get(scope, "Non-destructive modification")

    def is_destructive_scope(self, scope: PermissionScope) -> bool:
        return scope in DESTRUCTIVE_SCOPES or scope in {
            PermissionScope.WRITE_SCENE,
            PermissionScope.WRITE_SCRIPT,
        }

    def assert_loopback_bind(self, host: str) -> str:
        clean_host = (host or "").strip()
        if clean_host not in LOOPBACK_HOSTS:
            raise PermissionDeniedError(
                f"Network exposure blocked: daemon bind_host '{clean_host}' must be loopback.",
                details={"bindHost": clean_host, "allowed": sorted(LOOPBACK_HOSTS)},
            )
        return clean_host

    def validate_token_string(self, provided_token: str | None) -> None:
        """Verifies a raw bearer token in constant time."""
        if not self.require_auth:
            return
        if not self._api_token:
            raise AuthenticationError("Daemon bearer token is not initialized.")
        provided = (provided_token or "").strip()
        if not provided:
            raise AuthenticationError("Missing authentication token.")
        if not hmac.compare_digest(provided, self._api_token):
            raise AuthenticationError("Invalid local bearer token.")

    def validate_bearer_header(self, authorization_header: str | None) -> None:
        """Verifies Authorization: Bearer <token> in constant time."""
        if not self.require_auth:
            return
        if not self._api_token:
            raise AuthenticationError("Daemon bearer token is not initialized.")
        if not authorization_header:
            raise AuthenticationError("Missing Authorization header.")
        parts = authorization_header.strip().split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise AuthenticationError("Authorization header must use Bearer scheme.")
        self.validate_token_string(parts[1])

    def validate_project_registration_path(self, candidate: Path) -> Path:
        """Resolves path and ensures it does not escape configured allowed_roots."""
        if ".." in candidate.parts:
            raise PermissionDeniedError(
                "Path traversal segments ('..') are not allowed in project paths.",
                details={"path": str(candidate)},
            )
        resolved = candidate.expanduser().resolve()
        if self.allowed_roots and not any(
            resolved == root or root in resolved.parents for root in self.allowed_roots
        ):
            raise PermissionDeniedError(
                "Project path is outside allowed NEXUS workspace roots.",
                details={"path": str(resolved)},
            )
        return resolved

    def is_path_within_project(self, project_root: Path, target_path: Path) -> bool:
        resolved_root = project_root.expanduser().resolve()
        resolved_target = target_path.expanduser().resolve()
        return resolved_target == resolved_root or resolved_root in resolved_target.parents

    def assert_path_within_project(self, project_root: Path, target_path: Path) -> Path:
        raw_str = str(target_path).replace("\\", "/")
        if ".." in raw_str.split("/"):
            raise PermissionDeniedError(
                "Path traversal segments ('..') are blocked.",
                details={"targetPath": raw_str},
            )
        resolved_target = target_path.expanduser().resolve()
        if not self.is_path_within_project(project_root, resolved_target):
            raise PermissionDeniedError(
                "Target path escapes the registered project directory sandbox.",
                details={
                    "projectRoot": str(project_root.expanduser().resolve()),
                    "targetPath": str(resolved_target),
                },
            )
        return resolved_target

    def resolve_engine_resource_path(self, project_root: Path, raw_ref: str) -> Path:
        """Resolves res://, Assets/, relative or absolute path strictly within project_root."""
        clean = raw_ref.strip().replace("\\", "/")
        if not clean:
            raise ValidationError("Resource path cannot be empty.")
        if "\x00" in clean or any(ord(ch) < 32 for ch in clean):
            raise ValidationError("Resource path contains illegal control characters.")
        if ".." in clean.split("/"):
            raise PermissionDeniedError(
                f"Path traversal ('..') forbidden in path '{raw_ref}'.",
                details={"path": raw_ref},
            )
        if clean.startswith("res://"):
            rel = clean[len("res://") :].lstrip("/")
            candidate = project_root / rel
        elif _WINDOWS_DRIVE_OR_UNC_RE.match(clean):
            resolved_root = project_root.expanduser().resolve().as_posix().lower()
            if not clean.lower().startswith(resolved_root):
                raise PermissionDeniedError(
                    "External drive/UNC path is outside the registered project sandbox.",
                    details={"path": raw_ref},
                )
            candidate = Path(clean)
        elif Path(clean).is_absolute():
            candidate = Path(clean)
        else:
            candidate = project_root / clean
        return self.assert_path_within_project(project_root, candidate)

    def validate_tool_arguments(
        self,
        tool_id: str,
        arguments: dict[str, Any],
        *,
        project_root: Path | None = None,
    ) -> None:
        """Validates tool identifiers, nested argument safety, process args & project-root paths."""
        clean_tool = (tool_id or "").strip()
        if not _TOOL_ID_RE.match(clean_tool):
            raise ValidationError(
                f"Invalid tool identifier '{tool_id}'.",
                details={"toolId": tool_id},
            )
        if not isinstance(arguments, dict):
            raise ValidationError("Tool arguments must be a JSON object.")
        if len(arguments) > 64:
            raise ValidationError("Tool arguments object exceeds maximum allowed key count (64).")

        def _walk(node: Any, depth: int) -> None:
            if depth > 8:
                raise ValidationError("Tool arguments exceed maximum nesting depth (8).")
            if isinstance(node, str):
                if "\x00" in node:
                    raise ValidationError("Tool arguments cannot contain NUL bytes.")
            elif isinstance(node, dict):
                if len(node) > 64:
                    raise ValidationError("Nested argument object exceeds key limit (64).")
                for k, v in node.items():
                    if not isinstance(k, str) or "\x00" in k:
                        raise ValidationError("Invalid argument key.")
                    _walk(v, depth + 1)
            elif isinstance(node, list):
                if len(node) > 500:
                    raise ValidationError("Argument array exceeds length limit (500).")
                for item in node:
                    _walk(item, depth + 1)

        _walk(arguments, 0)

        for key in _PATH_ARG_KEYS:
            val = arguments.get(key)
            if isinstance(val, str) and val.strip():
                if project_root is not None:
                    self.resolve_engine_resource_path(project_root, val)
                else:
                    clean_ref = val.strip().replace("\\", "/")
                    if ".." in clean_ref.split("/"):
                        raise PermissionDeniedError(
                            f"Path traversal ('..') forbidden in argument '{key}'.",
                            details={"argument": key, "value": val},
                        )

        for proc_key in ("command", "shell", "executable", "shellCommand"):
            raw_proc = arguments.get(proc_key)
            if isinstance(raw_proc, str) and raw_proc.strip():
                if _SHELL_META_RE.search(raw_proc):
                    raise PermissionDeniedError(
                        f"Shell metacharacters forbidden in '{proc_key}'.",
                        details={"argument": proc_key},
                    )
                if not self.is_allowed_executable(Path(raw_proc.strip().split()[0])):
                    raise PermissionDeniedError(
                        f"Unauthorized executable '{raw_proc}' blocked by sandbox.",
                        details={"argument": proc_key},
                    )

    def validate_destructive_operation(
        self,
        scopes: list[PermissionScope],
        *,
        approved: bool,
        allow_restricted_process: bool = False,
        tool_id: str | None = None,
    ) -> None:
        """Applies explicit restrictions for destructive scopes & blocks restricted process spawns."""
        for scope in scopes:
            if scope == PermissionScope.PROCESS_SPAWN_RESTRICTED and not allow_restricted_process:
                raise PermissionDeniedError(
                    "Unrestricted OS process execution scope 'process:restricted' is forbidden."
                )
        gated = (
            self.requires_approval_for_tool(tool_id, scopes)
            if tool_id
            else [s for s in scopes if self.requires_approval(s)]
        )
        for scope in gated:
            if not approved:
                raise PermissionDeniedError(
                    f"Destructive operation requires explicit approval for scope '{scope.value}'.",
                    details={
                        "scope": scope.value,
                        "category": self.get_permission_category(scope),
                        **({"toolId": tool_id} if tool_id else {}),
                    },
                )

    def is_allowed_executable(self, executable: Path) -> bool:
        return executable.name.lower() in ALLOWED_PROCESS_NAMES

    def requires_approval(self, scope: PermissionScope) -> bool:
        return scope in DESTRUCTIVE_SCOPES

    def is_destructive_tool_id(self, tool_id: str) -> bool:
        leaf = (tool_id or "").strip().split(".")[-1].lower()
        return leaf in {"delete_object", "delete_node", "remove_component"} or leaf.startswith(
            "delete_"
        )

    def requires_approval_for_tool(
        self, tool_id: str, scopes: list[PermissionScope]
    ) -> list[PermissionScope]:
        gated = [s for s in scopes if self.requires_approval(s)]
        if not gated and self.is_destructive_tool_id(tool_id):
            return [PermissionScope.WRITE_SCENE]
        return gated


def redact_sensitive_fields(value: Any) -> Any:
    """Recursively redacts secrets, bearer tokens, and passwords from stored logs/records."""
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for k, v in value.items():
            lower_k = str(k).lower()
            if any(tok in lower_k for tok in _SENSITIVE_KEY_TOKENS):
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = redact_sensitive_fields(v)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive_fields(item) for item in value]
    return value
