"""NEXUS Structured Error Hierarchy & JSON Error Envelopes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class NexusErrorDetail:
    code: str
    message: str
    status_code: int = 500
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self, request_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
                "timestamp": self.timestamp,
            }
        }
        if request_id:
            payload["error"]["requestId"] = request_id
        return payload


class NexusCoreError(Exception):
    """Base exception for all structured NEXUS core failures."""

    code: str = "NEXUS_INTERNAL_ERROR"
    status_code: int = 500

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details or {}

    def to_envelope(self, request_id: str | None = None) -> dict[str, Any]:
        return NexusErrorDetail(
            code=self.code,
            message=self.message,
            status_code=self.status_code,
            details=self.details,
        ).to_dict(request_id=request_id)


class AuthenticationError(NexusCoreError):
    code = "NEXUS_UNAUTHORIZED"
    status_code = 401


class PermissionDeniedError(NexusCoreError):
    code = "NEXUS_PERMISSION_DENIED"
    status_code = 403


class ValidationError(NexusCoreError):
    code = "NEXUS_VALIDATION_ERROR"
    status_code = 400


class NotFoundError(NexusCoreError):
    code = "NEXUS_NOT_FOUND"
    status_code = 404


class ConflictError(NexusCoreError):
    code = "NEXUS_CONFLICT"
    status_code = 409


class DaemonUnavailableError(NexusCoreError):
    code = "NEXUS_DAEMON_UNAVAILABLE"
    status_code = 503


class ProviderAuthError(NexusCoreError):
    code = "NEXUS_PROVIDER_AUTH_FAILED"
    status_code = 401


class ProviderRateLimitError(NexusCoreError):
    code = "NEXUS_PROVIDER_RATE_LIMITED"
    status_code = 429


class ProviderUpstreamError(NexusCoreError):
    code = "NEXUS_PROVIDER_UPSTREAM_ERROR"
    status_code = 502


class AdapterCompatibilityError(NexusCoreError):
    code = "NEXUS_ADAPTER_INCOMPATIBLE"
    status_code = 422


class AdapterProtocolError(NexusCoreError):
    code = "NEXUS_ADAPTER_PROTOCOL_ERROR"
    status_code = 502
