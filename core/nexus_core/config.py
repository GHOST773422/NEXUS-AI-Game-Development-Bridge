"""NEXUS Configuration Manager & Loopback Auth Token Lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import secrets
from typing import Any

from core.nexus_core.errors import ValidationError

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
APP_VERSION = "0.10.0"


def default_data_dir() -> Path:
    """Resolves the OS-appropriate local NEXUS data directory."""
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            return Path(local_app_data) / "NEXUS"
    return Path.home() / ".nexus"


@dataclass(slots=True)
class NexusDaemonConfig:
    bind_host: str = "127.0.0.1"
    rest_port: int = 47100
    ws_port: int = 47101
    mcp_http_port: int = 47102
    require_bearer_token: bool = True
    allow_remote_bind: bool = False
    log_level: str = "INFO"
    data_dir: Path = field(default_factory=default_data_dir)
    sqlite_path: Path = field(default_factory=lambda: default_data_dir() / "nexus.db")
    token_path: Path = field(default_factory=lambda: default_data_dir() / "daemon.token")
    log_file: Path | None = None
    allowed_project_roots: list[Path] = field(default_factory=list)
    _api_token: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir).expanduser().resolve()
        self.sqlite_path = Path(self.sqlite_path).expanduser().resolve()
        self.token_path = Path(self.token_path).expanduser().resolve()
        if self.log_file is not None:
            self.log_file = Path(self.log_file).expanduser().resolve()
        self.validate()

    def validate(self) -> None:
        if not self.allow_remote_bind and self.bind_host not in LOOPBACK_HOSTS:
            raise ValidationError(
                f"Refusing non-loopback bind_host '{self.bind_host}' when allow_remote_bind is False.",
                details={"bindHost": self.bind_host},
            )
        for name, port in (
            ("rest_port", self.rest_port),
            ("ws_port", self.ws_port),
            ("mcp_http_port", self.mcp_http_port),
        ):
            if port < 0 or port > 65535:
                raise ValidationError(f"Invalid port for {name}: {port}")

    def ensure_data_dir(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def get_or_create_api_token(self) -> str:
        """Resolves API token from env or creates a local random token on disk."""
        if self._api_token:
            return self._api_token

        env_token = os.environ.get("NEXUS_API_TOKEN", "").strip()
        if env_token:
            self._api_token = env_token
            return env_token

        self.ensure_data_dir()
        if self.token_path.exists():
            stored = self.token_path.read_text(encoding="utf-8").strip()
            if stored:
                self._api_token = stored
                return stored

        generated = secrets.token_urlsafe(32)
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(generated, encoding="utf-8")
        try:
            os.chmod(self.token_path, 0o600)
        except OSError:
            # Windows ACLs differ from POSIX chmod; ignore gracefully on Windows.
            pass
        self._api_token = generated
        return generated

    def to_safe_dict(self) -> dict[str, Any]:
        """Exports configuration without revealing secret tokens."""
        return {
            "version": APP_VERSION,
            "bindHost": self.bind_host,
            "restPort": self.rest_port,
            "wsPort": self.ws_port,
            "mcpHttpPort": self.mcp_http_port,
            "requireBearerToken": self.require_bearer_token,
            "logLevel": self.log_level,
            "dataDir": str(self.data_dir),
            "sqlitePath": str(self.sqlite_path),
            "logFile": str(self.log_file) if self.log_file is not None else None,
            "allowedProjectRoots": [str(p) for p in self.allowed_project_roots],
            "tokenConfigured": bool(self._api_token or self.token_path.exists()),
        }

    @classmethod
    def from_env(cls, config_file: Path | None = None) -> "NexusDaemonConfig":
        file_data: dict[str, Any] = {}
        if config_file and config_file.exists():
            file_data = json.loads(config_file.read_text(encoding="utf-8"))

        network = file_data.get("network", {})
        storage = file_data.get("storage", {})

        base_default_dir = default_data_dir()
        data_dir = Path(
            os.environ.get("NEXUS_DATA_DIR", str(base_default_dir))
        ).expanduser()
        sqlite_name = str(storage.get("sqliteFilename", "nexus.db"))
        sqlite_path = Path(
            os.environ.get("NEXUS_SQLITE_PATH", str(data_dir / sqlite_name))
        ).expanduser()
        token_path = data_dir / "daemon.token"
        raw_log_file = os.environ.get("NEXUS_LOG_FILE", "").strip()
        log_file = Path(raw_log_file).expanduser() if raw_log_file else None

        raw_roots = os.environ.get("NEXUS_ALLOWED_ROOTS", "")
        allowed_roots = [
            Path(p.strip()).expanduser().resolve()
            for p in raw_roots.split(os.pathsep)
            if p.strip()
        ]

        return cls(
            bind_host=os.environ.get(
                "NEXUS_BIND_HOST", str(network.get("bindAddress", "127.0.0.1"))
            ),
            rest_port=int(
                os.environ.get("NEXUS_REST_PORT", str(network.get("restPort", 47100)))
            ),
            ws_port=int(
                os.environ.get("NEXUS_WS_PORT", str(network.get("websocketPort", 47101)))
            ),
            mcp_http_port=int(
                os.environ.get("NEXUS_MCP_PORT", str(network.get("mcpHttpPort", 47102)))
            ),
            require_bearer_token=os.environ.get(
                "NEXUS_REQUIRE_AUTH",
                "true" if network.get("requireBearerToken", True) else "false",
            ).lower()
            == "true",
            allow_remote_bind=os.environ.get("NEXUS_ALLOW_REMOTE_BIND", "false").lower()
            == "true",
            log_level=os.environ.get("NEXUS_LOG_LEVEL", "INFO").upper(),
            data_dir=data_dir,
            sqlite_path=sqlite_path,
            token_path=token_path,
            log_file=log_file,
            allowed_project_roots=allowed_roots,
        )
